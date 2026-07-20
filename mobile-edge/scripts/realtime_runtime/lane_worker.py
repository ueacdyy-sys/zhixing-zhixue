"""Persistent, lease-backed workers for the three sealed-media lanes.

Workers never open RTSP.  Each consumes only the immutable media URIs returned
by ``SealedWindowLedger.window_descriptor`` and writes a self-describing
artifact before the ledger accepts completion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import msvcrt
import os
import subprocess
import tempfile
import time
import wave
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .contracts import JobLease, Lane, LaneEvidence, QualityStatus, WindowDescriptor
from .ledger import SealedWindowLedger
from .window_media import build_window_media


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _resolve_media_uri(uri: str, capture_root: Path) -> Path:
    prefix = "local://capture/"
    if not uri.startswith(prefix):
        raise ValueError("unsupported_media_uri")
    path = (capture_root / Path(uri[len(prefix) :])).resolve()
    if capture_root.resolve() not in path.parents or not path.is_file():
        raise ValueError("media_uri_outside_capture_root")
    return path


def _run_ffmpeg(arguments: list[str], *, failure_code: str) -> None:
    completed = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{failure_code}:{(completed.stderr or completed.stdout).strip()[-300:]}")


@contextmanager
def exclusive_slot(lock_path: Path) -> Any:
    """Use an advisory Windows byte lock for a shared, bounded resource."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        while True:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.025)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _normalize_fragment(fragment: Path) -> Path:
    normalized = fragment.with_suffix(".normalized.mp4")
    with exclusive_slot(normalized.with_suffix(normalized.suffix + ".lock")):
        if normalized.is_file() and normalized.stat().st_size > 0:
            return normalized
        partial = normalized.with_name(f"{normalized.stem}.{os.getpid()}.partial{normalized.suffix}")
        _run_ffmpeg(
            ["-fflags", "+genpts", "-i", str(fragment), "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-movflags", "+faststart", str(partial)],
            failure_code="fragment_normalize_failed",
        )
        if not partial.is_file() or partial.stat().st_size <= 0:
            raise RuntimeError("fragment_normalize_missing")
        os.replace(partial, normalized)
        return normalized


def materialize_window(descriptor: WindowDescriptor, *, capture_root: Path, cache_root: Path) -> Path:
    fragments = tuple(_normalize_fragment(_resolve_media_uri(uri, capture_root)) for uri in descriptor.media_uris)
    output = cache_root / f"{_safe_name(descriptor.window_id)}.mp4"
    with exclusive_slot(output.with_suffix(output.suffix + ".lock")):
        if output.is_file() and output.stat().st_size > 0:
            return output
        return build_window_media(fragments, output_path=output).path


class LaneExecutor:
    def __init__(self, lane: Lane, *, model_dir: Path) -> None:
        self._lane = lane
        self._model_dir = model_dir
        self._engine: Any | None = None

    def warm(self, artifact_root: Path) -> None:
        artifact_root.mkdir(parents=True, exist_ok=True)
        if self._lane is Lane.ASR:
            from .asr_lane import PersistentWhisperLane

            self._engine = PersistentWhisperLane()
            self._engine._load()
            self._prime_asr(artifact_root)
        elif self._lane is Lane.VLM:
            from .full_video_vlm import SmolVlmFullVideoLane

            self._engine = SmolVlmFullVideoLane(self._model_dir)
            self._engine._load()
            self._prime_vlm(artifact_root)
        else:
            from rapidocr_onnxruntime import RapidOCR

            # RapidOCR creates three ONNX Runtime sessions (detect, classify
            # and recognise).  Its automatic thread pool uses the whole host
            # for each session, which starves the concurrent ASR and VLM
            # lanes on the live path.  Reserve a bounded CPU share for this
            # one worker instead of weakening OCR sampling or serialising the
            # modalities.
            self._engine = RapidOCR(intra_op_num_threads=6, inter_op_num_threads=1)
            self._prime_ocr()

    def _prime_asr(self, artifact_root: Path) -> None:
        """Execute one synthetic inference before RTSP ingress opens."""

        assert self._engine is not None
        with tempfile.TemporaryDirectory(dir=artifact_root, prefix=".asr-warm-") as directory:
            silence = Path(directory) / "silence.wav"
            with wave.open(str(silence), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16_000)
                output.writeframes(b"\x00\x00" * 16_000)
            self._engine.transcribe(silence)

    def _prime_vlm(self, artifact_root: Path) -> None:
        """Warm decoding and generation without consuming user media."""

        assert self._engine is not None
        from .full_video_vlm import FullVideoVlmJob

        with tempfile.TemporaryDirectory(dir=artifact_root, prefix=".vlm-warm-") as directory:
            root = Path(directory)
            video = root / "probe.mp4"
            _run_ffmpeg(
                ["-f", "lavfi", "-i", "color=c=black:s=64x64:r=1:d=1", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                failure_code="vlm_warmup_media_failed",
            )
            self._engine.analyze(FullVideoVlmJob("runtime-warmup", video, 0, 1_000_000_000, root))

    def _prime_ocr(self) -> None:
        """Exercise both text detection and recognition before user media arrives."""

        assert self._engine is not None
        import cv2
        import numpy as np

        image = np.full((540, 960, 3), 255, dtype=np.uint8)
        cv2.putText(image, "Warmup 123", (80, 270), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 5, cv2.LINE_AA)
        self._engine(image)

    def analyze(self, descriptor: WindowDescriptor, media: Path, artifact_root: Path) -> Path:
        if self._engine is None:
            self.warm(artifact_root)
        started_ns = time.monotonic_ns()
        name = _safe_name(descriptor.window_id)
        artifact_root.mkdir(parents=True, exist_ok=True)
        if self._lane is Lane.ASR:
            wav_path = artifact_root / f"{name}.wav"
            _run_ffmpeg(["-i", str(media), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path)], failure_code="audio_extract_failed")
            # The validated RTX 2080 Ti profile has enough headroom for the
            # resident tiny-Whisper and SmolVLM workers concurrently.  A
            # process-global CUDA lock made the declared ASR/VLM lanes
            # serial, inflating every fused-window latency by the other
            # lane's work.  Each worker remains single-threaded and durable;
            # CUDA schedules their kernels independently.
            payload: dict[str, Any] = {"segments": self._engine.transcribe(wav_path)}
        elif self._lane is Lane.VLM:
            from .full_video_vlm import FullVideoVlmJob

            model_artifact = self._engine.analyze(
                FullVideoVlmJob(descriptor.window_id, media, descriptor.start_pts_ns, descriptor.end_pts_ns, artifact_root)
            )
            payload = json.loads(model_artifact.read_text(encoding="utf-8"))
        else:
            import cv2

            capture = cv2.VideoCapture(str(media))
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            # OCR is a text lane, not a substitute for video understanding.
            # One representative midpoint prevents three full-frame OCR passes
            # from consuming the complete 6 s scheduling budget; the VLM still
            # receives the whole sealed MP4 in parallel.
            index = max(0, frame_count // 2)
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            samples: list[dict[str, Any]] = []
            if ok:
                result, _ = self._engine(frame)
                samples.append({"frame_index": index, "raw": result or []})
            capture.release()
            payload = {"samples": samples, "sampling": "midpoint_text_observation_of_complete_window"}
        completed_ns = time.monotonic_ns()
        final = artifact_root / f"{name}.{self._lane.value.lower()}.json"
        document = {
            "schema_version": "sealed_window_lane_artifact.v1",
            "classification": "CANDIDATE_ONLY",
            "lane": self._lane.value,
            "window_id": descriptor.window_id,
            "coverage_start_pts_ns": descriptor.start_pts_ns,
            "coverage_end_pts_ns": descriptor.end_pts_ns,
            "source_fragment_hashes": list(descriptor.fragment_hashes),
            "input_media_sha256": _sha256(media),
            "started_monotonic_ns": started_ns,
            "completed_monotonic_ns": completed_ns,
            "result": payload,
        }
        partial = final.with_suffix(final.suffix + ".partial")
        partial.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(partial, final)
        return final


def _evidence_from_artifact(lease: JobLease, descriptor: WindowDescriptor, artifact: Path) -> LaneEvidence:
    document = json.loads(artifact.read_text(encoding="utf-8"))
    if (
        document.get("lane") != lease.lane.value
        or document.get("window_id") != lease.window_id
        or document.get("coverage_start_pts_ns") != descriptor.start_pts_ns
        or document.get("coverage_end_pts_ns") != descriptor.end_pts_ns
        or tuple(document.get("source_fragment_hashes", ())) != descriptor.fragment_hashes
    ):
        raise ValueError("artifact_contract_mismatch")
    return LaneEvidence(
        window_id=lease.window_id,
        lane=lease.lane,
        coverage_start_pts_ns=descriptor.start_pts_ns,
        coverage_end_pts_ns=descriptor.end_pts_ns,
        source_fragment_hashes=descriptor.fragment_hashes,
        quality_status=QualityStatus.FUSION_ELIGIBLE,
        artifact_uri=f"local://artifact/{artifact.name}",
        artifact_sha256=_sha256(artifact),
        started_ns=int(document["started_monotonic_ns"]),
        completed_ns=int(document["completed_monotonic_ns"]),
    )


def _record_candidate_projection_error(artifact_root: Path, error: Exception) -> None:
    """Keep a visible projection failure without rewriting completed media evidence."""

    output = artifact_root / "candidate_card_projection_errors.jsonl"
    with exclusive_slot(output.with_suffix(output.suffix + ".lock")):
        with output.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {
                        "event_type": "CandidateCardProjectionFailed",
                        "pc_monotonic_ns": time.monotonic_ns(),
                        "error_type": type(error).__name__,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )


def run_worker(
    *, lane: Lane, ledger_path: Path, capture_root: Path, artifact_root: Path, model_dir: Path, worker_id: str, max_idle_seconds: float = 0.0
) -> int:
    executor = LaneExecutor(lane, model_dir=model_dir)
    executor.warm(artifact_root)
    ready = artifact_root / f"{worker_id}.ready.json"
    ready.parent.mkdir(parents=True, exist_ok=True)
    ready.write_text(json.dumps({"worker_id": worker_id, "lane": lane.value, "ready_ns": time.monotonic_ns()}), encoding="utf-8")
    idle_started = time.monotonic()
    with SealedWindowLedger(ledger_path) as ledger:
        while True:
            now_ns = time.monotonic_ns()
            ledger.recover_expired_leases(now_ns=now_ns)
            lease = ledger.claim(lane, worker_id, now_ns=now_ns, lease_ns=90_000_000_000)
            if lease is None:
                if max_idle_seconds and time.monotonic() - idle_started >= max_idle_seconds:
                    return 0
                time.sleep(0.05)
                continue
            idle_started = time.monotonic()
            try:
                descriptor = ledger.window_descriptor(lease.window_id)
                media = materialize_window(descriptor, capture_root=capture_root, cache_root=artifact_root / "windows")
                artifact = executor.analyze(descriptor, media, artifact_root)
                ledger.complete(lease, _evidence_from_artifact(lease, descriptor, artifact))
                fused = ledger.fuse_ready(now_ns=time.monotonic_ns())
                if fused:
                    try:
                        from .candidate_card_projection import project_candidate_cards

                        project_candidate_cards(
                            ledger_path=ledger_path,
                            artifact_root=artifact_root,
                            output_path=artifact_root / "candidate_cards.v1.json",
                        )
                    except Exception as projection_error:
                        _record_candidate_projection_error(artifact_root, projection_error)
            except Exception as error:  # A lane failure must remain a visible terminal/retry state.
                ledger.fail(lease, error_code=type(error).__name__[:80], now_ns=time.monotonic_ns(), retry_delay_ns=1_000_000_000, max_attempts=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=[item.value for item in Lane], required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--capture-root", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--max-idle-seconds", type=float, default=0.0)
    args = parser.parse_args()
    return run_worker(
        lane=Lane(args.lane), ledger_path=Path(args.ledger), capture_root=Path(args.capture_root), artifact_root=Path(args.artifact_root),
        model_dir=Path(args.model_dir), worker_id=args.worker_id, max_idle_seconds=args.max_idle_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
