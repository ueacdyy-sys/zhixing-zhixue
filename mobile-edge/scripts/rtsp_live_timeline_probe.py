from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import socket
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import av
import cv2
import imagehash
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


REGIONS = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "top": (0.0, 0.0, 1.0, 0.28),
    "center": (0.0, 0.20, 1.0, 0.72),
    "subtitle": (0.0, 0.48, 1.0, 0.86),
    "bottom": (0.0, 0.70, 1.0, 1.0),
}


@dataclass
class Sample:
    sample_index: int
    source_frame_index: int
    video_time_s: float | None
    timeline_s: float
    capture_wall_s: float
    process_wall_ms: float
    width: int
    height: int
    full_change: float | None
    top_change: float | None
    center_change: float | None
    subtitle_change: float | None
    bottom_change: float | None
    full_luma: float
    subtitle_luma: float
    phash: str
    phash_hamming: int | None
    evidence_file: str | None


@dataclass
class Segment:
    segment_index: int
    start_s: float
    end_s: float
    sample_count: int
    max_full_change: float | None
    mean_full_change: float | None
    max_subtitle_change: float | None
    mean_luma: float | None
    shift_sample_count: int
    evidence_files: list[str]


def port_open(host: str, port: int, timeout_s: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def positive_finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("value must be a positive finite number")
    return number


def nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative integer")
    return number


def valid_port(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return number


def rtsp_connectivity_endpoint(source: str) -> tuple[str, int]:
    parsed = urlsplit(source)
    if parsed.scheme.lower() != "rtsp" or not parsed.hostname:
        raise ValueError("invalid RTSP source URL")
    return parsed.hostname, parsed.port or 554


def frame_time_seconds(frame: av.VideoFrame) -> float | None:
    if frame.pts is None or frame.time_base is None:
        return None
    return float(frame.pts * frame.time_base)


def crop_region(image: np.ndarray, name: str) -> np.ndarray:
    h, w = image.shape[:2]
    x1p, y1p, x2p, y2p = REGIONS[name]
    x1, y1, x2, y2 = int(w * x1p), int(h * y1p), int(w * x2p), int(h * y2p)
    return image[y1:y2, x1:x2]


def feature_image(image: np.ndarray, region: str, width: int = 96) -> np.ndarray:
    crop = crop_region(image, region)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    scale = width / max(1, w)
    resized = cv2.resize(gray, (width, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
    return resized.astype(np.float32)


def mean_abs_change(prev: np.ndarray | None, curr: np.ndarray) -> float | None:
    if prev is None:
        return None
    if prev.shape != curr.shape:
        curr = cv2.resize(curr, (prev.shape[1], prev.shape[0]), interpolation=cv2.INTER_AREA)
    return float(np.mean(np.abs(curr - prev)))


def phash_for_bgr(image: np.ndarray) -> imagehash.ImageHash:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return imagehash.phash(Image.fromarray(rgb))


def save_evidence_frame(image: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise RuntimeError(f"failed to write evidence frame: {path}")


def prewarm_visual_pipeline(width: int, height: int, iterations: int) -> dict[str, Any]:
    if iterations <= 0:
        return {"iterations": 0, "wall_ms": 0.0}
    width = max(64, int(width or 508))
    height = max(64, int(height or 1088))
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 0] = np.linspace(0, 255, width, dtype=np.uint8)
    image[:, :, 1] = np.linspace(0, 255, height, dtype=np.uint8).reshape(height, 1)
    t0 = time.perf_counter()
    prev_features: dict[str, np.ndarray | None] = {name: None for name in REGIONS}
    prev_hash: imagehash.ImageHash | None = None
    for i in range(iterations):
        rolled = np.roll(image, shift=i * 3, axis=1)
        features = {name: feature_image(rolled, name) for name in REGIONS}
        for name in REGIONS:
            _ = mean_abs_change(prev_features[name], features[name])
        current_hash = phash_for_bgr(rolled)
        if prev_hash is not None:
            _ = int(current_hash - prev_hash)
        prev_features = features
        prev_hash = current_hash
    return {
        "iterations": iterations,
        "width": width,
        "height": height,
        "wall_ms": (time.perf_counter() - t0) * 1000.0,
    }


def finite(values: list[float | None]) -> list[float]:
    return [v for v in values if v is not None and math.isfinite(v)]


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.array(values, dtype=np.float64), pct))


def summarize(values: list[float | None]) -> dict[str, float | None]:
    clean = finite(values)
    if not clean:
        return {"min": None, "p50": None, "p90": None, "p95": None, "max": None, "mean": None}
    arr = np.array(clean, dtype=np.float64)
    return {
        "min": float(np.min(arr)),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
    }


def start_raw_recorder(ffmpeg: str, rtsp_url: str, seconds: float, out_file: Path, log_file: Path) -> subprocess.Popen[str]:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_file.open("w", encoding="utf-8", errors="replace")
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-rtsp_transport",
        "tcp",
        "-t",
        f"{seconds:.3f}",
        "-i",
        rtsp_url,
        "-map",
        "0",
        "-c",
        "copy",
        "-f",
        "matroska",
        str(out_file),
    ]
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    finally:
        if proc is None:
            log_handle.close()
    proc._codex_log_handle = log_handle  # type: ignore[attr-defined]
    return proc


def close_raw_recorder(proc: subprocess.Popen[str] | None, timeout_s: float = 8.0) -> int | None:
    if proc is None:
        return None
    try:
        try:
            return proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                return proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                return proc.wait(timeout=3)
        except (KeyboardInterrupt, SystemExit):
            try:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        proc.wait(timeout=3)
                    except Exception:
                        pass
            finally:
                raise
    finally:
        log_handle = getattr(proc, "_codex_log_handle", None)
        if log_handle is not None:
            log_handle.close()


def ffprobe(ffprobe_bin: str, file: Path) -> dict[str, Any] | None:
    if not file.exists() or file.stat().st_size <= 0:
        return None
    proc = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return {"error": proc.stderr}
    return json.loads(proc.stdout)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("x", encoding="utf-8") as file_handle:
            json.dump(value, file_handle, ensure_ascii=False, indent=2, allow_nan=False)
            file_handle.write("\n")
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("x", encoding="utf-8", newline="\n") as file_handle:
            file_handle.write(text)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n" for value in values)
    atomic_write_text(path, text)


def stable_file_snapshot(path: Path, chunk_size: int = 1024 * 1024) -> dict[str, Any]:
    before = path.stat()
    digest = sha256_file(path, chunk_size=chunk_size)
    after = path.stat()
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise RuntimeError("file_changed_during_hash")
    return {
        "canonical_file": str(path.resolve()),
        "size_bytes": after.st_size,
        "sha256": digest,
        "identity": {
            "device": after.st_dev,
            "inode": after.st_ino,
            "mtime_ns": after.st_mtime_ns,
        },
    }


def snapshots_match(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return all(first.get(key) == second.get(key) for key in ("canonical_file", "size_bytes", "sha256", "identity"))


def create_capture_output_dir(
    captures_root: Path,
    *,
    tag: str,
    stamp: str,
    capture_id: str,
    manifest_id: str,
) -> Path:
    if ".." in tag or not re.fullmatch(r"[A-Za-z0-9._-]+", tag):
        raise ValueError("tag must contain only letters, digits, '.', '_', or '-' and must not contain '..'")
    root = captures_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate = (root / f"{tag}_{stamp}_{capture_id}_{manifest_id}").resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("capture output directory escapes captures root")
    candidate.mkdir(exist_ok=False)
    return candidate


def redact_source(source: str) -> str:
    if not source.lower().startswith("rtsp://"):
        return source
    parsed = urlsplit(source)
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError:
        port = ""
    credentials = "***@" if parsed.username is not None else ""
    return urlunsplit((parsed.scheme, f"{credentials}{host}{port}", parsed.path, parsed.query, parsed.fragment))


def safe_exception(exc: BaseException, source: str) -> str:
    message = repr(exc).replace(source, redact_source(source))
    if source.lower().startswith("rtsp://"):
        parsed = urlsplit(source)
        for secret in (parsed.username, parsed.password):
            if secret:
                message = message.replace(secret, "***")
    return message


def recording_status(ffmpeg_exit_code: int | None, probe_report: dict[str, Any] | None, target_seconds: float) -> dict[str, Any]:
    ffprobe_ok = bool(probe_report) and "error" not in (probe_report or {})
    has_video_stream = any(stream.get("codec_type") == "video" for stream in (probe_report or {}).get("streams", []))
    try:
        duration_s = float((probe_report or {}).get("format", {}).get("duration"))
    except (TypeError, ValueError):
        duration_s = None
    if duration_s is not None and not math.isfinite(duration_s):
        duration_s = None
    required_duration_s = max(0.0, target_seconds * 0.8)
    duration_ok = duration_s is not None and duration_s >= required_duration_s
    return {
        "ffmpeg_exit_code": ffmpeg_exit_code,
        "ffprobe_ok": ffprobe_ok,
        "has_video_stream": has_video_stream,
        "duration_s": duration_s,
        "required_duration_s": required_duration_s,
        "duration_ok": duration_ok,
        "complete": ffmpeg_exit_code == 0 and ffprobe_ok and has_video_stream and duration_ok,
    }


def artifact_record(path: Path, base_dir: Path) -> dict[str, Any]:
    snapshot = stable_file_snapshot(path)
    return {
        "file": str(path.relative_to(base_dir)),
        "size_bytes": snapshot["size_bytes"],
        "sha256": snapshot["sha256"],
    }


def build_capture_manifest(
    *,
    manifest_id: str,
    capture_id: str,
    source: str,
    source_kind: str,
    rtsp_url: str | None,
    raw_recording: dict[str, Any],
    trust_level: str,
    artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_raw_keys = ["canonical_file", "size_bytes", "sha256", "error"]
    if trust_level == "insufficient":
        manifest_raw_keys.extend(["observed_size_bytes", "observed_sha256"])
    manifest_raw = {
        key: raw_recording[key]
        for key in manifest_raw_keys
        if key in raw_recording
    }
    manifest = {
        "schema_version": "1.0",
        "manifest_id": manifest_id,
        "generated_at": datetime.now().astimezone().isoformat(),
        "capture_id": capture_id,
        "source_kind": source_kind,
        "source": source,
        "rtsp_url": rtsp_url,
        "raw_recording": manifest_raw,
        "trust_level": trust_level,
    }
    if artifacts is not None:
        manifest["artifacts"] = artifacts
    return manifest


def build_segments(
    samples: list[Sample],
    segment_s: float,
    shift_threshold: float | None,
    timeline_duration_s: float,
) -> list[Segment]:
    if not samples or timeline_duration_s <= 0:
        return []
    count = int(math.ceil(timeline_duration_s / segment_s))
    segments: list[Segment] = []
    for idx in range(count):
        start = idx * segment_s
        end = min(start + segment_s, timeline_duration_s)
        if idx == count - 1:
            bucket = [s for s in samples if start <= s.timeline_s <= end]
        else:
            bucket = [s for s in samples if start <= s.timeline_s < end]
        if not bucket:
            continue
        changes = finite([s.full_change for s in bucket])
        subtitle_changes = finite([s.subtitle_change for s in bucket])
        lumas = finite([s.full_luma for s in bucket])
        shift_count = 0
        if shift_threshold is not None:
            shift_count = sum(1 for s in bucket if s.full_change is not None and s.full_change >= shift_threshold)
        segments.append(
            Segment(
                segment_index=len(segments) + 1,
                start_s=start,
                end_s=end,
                sample_count=len(bucket),
                max_full_change=max(changes) if changes else None,
                mean_full_change=float(np.mean(changes)) if changes else None,
                max_subtitle_change=max(subtitle_changes) if subtitle_changes else None,
                mean_luma=float(np.mean(lumas)) if lumas else None,
                shift_sample_count=shift_count,
                evidence_files=[s.evidence_file for s in bucket if s.evidence_file],
            )
        )
    return segments


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    raw = report.get("raw_recording") or {}
    perf = report.get("performance") or {}
    lines = [
        "# RTSP Live Timeline Probe",
        "",
        "## Boundary",
        "",
        "- Passive RTSP read only; no tap, no swipe, no ADB control.",
        "- This is a real-time visual-signal timeline, not full semantic video understanding.",
        "- OCR/ASR/VLM must be separate downstream stages with their own latency budget.",
        "",
        "## Summary",
        "",
        f"- capture_id: `{report.get('capture_id')}`",
        f"- source_kind: `{report.get('source_kind')}`",
        f"- source: `{report.get('source')}`",
        f"- rtsp_url: `{report.get('rtsp_url')}`",
        f"- target_seconds: `{report.get('target_seconds')}`",
        f"- timeline_duration_s: `{report.get('timeline_duration_s')}`",
        f"- processing_wall_s: `{report.get('processing_wall_s')}`",
        f"- prewarm: `{report.get('prewarm')}`",
        f"- decoded_frames: `{report.get('decoded_frames')}`",
        f"- sampled_frames: `{report.get('sampled_frames')}`",
        f"- capture_wall_s: `{report.get('capture_wall_s')}`",
        f"- estimated_source_fps: `{report.get('estimated_source_fps')}`",
        f"- sample_interval_s: `{report.get('sample_interval_s')}`",
        f"- segment_s: `{report.get('segment_s')}`",
        f"- trust_level: `{report.get('trust_level')}`",
        f"- manifest_id: `{report.get('manifest_id')}`",
        f"- manifest_file: `{report.get('manifest_file')}`",
        "",
        "## Raw Recording",
        "",
        f"- file: `{raw.get('file')}`",
        f"- size_mb: `{raw.get('size_mb')}`",
        f"- canonical_file: `{raw.get('canonical_file')}`",
        f"- size_bytes: `{raw.get('size_bytes')}`",
        f"- sha256: `{raw.get('sha256')}`",
        f"- error: `{raw.get('error')}`",
        f"- bitrate_mbps: `{raw.get('bitrate_mbps')}`",
        f"- ffmpeg_exit_code: `{raw.get('ffmpeg_exit_code')}`",
        "",
        "## Processing Performance",
        "",
        f"- sample_process_ms_p50: `{perf.get('sample_process_ms', {}).get('p50')}`",
        f"- sample_process_ms_p95: `{perf.get('sample_process_ms', {}).get('p95')}`",
        f"- sample_process_ms_max: `{perf.get('sample_process_ms', {}).get('max')}`",
        "",
        "## Segments",
        "",
    ]
    for seg in report.get("segments", []):
        lines.append(
            f"- segment {seg['segment_index']}: {seg['start_s']:.2f}-{seg['end_s']:.2f}s, "
            f"samples={seg['sample_count']}, max_full_change={seg['max_full_change']}, "
            f"shift_samples={seg['shift_sample_count']}"
        )
    atomic_write_text(path, "\n".join(lines) + "\n")


def analyze_live(
    capture_id: str,
    source: str,
    out_dir: Path,
    seconds: float,
    sample_interval_s: float,
    segment_s: float,
    save_every_sample: bool,
    rtsp_transport: str,
    open_retries: int,
    retry_delay_s: float,
    source_is_live: bool,
    prewarm_iterations: int,
) -> dict[str, Any]:
    options = {"rtsp_transport": rtsp_transport, "stimeout": "5000000"} if source.lower().startswith("rtsp://") else {}
    last_error: Exception | None = None
    container = None
    open_start = time.perf_counter()
    for attempt in range(1, max(1, open_retries) + 1):
        try:
            container = av.open(source, options=options)
            break
        except Exception as exc:
            last_error = exc
            if attempt >= open_retries:
                raise
            time.sleep(retry_delay_s)
    if container is None:
        raise RuntimeError(f"failed to open source: {source}") from last_error
    open_wall_s = time.perf_counter() - open_start

    stream = container.streams.video[0]
    prewarm_report = prewarm_visual_pipeline(
        width=stream.codec_context.width or 508,
        height=stream.codec_context.height or 1088,
        iterations=prewarm_iterations,
    )
    capture_start = time.perf_counter()
    first_video_t: float | None = None
    last_video_t: float | None = None
    next_sample_t = 0.0
    decoded = 0
    prev_features: dict[str, np.ndarray | None] = {name: None for name in REGIONS}
    prev_hash: imagehash.ImageHash | None = None
    samples: list[Sample] = []
    frames_dir = out_dir / "evidence_frames"
    last_error = None
    timeline_deadline_reached = False

    try:
        for packet in container.demux(stream):
            for frame in packet.decode():
                decoded += 1
                now = time.perf_counter()
                wall_t = now - capture_start
                vt = frame_time_seconds(frame)
                if vt is not None:
                    first_video_t = vt if first_video_t is None else min(first_video_t, vt)
                    last_video_t = vt
                rel_video_t = (vt - first_video_t) if vt is not None and first_video_t is not None else wall_t
                timeline_t = wall_t if source_is_live else rel_video_t
                if timeline_t >= seconds:
                    timeline_deadline_reached = True
                    break
                if rel_video_t + 1e-9 < next_sample_t:
                    continue

                sample_start = time.perf_counter()
                image = frame.to_ndarray(format="bgr24")
                h, w = image.shape[:2]
                features = {name: feature_image(image, name) for name in REGIONS}
                changes = {name: mean_abs_change(prev_features[name], features[name]) for name in REGIONS}
                prev_features = features
                current_hash = phash_for_bgr(image)
                hamming = int(current_hash - prev_hash) if prev_hash is not None else None
                prev_hash = current_hash

                evidence_file = None
                if save_every_sample:
                    evidence_name = f"sample_{len(samples) + 1:04d}_src{decoded:05d}.jpg"
                    evidence_file = str(Path("evidence_frames") / evidence_name)
                    save_evidence_frame(image, out_dir / evidence_file)

                process_ms = (time.perf_counter() - sample_start) * 1000.0
                samples.append(
                    Sample(
                        sample_index=len(samples) + 1,
                        source_frame_index=decoded,
                        video_time_s=vt,
                        timeline_s=timeline_t,
                        capture_wall_s=wall_t,
                        process_wall_ms=process_ms,
                        width=w,
                        height=h,
                        full_change=changes["full"],
                        top_change=changes["top"],
                        center_change=changes["center"],
                        subtitle_change=changes["subtitle"],
                        bottom_change=changes["bottom"],
                        full_luma=float(np.mean(features["full"])),
                        subtitle_luma=float(np.mean(features["subtitle"])),
                        phash=str(current_hash),
                        phash_hamming=hamming,
                        evidence_file=evidence_file,
                    )
                )
                while next_sample_t <= rel_video_t + 1e-9:
                    next_sample_t += sample_interval_s
            if timeline_deadline_reached:
                break
    except Exception as exc:
        last_error = exc
    finally:
        container.close()

    capture_wall_s = time.perf_counter() - capture_start
    if last_error is not None:
        raise last_error

    full_values = finite([s.full_change for s in samples])
    shift_threshold = percentile(full_values, 90)
    timeline_duration_s = max([s.timeline_s for s in samples], default=0.0)
    segments = build_segments(
        samples,
        segment_s=segment_s,
        shift_threshold=shift_threshold,
        timeline_duration_s=timeline_duration_s,
    )
    video_duration_s = None
    if first_video_t is not None and last_video_t is not None and last_video_t >= first_video_t:
        video_duration_s = last_video_t - first_video_t

    report: dict[str, Any] = {
        "capture_id": capture_id,
        "source": source,
        "source_kind": "live_rtsp" if source_is_live else "local_replay",
        "rtsp_url": source if source.lower().startswith("rtsp://") else None,
        "mode": "passive_rtsp_live_visual_timeline" if source_is_live else "local_replay_visual_timeline",
        "target_seconds": seconds,
        "sample_interval_s": sample_interval_s,
        "segment_s": segment_s,
        "open_wall_s": open_wall_s,
        "prewarm": prewarm_report,
        "processing_wall_s": capture_wall_s,
        "timeline_duration_s": timeline_duration_s,
        "capture_wall_s": capture_wall_s,
        "decoded_frames": decoded,
        "sampled_frames": len(samples),
        "source_width": stream.codec_context.width,
        "source_height": stream.codec_context.height,
        "video_duration_s_from_pts": video_duration_s,
        "estimated_source_fps": decoded / video_duration_s if video_duration_s and video_duration_s > 0 else None,
        "adaptive_thresholds": {
            "full_change_p90": shift_threshold,
            "subtitle_change_p90": percentile(finite([s.subtitle_change for s in samples]), 90),
            "phash_hamming_p90": percentile(finite([float(s.phash_hamming) if s.phash_hamming is not None else None for s in samples]), 90),
        },
        "performance": {
            "sample_process_ms": summarize([s.process_wall_ms for s in samples]),
            "decoded_fps_wall": decoded / capture_wall_s if capture_wall_s > 0 else None,
            "sampled_fps_wall": len(samples) / capture_wall_s if capture_wall_s > 0 else None,
        },
        "change_summary": {
            "full_change": summarize([s.full_change for s in samples]),
            "top_change": summarize([s.top_change for s in samples]),
            "center_change": summarize([s.center_change for s in samples]),
            "subtitle_change": summarize([s.subtitle_change for s in samples]),
            "bottom_change": summarize([s.bottom_change for s in samples]),
            "phash_hamming": summarize([float(s.phash_hamming) if s.phash_hamming is not None else None for s in samples]),
        },
        "samples": [asdict(s) for s in samples],
        "segments": [asdict(s) for s in segments],
        "notes": [
            "This probe uses adaptive thresholds from the observed session; it does not hard-code Bilibili or any platform UI.",
            "Segments are candidates for downstream ASR/VLM/OCR scheduling, not final learning-task boundaries.",
            "Without ADB this probe cannot collect touch events or foreground app state.",
        ],
    }
    if save_every_sample and not frames_dir.exists():
        frames_dir.mkdir(parents=True, exist_ok=True)
    return report


def publish_capture_bundle(
    *,
    out_dir: Path,
    report: dict[str, Any],
    manifest_id: str,
    capture_id: str,
    source: str,
    source_kind: str,
    rtsp_url: str | None,
    raw_recording: dict[str, Any],
    trust_level: str,
) -> None:
    manifest_path = out_dir / "capture_manifest.json"
    report_path = out_dir / "live_timeline_report.json"
    samples_path = out_dir / "samples.jsonl"
    markdown_path = out_dir / "live_timeline_report.md"
    report["manifest_id"] = manifest_id
    report["manifest_file"] = str(manifest_path)

    atomic_write_json(report_path, report)
    atomic_write_jsonl(samples_path, report.get("samples", []))
    write_markdown(markdown_path, report)
    artifacts = {
        "timeline_report": artifact_record(report_path, out_dir),
        "samples": artifact_record(samples_path, out_dir),
        "markdown_report": artifact_record(markdown_path, out_dir),
    }
    manifest = build_capture_manifest(
        manifest_id=manifest_id,
        capture_id=capture_id,
        source=source,
        source_kind=source_kind,
        rtsp_url=rtsp_url,
        raw_recording=raw_recording,
        trust_level=trust_level,
        artifacts=artifacts,
    )
    atomic_write_json(manifest_path, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Passive RTSP live timeline probe without ADB control.")
    parser.add_argument("--source", default=None, help="Optional RTSP URL or local video file. If omitted, phone-ip/rtsp-port is used.")
    parser.add_argument("--phone-ip", default="10.26.122.39")
    parser.add_argument("--rtsp-port", type=valid_port, default=8554)
    parser.add_argument("--seconds", type=positive_finite_float, default=20.0)
    parser.add_argument("--sample-interval-s", type=positive_finite_float, default=0.5)
    parser.add_argument("--segment-s", type=positive_finite_float, default=3.0)
    parser.add_argument("--tag", default="rtsp_live_timeline")
    parser.add_argument("--rtsp-transport", choices=("tcp",), default="tcp")
    parser.add_argument("--open-retries", type=nonnegative_int, default=5)
    parser.add_argument("--open-retry-delay-s", type=positive_finite_float, default=1.0)
    parser.add_argument("--prewarm-iterations", type=nonnegative_int, default=3)
    parser.add_argument("--no-raw-record", action="store_true")
    parser.add_argument("--no-save-frames", action="store_true")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()

    capture_id = f"cap_{uuid.uuid4()}"
    manifest_id = f"manifest_{uuid.uuid4()}"
    source = args.source or f"rtsp://{args.phone_ip}:{args.rtsp_port}/screen"
    source_is_rtsp = source.lower().startswith("rtsp://")
    connectivity_endpoint: tuple[str, int] | None = None
    if source_is_rtsp:
        try:
            connectivity_endpoint = rtsp_connectivity_endpoint(source)
        except ValueError as exc:
            parser.error(str(exc))
    safe_source = redact_source(source)
    rtsp_url = safe_source if source_is_rtsp else None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = create_capture_output_dir(
        ROOT / "captures",
        tag=args.tag,
        stamp=stamp,
        capture_id=capture_id,
        manifest_id=manifest_id,
    )

    if source_is_rtsp and connectivity_endpoint is not None and not port_open(*connectivity_endpoint, timeout_s=2.0):
        report = {
            "capture_id": capture_id,
            "out_dir": str(out_dir),
            "source": safe_source,
            "source_kind": "live_rtsp",
            "rtsp_url": rtsp_url,
            "mode": "passive_rtsp_live_visual_timeline",
            "error": "rtsp_port_not_open",
            "primary_error": "rtsp_port_not_open",
            "trust_level": "insufficient",
            "production_usable": False,
            "acquisition_source_kind": "live_rtsp",
            "analysis_source_kind": "not_started",
            "processing_mode": "acquisition_failed",
            "raw_recording": {
                "capture_id": capture_id,
                "error": "raw_recording_missing_or_empty",
            },
            "samples": [],
            "segments": [],
        }
        publish_capture_bundle(
            out_dir=out_dir,
            report=report,
            manifest_id=manifest_id,
            capture_id=capture_id,
            source=safe_source,
            source_kind="live_rtsp",
            rtsp_url=rtsp_url,
            raw_recording=report["raw_recording"],
            trust_level="insufficient",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        raise SystemExit(2)

    raw_partial = out_dir / "raw_rtsp_copy.mkv.partial"
    canonical_raw = out_dir / "raw_rtsp_copy.mkv"
    raw_log = out_dir / "ffmpeg_raw_record.log"
    raw_info: dict[str, Any] = {
        "capture_id": capture_id,
        "file": None,
        "ffmpeg_exit_code": None,
        "ffmpeg_log": None,
    }
    primary_error: str | None = None
    error_detail: str | None = None
    recorder_error: str | None = None
    recording: dict[str, Any] | None = None
    trust_level = "insufficient"
    production_usable = False
    report: dict[str, Any] = {
        "capture_id": capture_id,
        "source": safe_source,
        "source_kind": "live_rtsp" if source_is_rtsp else "local_replay",
        "rtsp_url": rtsp_url,
        "target_seconds": args.seconds,
        "samples": [],
        "segments": [],
    }

    analysis_kwargs = {
        "capture_id": capture_id,
        "out_dir": out_dir,
        "seconds": args.seconds,
        "sample_interval_s": args.sample_interval_s,
        "segment_s": args.segment_s,
        "save_every_sample": not args.no_save_frames,
        "rtsp_transport": args.rtsp_transport,
        "open_retries": args.open_retries,
        "retry_delay_s": args.open_retry_delay_s,
        "prewarm_iterations": args.prewarm_iterations,
    }

    if source_is_rtsp and not args.no_raw_record:
        raw_proc: subprocess.Popen[str] | None = None
        acquisition_start = time.perf_counter()
        try:
            raw_proc = start_raw_recorder(args.ffmpeg, source, args.seconds, raw_partial, raw_log)
        except Exception as exc:
            primary_error = "raw_recorder_start_failed"
            recorder_error = safe_exception(exc, source)
        if raw_proc is not None:
            try:
                raw_info["ffmpeg_exit_code"] = close_raw_recorder(
                    raw_proc,
                    timeout_s=max(8.0, args.seconds + 8.0),
                )
            except Exception as exc:
                primary_error = "raw_recorder_close_failed"
                recorder_error = safe_exception(exc, source)
        acquisition_wall_s = time.perf_counter() - acquisition_start
        raw_info["ffmpeg_log"] = str(raw_log) if raw_log.exists() else None

        observed_snapshot: dict[str, Any] | None = None
        if raw_partial.exists() and raw_partial.stat().st_size > 0:
            raw_info["file"] = str(raw_partial)
            try:
                observed_snapshot = stable_file_snapshot(raw_partial)
                raw_info["observed_size_bytes"] = observed_snapshot["size_bytes"]
                raw_info["observed_sha256"] = observed_snapshot["sha256"]
                raw_info["size_mb"] = observed_snapshot["size_bytes"] / 1024 / 1024
            except Exception as exc:
                primary_error = primary_error or "raw_snapshot_unstable"
                recorder_error = recorder_error or safe_exception(exc, source)

        probe_report: dict[str, Any] | None = None
        if observed_snapshot is not None and primary_error is None:
            try:
                probe_report = ffprobe(args.ffprobe, raw_partial)
            except Exception as exc:
                recorder_error = safe_exception(exc, source)
        recording = recording_status(raw_info["ffmpeg_exit_code"], probe_report, args.seconds)
        raw_info["ffprobe"] = probe_report
        if not recording["complete"]:
            if raw_info["ffmpeg_exit_code"] not in (None, 0):
                raw_info["error"] = f"raw_recorder_failed_exit_code_{raw_info['ffmpeg_exit_code']}"
                primary_error = primary_error or "raw_recorder_failed"
            elif primary_error is not None:
                raw_info["error"] = primary_error
            else:
                raw_info["error"] = "invalid_or_incomplete_raw_recording"
                primary_error = "invalid_or_incomplete_raw_recording"
        elif primary_error is None:
            try:
                os.replace(raw_partial, canonical_raw)
                canonical_before = stable_file_snapshot(canonical_raw)
                raw_info["file"] = str(canonical_raw)
            except Exception as exc:
                primary_error = "canonical_raw_publish_failed"
                error_detail = safe_exception(exc, source)
                raw_info["error"] = "capture_failed_before_content_hash_binding"
            if primary_error is None and observed_snapshot is not None:
                if (
                    canonical_before["size_bytes"] != observed_snapshot["size_bytes"]
                    or canonical_before["sha256"] != observed_snapshot["sha256"]
                ):
                    primary_error = "source_changed_before_canonical_analysis"
                    raw_info["error"] = primary_error
            if primary_error is None:
                canonical_probe: dict[str, Any] | None = None
                try:
                    canonical_probe = ffprobe(args.ffprobe, canonical_raw)
                except Exception as exc:
                    recorder_error = safe_exception(exc, source)
                recording = recording_status(raw_info["ffmpeg_exit_code"], canonical_probe, args.seconds)
                raw_info["partial_ffprobe"] = probe_report
                raw_info["ffprobe"] = canonical_probe
                if not recording["complete"]:
                    primary_error = "canonical_media_validation_failed"
                    raw_info["error"] = primary_error
            if primary_error is None:
                try:
                    replay_report = analyze_live(
                        source=str(canonical_raw),
                        source_is_live=False,
                        **analysis_kwargs,
                    )
                    canonical_after = stable_file_snapshot(canonical_raw)
                    if not snapshots_match(canonical_before, canonical_after):
                        raise RuntimeError("canonical_raw_changed_during_analysis")
                    report = replay_report
                    raw_info.update({
                        "canonical_file": canonical_after["canonical_file"],
                        "size_bytes": canonical_after["size_bytes"],
                        "sha256": canonical_after["sha256"],
                    })
                    trust_level = "content_hash_bound"
                    production_usable = True
                except Exception as exc:
                    primary_error = "timeline_analysis_failed"
                    error_detail = safe_exception(exc, source)
                    raw_info["error"] = "capture_failed_before_content_hash_binding"

        report["source"] = safe_source
        report["source_kind"] = "live_rtsp"
        report["rtsp_url"] = rtsp_url
        report["acquisition_source_kind"] = "live_rtsp"
        report["analysis_source_kind"] = "canonical_raw_replay" if canonical_raw.exists() else "not_started"
        report["processing_mode"] = "deferred_trusted_evidence"
        report["mode"] = "deferred_canonical_raw_timeline"
        report["acquisition_wall_s"] = acquisition_wall_s
        if "capture_wall_s" in report:
            report["analysis_wall_s"] = report.pop("capture_wall_s")
        report["capture_wall_s"] = acquisition_wall_s
        if "processing_wall_s" in report:
            report["analysis_processing_wall_s"] = report.pop("processing_wall_s")
    elif source_is_rtsp:
        try:
            report = analyze_live(source=source, source_is_live=True, **analysis_kwargs)
        except Exception as exc:
            primary_error = "live_fast_path_analysis_failed"
            error_detail = safe_exception(exc, source)
        report["source"] = safe_source
        report["source_kind"] = "live_rtsp"
        report["rtsp_url"] = rtsp_url
        report["acquisition_source_kind"] = "live_rtsp"
        report["analysis_source_kind"] = "live_rtsp_untrusted"
        report["processing_mode"] = "live_untrusted_fast_path"
        raw_info["error"] = "raw_recording_disabled"
    else:
        replay_path = Path(source)
        before_snapshot: dict[str, Any] | None = None
        try:
            if replay_path.exists() and replay_path.stat().st_size > 0:
                before_snapshot = stable_file_snapshot(replay_path)
                raw_info["file"] = str(replay_path)
                raw_info["observed_size_bytes"] = before_snapshot["size_bytes"]
                raw_info["observed_sha256"] = before_snapshot["sha256"]
                raw_info["size_mb"] = before_snapshot["size_bytes"] / 1024 / 1024
        except Exception as exc:
            primary_error = "local_replay_snapshot_failed"
            error_detail = safe_exception(exc, source)
        try:
            replay_report = analyze_live(source=source, source_is_live=False, **analysis_kwargs)
            report = replay_report
        except Exception as exc:
            primary_error = "timeline_analysis_failed"
            error_detail = safe_exception(exc, source)
        if primary_error is None and before_snapshot is not None:
            try:
                after_snapshot = stable_file_snapshot(replay_path)
                if not snapshots_match(before_snapshot, after_snapshot):
                    raise RuntimeError("local_replay_changed_during_analysis")
            except Exception as exc:
                primary_error = "local_replay_changed_during_analysis"
                error_detail = safe_exception(exc, source)
        raw_info["error"] = primary_error or "local_replay_external_toctou_untrusted"
        report["source"] = safe_source
        report["source_kind"] = "local_replay"
        report["rtsp_url"] = None
        report["acquisition_source_kind"] = "local_replay"
        report["analysis_source_kind"] = "local_replay"
        report["processing_mode"] = "local_replay_untrusted_external_source"
        report["trust_limitations"] = ["external_local_replay_not_copied_to_canonical_snapshot"]

    report["capture_id"] = capture_id
    report["out_dir"] = str(out_dir)
    report["raw_recording"] = raw_info
    report["trust_level"] = trust_level
    report["production_usable"] = production_usable
    if recording is not None:
        report["recording_status"] = recording
    if primary_error is not None:
        report["primary_error"] = primary_error
        report["error"] = error_detail or primary_error
    if recorder_error is not None:
        report["recorder_error"] = recorder_error
    report.setdefault("samples", [])
    report.setdefault("segments", [])

    publish_capture_bundle(
        out_dir=out_dir,
        report=report,
        manifest_id=manifest_id,
        capture_id=capture_id,
        source=safe_source,
        source_kind=report["source_kind"],
        rtsp_url=rtsp_url,
        raw_recording=raw_info,
        trust_level=trust_level,
    )

    print(json.dumps({
        "capture_id": capture_id,
        "out_dir": str(out_dir),
        "error": report.get("error"),
        "raw_size_mb": raw_info.get("size_mb"),
        "decoded_frames": report.get("decoded_frames"),
        "sampled_frames": report.get("sampled_frames"),
        "capture_wall_s": report.get("capture_wall_s"),
        "sample_process_ms_p95": (report.get("performance") or {}).get("sample_process_ms", {}).get("p95"),
        "sample_process_ms_max": (report.get("performance") or {}).get("sample_process_ms", {}).get("max"),
        "prewarm": report.get("prewarm"),
        "segment_count": len(report.get("segments", [])),
    }, ensure_ascii=False, indent=2, allow_nan=False))
    if primary_error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
