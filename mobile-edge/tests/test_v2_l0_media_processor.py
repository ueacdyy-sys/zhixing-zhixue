from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from threading import Event
from time import monotonic

import pytest

from scripts.realtime_runtime.encoded_media_frame import (
    EncodedMediaFrame,
    EncodedMediaTrack,
    encode_encoded_media_frame,
)
from scripts.realtime_runtime.media_buffer import PcBufferedFragment
from scripts.realtime_runtime.media_security import AcceptedMediaFragment, MediaFragmentHeader
from scripts.realtime_runtime.semantic_ledger import RealtimeSemanticLedger
from scripts.realtime_runtime.v2_l0_media_processor import (
    V2L0MediaProcessor,
    V2L0MediaProcessorError,
    V2L0ProcessingDispatcher,
)


def _accepted(
    *,
    sequence: int = 0,
    start_us: int = 10_000,
    duration_us: int = 2_000,
    track: EncodedMediaTrack = EncodedMediaTrack.VIDEO,
    is_key_frame: bool = True,
) -> AcceptedMediaFragment:
    payload = encode_encoded_media_frame(
        EncodedMediaFrame(track, start_us, duration_us, is_key_frame, b"annex-b-frame")
    )
    return AcceptedMediaFragment(
        header=MediaFragmentHeader(
            media_security_session_id="media-session-1",
            learner_id="learner-1",
            capture_session_id="capture-1",
            capture_consent_id="consent-1",
            consent_generation=1,
            route_lease_id="route-1",
            route_epoch=1,
            capture_epoch=2,
            sequence=sequence,
            pts_start_us=start_us,
            pts_end_us=start_us + duration_us,
            media_sha256=hashlib.sha256(payload).hexdigest(),
        ),
        plaintext=payload,
    )


def _buffered(accepted: AcceptedMediaFragment) -> PcBufferedFragment:
    return PcBufferedFragment(
        fragment_id=f"fragment-{accepted.header.sequence}",
        sequence=accepted.header.sequence,
        start_pts_ns=accepted.header.pts_start_us * 1_000,
        end_pts_ns=accepted.header.pts_end_us * 1_000,
        media_hash=accepted.header.media_sha256,
        local_storage_hash="a" * 64,
        outbox_id="outbox-1",
        replay_idempotency_key="replay-1",
    )


def test_verified_video_is_decoded_and_recorded_as_l0_only(tmp_path: Path) -> None:
    calls: list[tuple[str, bytes, bool]] = []

    def decoder(session_key: str, payload: bytes, is_key_frame: bool) -> bytes:
        calls.append((session_key, payload, is_key_frame))
        return b"decoded-pixel-fingerprint"

    accepted = _accepted()
    processor = V2L0MediaProcessor(
        root=tmp_path / "private-v2-l0",
        semantic_ledger_path=tmp_path / "semantic.sqlite3",
        video_decoder=decoder,
        now_elapsed_ns=lambda: 123,
    )

    receipt = processor.process(accepted, _buffered(accepted))

    assert receipt.state == "DECODED_L0"
    assert receipt.fact_id
    assert calls == [("capture-1:consent-1:1:2:0", b"annex-b-frame", True)]
    with RealtimeSemanticLedger(tmp_path / "semantic.sqlite3") as ledger:
        assert ledger.contiguous_watermark(
            episode_id="v2-capture:capture-1:epoch:2:continuity:0", continuity_start_pts_ns=10_000_000
        ) == 12_000_000
    assert not list((tmp_path / "private-v2-l0").rglob("*.h264"))
    assert b"annex-b-frame" not in (tmp_path / "private-v2-l0" / "v2_l0_receipts.jsonl").read_bytes()


def test_audio_is_kept_as_l0_unresolved_and_never_decoded_as_video(tmp_path: Path) -> None:
    accepted = _accepted(track=EncodedMediaTrack.AUDIO)
    processor = V2L0MediaProcessor(
        root=tmp_path / "private-v2-l0",
        semantic_ledger_path=tmp_path / "semantic.sqlite3",
        video_decoder=lambda *_: pytest.fail("audio must not enter video decoder"),
    )

    receipt = processor.process(accepted, _buffered(accepted))

    assert receipt.state == "AUDIO_UNRESOLVED_L0"
    assert receipt.fact_id is None


def test_security_rekey_preserves_capture_decoder_and_pts_continuity(tmp_path: Path) -> None:
    calls: list[tuple[str, bool]] = []
    first = _accepted(sequence=0, start_us=10_000, is_key_frame=True)
    second_base = _accepted(sequence=0, start_us=12_000, is_key_frame=False)
    second = replace(
        second_base,
        header=replace(second_base.header, media_security_session_id="media-session-2"),
    )
    processor = V2L0MediaProcessor(
        root=tmp_path / "private-v2-l0",
        semantic_ledger_path=tmp_path / "semantic.sqlite3",
        video_decoder=lambda key, _payload, is_key: calls.append((key, is_key)) or b"decoded",
    )

    assert processor.process(first, _buffered(first)).state == "DECODED_L0"
    assert processor.process(second, _buffered(second)).state == "DECODED_L0"
    assert calls == [
        ("capture-1:consent-1:1:2:0", True),
        ("capture-1:consent-1:1:2:0", False),
    ]


def test_retried_frame_in_a_new_security_session_keeps_the_same_l0_fact_identity(tmp_path: Path) -> None:
    first = _accepted(sequence=0, start_us=10_000, is_key_frame=True)
    retry = replace(first, header=replace(first.header, media_security_session_id="media-session-2"))
    processor = V2L0MediaProcessor(
        root=tmp_path / "private-v2-l0",
        semantic_ledger_path=tmp_path / "semantic.sqlite3",
        video_decoder=lambda *_: b"decoded",
    )

    first_receipt = processor.process(first, _buffered(first))
    retry_receipt = processor.process(retry, _buffered(retry))

    assert first_receipt.fact_id == retry_receipt.fact_id


def test_intentional_pts_gap_requires_a_new_key_frame_before_a_new_decoder_context(tmp_path: Path) -> None:
    calls: list[tuple[str, bool]] = []
    first = _accepted(start_us=10_000, is_key_frame=True)
    gap = _accepted(sequence=1, start_us=13_000, is_key_frame=False)
    resumed = _accepted(sequence=2, start_us=15_000, is_key_frame=False)
    recovery_key_frame = _accepted(sequence=3, start_us=17_000, is_key_frame=True)
    processor = V2L0MediaProcessor(
        root=tmp_path / "private-v2-l0",
        semantic_ledger_path=tmp_path / "semantic.sqlite3",
        video_decoder=lambda key, _payload, is_key: calls.append((key, is_key)) or b"decoded",
    )

    assert processor.process(first, _buffered(first)).state == "DECODED_L0"
    assert processor.process(gap, _buffered(gap)).state == "VIDEO_GAP_QUARANTINED_L0"
    assert processor.process(resumed, _buffered(resumed)).state == "WAITING_KEYFRAME_L0"
    assert processor.process(recovery_key_frame, _buffered(recovery_key_frame)).state == "DECODED_L0"
    assert calls == [
        ("capture-1:consent-1:1:2:0", True),
        ("capture-1:consent-1:1:2:1", True),
    ]


def test_header_pts_must_match_the_authenticated_encoded_frame_before_buffered_l0_processing(tmp_path: Path) -> None:
    accepted = _accepted()
    mismatched = replace(accepted, header=replace(accepted.header, pts_end_us=12_001))
    processor = V2L0MediaProcessor(
        root=tmp_path / "private-v2-l0", semantic_ledger_path=tmp_path / "semantic.sqlite3"
    )

    with pytest.raises(V2L0MediaProcessorError, match="v2_l0_frame_header_pts_mismatch"):
        processor.validate(mismatched)


def test_video_decode_failure_is_a_visible_l0_failure_without_a_semantic_fact(tmp_path: Path) -> None:
    accepted = _accepted()
    processor = V2L0MediaProcessor(
        root=tmp_path / "private-v2-l0",
        semantic_ledger_path=tmp_path / "semantic.sqlite3",
        video_decoder=lambda *_: (_ for _ in ()).throw(ValueError("bad-annex-b")),
    )

    receipt = processor.process(accepted, _buffered(accepted))

    assert receipt.state == "VIDEO_DECODE_FAILED_L0"
    assert receipt.fact_id is None


def test_durable_v2_ingress_is_acknowledged_while_l0_decoder_is_still_busy(tmp_path: Path) -> None:
    """The encrypted-buffer receipt must never wait for one slow L0 decode."""

    decoder_started = Event()
    allow_decoder = Event()
    decoded_sequences: list[int] = []

    def blocking_decoder(_session_key: str, _payload: bytes, _is_key_frame: bool) -> bytes:
        decoder_started.set()
        assert allow_decoder.wait(timeout=2)
        return b"decoded"

    processor = V2L0MediaProcessor(
        root=tmp_path / "private-v2-l0",
        semantic_ledger_path=tmp_path / "semantic.sqlite3",
        video_decoder=blocking_decoder,
    )
    dispatcher = V2L0ProcessingDispatcher(processor, max_pending_media_bytes=64 * 1024)
    first = _accepted(sequence=0, start_us=10_000)
    second = _accepted(sequence=1, start_us=12_000)
    try:
        assert dispatcher.submit(first, _buffered(first)).state == "QUEUED_L0"
        assert decoder_started.wait(timeout=1)

        started_at = monotonic()
        second_receipt = dispatcher.submit(second, _buffered(second))
        assert monotonic() - started_at < 0.1
        assert second_receipt.state == "QUEUED_L0"

        allow_decoder.set()
        assert dispatcher.drain(timeout=2)
        decoded_sequences.extend(dispatcher.completed_sequences())
    finally:
        allow_decoder.set()
        dispatcher.close(timeout=2)

    assert decoded_sequences == [0, 1]


def test_l0_pressure_drops_only_optional_decode_and_keeps_an_audit_record(tmp_path: Path) -> None:
    decoder_started = Event()
    allow_decoder = Event()

    def blocking_decoder(_session_key: str, _payload: bytes, _is_key_frame: bool) -> bytes:
        decoder_started.set()
        assert allow_decoder.wait(timeout=2)
        return b"decoded"

    first = _accepted(sequence=0, start_us=10_000)
    second = _accepted(sequence=1, start_us=12_000)
    processor = V2L0MediaProcessor(
        root=tmp_path / "private-v2-l0",
        semantic_ledger_path=tmp_path / "semantic.sqlite3",
        video_decoder=blocking_decoder,
    )
    dispatcher = V2L0ProcessingDispatcher(processor, max_pending_media_bytes=len(first.plaintext))
    try:
        assert dispatcher.submit(first, _buffered(first)).state == "QUEUED_L0"
        assert decoder_started.wait(timeout=1)
        assert dispatcher.submit(second, _buffered(second)).state == "L0_QUEUE_DROPPED_BACKPRESSURE"
        allow_decoder.set()
        assert dispatcher.drain(timeout=2)
    finally:
        allow_decoder.set()
        dispatcher.close(timeout=2)

    records = [
        line for line in (tmp_path / "private-v2-l0" / "v2_l0_receipts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert '"state":"L0_QUEUE_DROPPED_BACKPRESSURE"' in records[-1]
    assert b"annex-b-frame" not in (tmp_path / "private-v2-l0" / "v2_l0_receipts.jsonl").read_bytes()
