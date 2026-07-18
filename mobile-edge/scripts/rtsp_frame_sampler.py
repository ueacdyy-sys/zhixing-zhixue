from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import av
import cv2
import imagehash
import numpy as np
from PIL import Image


@dataclass
class KeptFrame:
    index: int
    video_time_s: float | None
    wall_time_s: float
    width: int
    height: int
    phash: str
    hamming_from_previous_kept: int | None
    reason: str
    file: str


def frame_time_seconds(frame: av.VideoFrame) -> float | None:
    if frame.pts is None or frame.time_base is None:
        return None
    return float(frame.pts * frame.time_base)


def phash_for_bgr(frame_bgr: np.ndarray) -> imagehash.ImageHash:
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    return imagehash.phash(img)


def save_frame(frame_bgr: np.ndarray, path: Path, jpeg_quality: int = 88) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    if not ok:
        raise RuntimeError(f"failed to write frame: {path}")


def summarize_intervals(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "max": None, "mean": None}
    arr = np.array(values, dtype=np.float64)
    return {
        "min": float(np.min(arr)),
        "median": float(np.median(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
    }


def sample_video(
    source: str,
    out_dir: Path,
    target_interval_s: float,
    max_frames: int | None,
    max_duration_s: float | None,
    dedup_hamming_threshold: int,
    resize_width: int | None,
    rtsp_transport: str | None,
    open_retries: int = 1,
    open_retry_delay_s: float = 1.0,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "keyframes"
    frames_dir.mkdir(parents=True, exist_ok=True)

    options: dict[str, str] = {}
    if source.lower().startswith("rtsp://"):
        options["rtsp_transport"] = rtsp_transport or "tcp"
        options["stimeout"] = "5000000"

    t0 = time.perf_counter()
    last_open_error: Exception | None = None
    container = None
    attempts = max(1, open_retries)
    for attempt in range(1, attempts + 1):
        try:
            container = av.open(source, options=options)
            break
        except Exception as exc:
            last_open_error = exc
            if attempt >= attempts:
                raise
            time.sleep(open_retry_delay_s)
    if container is None:
        raise RuntimeError(f"failed to open source: {source}") from last_open_error
    open_wall_s = time.perf_counter() - t0
    stream = container.streams.video[0]

    decoded = 0
    kept: list[KeptFrame] = []
    phash_values: list[imagehash.ImageHash] = []
    decode_wall_times: list[float] = []
    video_times: list[float] = []
    last_kept_video_t: float | None = None
    last_kept_hash: imagehash.ImageHash | None = None
    first_video_t: float | None = None
    last_video_t: float | None = None
    width: int | None = None
    height: int | None = None

    decode_start = time.perf_counter()
    for packet in container.demux(stream):
        for frame in packet.decode():
            now = time.perf_counter()
            decoded += 1
            vt = frame_time_seconds(frame)
            if vt is not None:
                first_video_t = vt if first_video_t is None else min(first_video_t, vt)
                last_video_t = vt
                video_times.append(vt)

            if max_frames is not None and decoded > max_frames:
                break
            if max_duration_s is not None and vt is not None and first_video_t is not None:
                if vt - first_video_t > max_duration_s:
                    break

            frame_bgr = frame.to_ndarray(format="bgr24")
            height, width = frame_bgr.shape[:2]
            if resize_width and width and width > resize_width:
                scale = resize_width / width
                frame_bgr = cv2.resize(
                    frame_bgr,
                    (resize_width, max(1, int(round(height * scale)))),
                    interpolation=cv2.INTER_AREA,
                )
                height, width = frame_bgr.shape[:2]

            keep_reason = None
            if last_kept_video_t is None:
                keep_reason = "first_frame"
            elif vt is not None and (vt - last_kept_video_t) >= target_interval_s:
                keep_reason = f"interval>={target_interval_s:.3f}s"
            elif vt is None:
                # Fallback for sources without PTS: keep by decoded frame count.
                step = max(1, int(round(target_interval_s * 30)))
                if decoded % step == 0:
                    keep_reason = f"fallback_every_{step}_frames"

            if keep_reason:
                current_hash = phash_for_bgr(frame_bgr)
                hamming = None
                if last_kept_hash is not None:
                    hamming = int(current_hash - last_kept_hash)
                    if hamming < dedup_hamming_threshold:
                        keep_reason = None
                if keep_reason:
                    name = f"keyframe_{len(kept) + 1:04d}_src{decoded:05d}.jpg"
                    rel_file = str(Path("keyframes") / name)
                    save_frame(frame_bgr, out_dir / rel_file)
                    kept.append(
                        KeptFrame(
                            index=decoded,
                            video_time_s=vt,
                            wall_time_s=now - decode_start,
                            width=width or 0,
                            height=height or 0,
                            phash=str(current_hash),
                            hamming_from_previous_kept=hamming,
                            reason=keep_reason,
                            file=rel_file,
                        )
                    )
                    phash_values.append(current_hash)
                    last_kept_hash = current_hash
                    if vt is not None:
                        last_kept_video_t = vt
            decode_wall_times.append(time.perf_counter() - now)

        if max_frames is not None and decoded > max_frames:
            break
        if max_duration_s is not None and last_video_t is not None and first_video_t is not None:
            if last_video_t - first_video_t > max_duration_s:
                break

    total_wall_s = time.perf_counter() - decode_start
    container.close()

    video_duration_s = None
    if first_video_t is not None and last_video_t is not None and last_video_t >= first_video_t:
        video_duration_s = last_video_t - first_video_t

    video_intervals = [
        b - a for a, b in zip(video_times, video_times[1:]) if b >= a and math.isfinite(b - a)
    ]
    kept_intervals = []
    kept_times = [k.video_time_s for k in kept if k.video_time_s is not None]
    kept_intervals = [b - a for a, b in zip(kept_times, kept_times[1:]) if b >= a]

    report: dict[str, Any] = {
        "source": source,
        "created_at_unix": time.time(),
        "open_wall_s": open_wall_s,
        "decode_wall_s": total_wall_s,
        "decoded_frames": decoded,
        "kept_frames": len(kept),
        "source_width": stream.codec_context.width,
        "source_height": stream.codec_context.height,
        "output_width": width,
        "output_height": height,
        "stream_average_rate": str(stream.average_rate) if stream.average_rate else None,
        "stream_base_rate": str(stream.base_rate) if stream.base_rate else None,
        "stream_time_base": str(stream.time_base) if stream.time_base else None,
        "video_duration_s_from_pts": video_duration_s,
        "offline_decode_fps": decoded / total_wall_s if total_wall_s > 0 else None,
        "estimated_source_fps_from_pts": decoded / video_duration_s if video_duration_s and video_duration_s > 0 else None,
        "target_interval_s": target_interval_s,
        "dedup_hamming_threshold": dedup_hamming_threshold,
        "video_frame_interval_s": summarize_intervals(video_intervals),
        "kept_frame_interval_s": summarize_intervals(kept_intervals),
        "frames": [asdict(k) for k in kept],
        "notes": [
            "offline_decode_fps reflects local file decode throughput, not phone-to-PC live latency.",
            "estimated_source_fps_from_pts estimates original stream cadence from video timestamps.",
            "kept frames are sampled for downstream OCR/vision; this script does not perform semantic understanding yet.",
        ],
    }
    (out_dir / "sampler_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample keyframes from RTSP or saved screen stream.")
    parser.add_argument("--source", required=True, help="RTSP URL or local video file")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--target-interval-s", type=float, default=0.75)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--max-duration-s", type=float, default=None)
    parser.add_argument("--dedup-hamming-threshold", type=int, default=4)
    parser.add_argument("--resize-width", type=int, default=None)
    parser.add_argument("--rtsp-transport", default="tcp")
    parser.add_argument("--open-retries", type=int, default=5)
    parser.add_argument("--open-retry-delay-s", type=float, default=1.0)
    args = parser.parse_args()

    report = sample_video(
        source=args.source,
        out_dir=Path(args.out_dir),
        target_interval_s=args.target_interval_s,
        max_frames=args.max_frames,
        max_duration_s=args.max_duration_s,
        dedup_hamming_threshold=args.dedup_hamming_threshold,
        resize_width=args.resize_width,
        rtsp_transport=args.rtsp_transport,
        open_retries=args.open_retries,
        open_retry_delay_s=args.open_retry_delay_s,
    )
    print(json.dumps({k: report[k] for k in (
        "source",
        "decode_wall_s",
        "decoded_frames",
        "kept_frames",
        "video_duration_s_from_pts",
        "offline_decode_fps",
        "estimated_source_fps_from_pts",
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
