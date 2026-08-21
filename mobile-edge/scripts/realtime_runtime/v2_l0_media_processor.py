"""Controlled, L0-only decoder for authenticated v2 encoded media frames.

This module is deliberately downstream of ``MediaSecurityAuthority`` and
``PcMediaBuffer``.  It receives plaintext only after the authenticated
ciphertext is durable, decodes a video access unit in process memory, and
records an immutable *technical* L0 fact.  It has no path to scopes, interest,
packages, notifications, or L1.

The first production decoder is H.264 Annex-B.  A different Android codec must
be declared and implemented explicitly; guessing a codec from bytes would turn
a decoder failure into an unverifiable semantic input.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .contracts import RealtimeSemanticFact, SourceKind
from .encoded_media_frame import EncodedMediaFrame, EncodedMediaTrack, decode_encoded_media_frame
from .media_buffer import PcBufferedFragment
from .media_security import AcceptedMediaFragment, MediaFragmentHeader
from .semantic_ledger import RealtimeSemanticLedger


_POLICY_VERSION = "v2-h264-annexb-controlled-l0-decoder.v1"
_PROVENANCE_HASH = hashlib.sha256(_POLICY_VERSION.encode("utf-8")).hexdigest()
_REPLAY_CACHE_LIMIT = 4_096


class V2L0MediaProcessorError(ValueError):
    """The authenticated v2 frame cannot become a safe L0 decoder input."""


@dataclass(frozen=True)
class V2L0ProcessingReceipt:
    state: str
    fact_id: str | None
    sequence: int
    media_hash: str
    decoded_evidence_hash: str | None


@dataclass(frozen=True)
class V2L0DispatchReceipt:
    """Immediate ingress result, separate from the eventual L0 outcome."""

    state: str
    sequence: int
    media_hash: str


@dataclass(frozen=True)
class _QueuedL0Work:
    accepted: AcceptedMediaFragment
    buffered: PcBufferedFragment
    plaintext_bytes: int


@dataclass(frozen=True)
class _QueuePressureWork:
    header: MediaFragmentHeader
    frame: EncodedMediaFrame


VideoDecoder = Callable[[str, bytes, bool], bytes]


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class _H264AnnexBDecoder:
    """Session-local, memory-only PyAV decoder.

    Decoder state intentionally is not serialized.  After a PC restart the
    old encrypted buffer remains retained as evidence, but it is not silently
    reinterpreted with a lost session key or guessed codec context.  The next
    live keyframe starts a new L0 decoder run.
    """

    def __init__(self) -> None:
        self._contexts: dict[str, object] = {}

    def __call__(self, session_key: str, payload: bytes, is_key_frame: bool) -> bytes:
        if is_key_frame:
            self._contexts.pop(session_key, None)
        context = self._contexts.get(session_key)
        if context is None:
            if not is_key_frame:
                raise V2L0MediaProcessorError("v2_l0_decoder_waiting_for_keyframe")
            try:
                import av
            except ImportError as error:  # pragma: no cover - environment fault, not a media claim
                raise V2L0MediaProcessorError("v2_l0_h264_decoder_unavailable") from error
            context = av.CodecContext.create("h264", "r")
            self._contexts[session_key] = context
        try:
            import av

            decoded = context.decode(av.Packet(payload))  # type: ignore[union-attr]
        except Exception as error:
            raise V2L0MediaProcessorError("v2_l0_h264_decode_failed") from error
        if not decoded:
            raise V2L0MediaProcessorError("v2_l0_h264_no_decoded_picture")
        digest = hashlib.sha256()
        for frame in decoded:
            # Plane bytes are sufficient to prove that the controlled decoder
            # produced a picture.  No clear media or pixels are written here.
            digest.update(str(frame.format.name).encode("ascii", "strict"))
            digest.update(int(frame.width).to_bytes(4, "big", signed=False))
            digest.update(int(frame.height).to_bytes(4, "big", signed=False))
            for plane in frame.planes:
                digest.update(bytes(plane))
        return digest.digest()


class V2L0MediaProcessor:
    """Validate and decode the v2 video path without any L1 side effect."""

    def __init__(
        self,
        *,
        root: Path,
        semantic_ledger_path: Path,
        video_decoder: VideoDecoder | None = None,
        now_elapsed_ns: Callable[[], int] | None = None,
    ) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._root, 0o700)
        except OSError:
            pass
        self._semantic_ledger_path = Path(semantic_ledger_path)
        self._semantic_ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._video_decoder = video_decoder or _H264AnnexBDecoder()
        self._now_elapsed_ns = now_elapsed_ns or time.monotonic_ns
        self._lock = threading.RLock()
        self._last_track_end_us: dict[tuple[str, int, EncodedMediaTrack], int] = {}
        self._decoder_generation: dict[tuple[str, int, EncodedMediaTrack], int] = {}
        # The decoder itself must not be the only protection against a
        # reference-frame hole.  Test doubles and future decoder adapters are
        # allowed to be simpler than PyAV, so the admission boundary keeps the
        # "new IDR after a discontinuity" rule independently.
        self._video_requires_key_frame: dict[tuple[str, int, EncodedMediaTrack], bool] = {}
        self._continuity_generation: dict[tuple[str, int], int] = {}
        self._completed_replays: dict[tuple[str, int, EncodedMediaTrack, int, int, str], V2L0ProcessingReceipt] = {}
        self._completed_replay_order: deque[tuple[str, int, EncodedMediaTrack, int, int, str]] = deque()
        self._receipts_path = self._root / "v2_l0_receipts.jsonl"

    def validate(self, accepted: AcceptedMediaFragment) -> EncodedMediaFrame:
        """Validate inner framing before buffer persistence advances sequence."""

        return self.validate_plaintext(accepted.header, accepted.plaintext)

    @staticmethod
    def validate_plaintext(header: MediaFragmentHeader, plaintext: bytes) -> EncodedMediaFrame:
        """Validator shape consumed directly by ``MediaSecurityAuthority``."""

        frame = decode_encoded_media_frame(plaintext)
        if header.media_sha256 != _sha256(plaintext):
            raise V2L0MediaProcessorError("v2_l0_media_hash_mismatch")
        if frame.pts_us != header.pts_start_us or frame.pts_us + frame.duration_us != header.pts_end_us:
            raise V2L0MediaProcessorError("v2_l0_frame_header_pts_mismatch")
        return frame

    def process(self, accepted: AcceptedMediaFragment, buffered: PcBufferedFragment) -> V2L0ProcessingReceipt:
        """Consume a durably buffered frame and return a non-promoting receipt.

        Decode failures are intentionally represented as a visible L0 state
        instead of raising after persistence: rejecting an already accepted
        sequence would strand the Android sender between protocol and buffer
        cursors.  Structural validation belongs in :meth:`validate` before
        ``MediaSecurityAuthority`` commits that sequence.
        """

        frame = self.validate(accepted)
        header = accepted.header
        self._assert_buffer_binding(header, buffered)
        with self._lock:
            replay_key = self._replay_key(header, frame)
            completed = self._completed_replays.get(replay_key)
            if completed is not None:
                # A new ECDH session may resend one frame after the PC
                # persisted it but its HTTPS response was lost.  Do not turn
                # that transport replay into a PTS gap or a second decode.
                self._append_receipt(header, frame, completed)
                return completed
            # Security rekeying is expected during one long-running
            # MediaProjection session.  Continuity and decoder references must
            # therefore follow the capture/consent identity, never the
            # short-lived ECDH session identifier.
            key = (self._capture_decoder_key(header), header.capture_epoch, frame.track)
            previous_end = self._last_track_end_us.get(key)
            if previous_end is not None and frame.pts_us != previous_end:
                self._last_track_end_us.pop(key, None)
                # A selected-app gate or transport hole makes reference-frame
                # decoder state unsafe.  The next video AU receives a new
                # in-memory decoder identity and the real H.264 decoder will
                # wait for a fresh IDR instead of decoding across that hole.
                if frame.track is EncodedMediaTrack.VIDEO:
                    self._decoder_generation[key] = self._decoder_generation.get(key, 0) + 1
                    self._video_requires_key_frame[key] = True
                    capture_key = (self._capture_decoder_key(header), header.capture_epoch)
                    self._continuity_generation[capture_key] = self._continuity_generation.get(capture_key, 0) + 1
                receipt = V2L0ProcessingReceipt(
                    "VIDEO_GAP_QUARANTINED_L0" if frame.track is EncodedMediaTrack.VIDEO else "AUDIO_GAP_UNRESOLVED_L0",
                    None,
                    header.sequence,
                    header.media_sha256,
                    None,
                )
                self._append_receipt(header, frame, receipt)
                return receipt
            if frame.track is EncodedMediaTrack.AUDIO:
                self._last_track_end_us[key] = frame.pts_us + frame.duration_us
                receipt = V2L0ProcessingReceipt(
                    "AUDIO_UNRESOLVED_L0", None, header.sequence, header.media_sha256, None
                )
                self._append_receipt(header, frame, receipt)
                return receipt
            # Require an IDR for the first accepted video access unit as well
            # as after every PTS discontinuity.  A caller-supplied decoder is
            # never permitted to bypass this media-integrity condition.
            # A missing flag has two distinct meanings: first sight of a
            # track (which needs an IDR), or a continuous track whose initial
            # IDR was already decoded (which must retain decoder references).
            # ``previous_end`` distinguishes those cases across ECDH rekeys.
            if self._video_requires_key_frame.get(key, previous_end is None) and not frame.is_key_frame:
                receipt = V2L0ProcessingReceipt(
                    "WAITING_KEYFRAME_L0", None, header.sequence, header.media_sha256, None
                )
                self._append_receipt(header, frame, receipt)
                return receipt
            receipt = self._process_video(header, frame)
            if receipt.state == "DECODED_L0":
                self._last_track_end_us[key] = frame.pts_us + frame.duration_us
                if frame.is_key_frame:
                    self._video_requires_key_frame.pop(key, None)
                self._remember_completed(replay_key, receipt)
            return receipt

    def _process_video(self, header: MediaFragmentHeader, frame: EncodedMediaFrame) -> V2L0ProcessingReceipt:
        track_key = (self._capture_decoder_key(header), header.capture_epoch, frame.track)
        decoder_generation = self._decoder_generation.get(track_key, 0)
        decoder_session = f"{track_key[0]}:{header.capture_epoch}:{decoder_generation}"
        try:
            decoded_fingerprint = self._video_decoder(decoder_session, frame.payload, frame.is_key_frame)
        except V2L0MediaProcessorError as error:
            state = "WAITING_KEYFRAME_L0" if str(error) == "v2_l0_decoder_waiting_for_keyframe" else "VIDEO_DECODE_FAILED_L0"
            receipt = V2L0ProcessingReceipt(state, None, header.sequence, header.media_sha256, None)
            self._append_receipt(header, frame, receipt)
            return receipt
        except Exception:
            receipt = V2L0ProcessingReceipt("VIDEO_DECODE_FAILED_L0", None, header.sequence, header.media_sha256, None)
            self._append_receipt(header, frame, receipt)
            return receipt
        decoded_hash = _sha256(decoded_fingerprint)
        capture_key = (self._capture_decoder_key(header), header.capture_epoch)
        continuity_generation = self._continuity_generation.get(capture_key, 0)
        episode_id = (
            f"v2-capture:{header.capture_session_id}:epoch:{header.capture_epoch}:"
            f"continuity:{continuity_generation}"
        )
        content_hash = _sha256(
            json.dumps(
                {
                    "capture_consent_id": header.capture_consent_id,
                    "capture_epoch": header.capture_epoch,
                    "capture_session_id": header.capture_session_id,
                    "consent_generation": header.consent_generation,
                    "continuity_generation": continuity_generation,
                    "decoded_evidence_hash": decoded_hash,
                    "media_hash": header.media_sha256,
                    "pts_end_us": header.pts_end_us,
                    "pts_start_us": header.pts_start_us,
                    "sequence": header.sequence,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        fact_id = f"v2-l0:{content_hash}"
        fact = RealtimeSemanticFact(
            fact_id=fact_id,
            # A lost HTTP response can cause Android to open a new ECDH
            # session and resend the same capture frame.  Security-session
            # identity proves transport isolation, not a new learner event;
            # keep semantic idempotency stable across that rekey/retry.
            idempotency_key=(
                f"v2-media-frame:{header.capture_session_id}:{header.capture_consent_id}:"
                f"{header.consent_generation}:{header.capture_epoch}:{continuity_generation}:{header.pts_start_us}:"
                f"{header.pts_end_us}:{header.media_sha256}"
            ),
            learner_id=header.learner_id,
            session_id=header.capture_session_id,
            episode_id=episode_id,
            capture_consent_id=header.capture_consent_id,
            consent_generation=header.consent_generation,
            source_kind=SourceKind.PHONE_SCREEN,
            start_pts_ns=header.pts_start_us * 1_000,
            end_pts_ns=header.pts_end_us * 1_000,
            fact_kind="V2_H264_DECODED_VIDEO_FRAME_L0",
            content_hash=content_hash,
            evidence_hashes=(header.media_sha256, decoded_hash),
            semantic_policy_version=_POLICY_VERSION,
            provenance_hash=_PROVENANCE_HASH,
        )
        try:
            with RealtimeSemanticLedger(self._semantic_ledger_path) as ledger:
                ledger.append_fact(fact)
        except Exception:
            receipt = V2L0ProcessingReceipt("L0_LEDGER_FAILED", None, header.sequence, header.media_sha256, decoded_hash)
            self._append_receipt(header, frame, receipt)
            return receipt
        receipt = V2L0ProcessingReceipt("DECODED_L0", fact_id, header.sequence, header.media_sha256, decoded_hash)
        self._append_receipt(header, frame, receipt)
        return receipt

    @staticmethod
    def _assert_buffer_binding(header: MediaFragmentHeader, buffered: PcBufferedFragment) -> None:
        if (
            buffered.sequence != header.sequence
            or buffered.start_pts_ns != header.pts_start_us * 1_000
            or buffered.end_pts_ns != header.pts_end_us * 1_000
            or buffered.media_hash != header.media_sha256
        ):
            raise V2L0MediaProcessorError("v2_l0_buffer_binding_mismatch")

    @staticmethod
    def _capture_decoder_key(header: MediaFragmentHeader) -> str:
        return f"{header.capture_session_id}:{header.capture_consent_id}:{header.consent_generation}"

    @classmethod
    def _replay_key(
        cls, header: MediaFragmentHeader, frame: EncodedMediaFrame
    ) -> tuple[str, int, EncodedMediaTrack, int, int, str]:
        return (
            cls._capture_decoder_key(header),
            header.capture_epoch,
            frame.track,
            frame.pts_us,
            frame.pts_us + frame.duration_us,
            header.media_sha256,
        )

    def _remember_completed(
        self,
        replay_key: tuple[str, int, EncodedMediaTrack, int, int, str],
        receipt: V2L0ProcessingReceipt,
    ) -> None:
        if replay_key in self._completed_replays:
            return
        self._completed_replays[replay_key] = receipt
        self._completed_replay_order.append(replay_key)
        while len(self._completed_replay_order) > _REPLAY_CACHE_LIMIT:
            self._completed_replays.pop(self._completed_replay_order.popleft(), None)

    def _append_receipt(
        self, header: MediaFragmentHeader, frame: EncodedMediaFrame, receipt: V2L0ProcessingReceipt
    ) -> None:
        """Persist only hashes, identity and outcome; never clear media bytes."""

        payload = {
            "event_type": "V2L0MediaProcessed",
            "media_security_session_id": header.media_security_session_id,
            "capture_epoch": header.capture_epoch,
            "sequence": header.sequence,
            "track": frame.track.name,
            "start_pts_us": frame.pts_us,
            "end_pts_us": frame.pts_us + frame.duration_us,
            "media_hash": receipt.media_hash,
            "decoded_evidence_hash": receipt.decoded_evidence_hash,
            "state": receipt.state,
            "fact_id": receipt.fact_id,
            "observed_elapsed_ns": self._now_elapsed_ns(),
        }
        with self._receipts_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def record_queue_pressure(self, header: MediaFragmentHeader, frame: EncodedMediaFrame) -> V2L0ProcessingReceipt:
        """Record an explicit L0-only drop without retaining clear media bytes.

        The authenticated ciphertext is already durable in ``PcMediaBuffer``.
        This is intentionally an L0 observability outcome rather than a
        media-ingress rejection: slowing or dropping the optional decoder may
        never make the phone abandon its durable encrypted delivery path.
        """

        receipt = V2L0ProcessingReceipt(
            "L0_QUEUE_DROPPED_BACKPRESSURE", None, header.sequence, header.media_sha256, None
        )
        self._append_receipt(header, frame, receipt)
        return receipt


class V2L0ProcessingDispatcher:
    """Bounded-cleartext, ordered background dispatcher for PC L0 processing.

    The HTTP handler has already authenticated and fsync'ed each encrypted
    fragment before it calls :meth:`submit`.  Raw encoded bytes are retained
    only up to ``max_pending_media_bytes``.  Once that bound is reached, a
    compact metadata-only pressure record stays in order behind prior work;
    it cannot delay a capture receipt or retain more clear media in memory.
    """

    def __init__(self, processor: V2L0MediaProcessor, *, max_pending_media_bytes: int = 32 * 1024 * 1024) -> None:
        if max_pending_media_bytes <= 0:
            raise ValueError("v2_l0_pending_media_limit_invalid")
        self._processor = processor
        self._max_pending_media_bytes = max_pending_media_bytes
        self._work: queue.SimpleQueue[_QueuedL0Work | _QueuePressureWork | None] = queue.SimpleQueue()
        self._condition = threading.Condition()
        self._pending_media_bytes = 0
        self._outstanding_work = 0
        self._completed_sequences: list[int] = []
        self._closed = False
        self._worker = threading.Thread(target=self._run, name="zhixing-v2-l0", daemon=True)
        self._worker.start()

    def submit(self, accepted: AcceptedMediaFragment, buffered: PcBufferedFragment) -> V2L0DispatchReceipt:
        """Queue post-buffer L0 work without waiting for decode or its ledger."""

        plaintext_bytes = len(accepted.plaintext)
        with self._condition:
            if self._closed:
                raise RuntimeError("v2_l0_dispatcher_closed")
            self._outstanding_work += 1
            if self._pending_media_bytes + plaintext_bytes <= self._max_pending_media_bytes:
                self._pending_media_bytes += plaintext_bytes
                self._work.put(_QueuedL0Work(accepted, buffered, plaintext_bytes))
                return V2L0DispatchReceipt("QUEUED_L0", accepted.header.sequence, accepted.header.media_sha256)

        # Parse only the authenticated inner header and discard its payload.
        # This slow-path executes only after the ciphertext is safely sealed;
        # the pressure record is then written by the same ordered worker.
        frame = self._processor.validate(accepted)
        self._work.put(_QueuePressureWork(accepted.header, frame))
        return V2L0DispatchReceipt("L0_QUEUE_DROPPED_BACKPRESSURE", accepted.header.sequence, accepted.header.media_sha256)

    def drain(self, *, timeout: float) -> bool:
        """Wait for the currently admitted L0 work; used only by tests/tools."""

        deadline = time.monotonic() + timeout
        with self._condition:
            while self._outstanding_work:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def completed_sequences(self) -> tuple[int, ...]:
        with self._condition:
            return tuple(self._completed_sequences)

    def close(self, *, timeout: float = 2.0) -> None:
        with self._condition:
            if self._closed:
                return
            self._closed = True
        self._work.put(None)
        self._worker.join(timeout)

    def _run(self) -> None:
        while True:
            work = self._work.get()
            if work is None:
                return
            try:
                if isinstance(work, _QueuedL0Work):
                    self._processor.process(work.accepted, work.buffered)
                else:
                    self._processor.record_queue_pressure(work.header, work.frame)
            finally:
                with self._condition:
                    if isinstance(work, _QueuedL0Work):
                        self._pending_media_bytes -= work.plaintext_bytes
                    self._completed_sequences.append(
                        work.accepted.header.sequence if isinstance(work, _QueuedL0Work) else work.header.sequence
                    )
                    self._outstanding_work -= 1
                    self._condition.notify_all()
