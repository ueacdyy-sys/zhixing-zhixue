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
import numpy as np


REGIONS = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "top": (0.0, 0.0, 1.0, 0.28),
    "center": (0.0, 0.20, 1.0, 0.72),
    "subtitle_band": (0.0, 0.48, 1.0, 0.86),
    "bottom": (0.0, 0.70, 1.0, 1.0),
}


@dataclass
class SampleSignal:
    sample_index: int
    source_frame_index: int
    video_time_s: float | None
    full_change: float | None
    top_change: float | None
    center_change: float | None
    subtitle_change: float | None
    bottom_change: float | None
    full_luma: float
    subtitle_luma: float


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


def summarize(values: list[float]) -> dict[str, float | None]:
    finite = [v for v in values if v is not None and math.isfinite(v)]
    if not finite:
        return {"min": None, "p50": None, "p90": None, "p95": None, "max": None, "mean": None}
    arr = np.array(finite, dtype=np.float64)
    return {
        "min": float(np.min(arr)),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
    }


def candidate_segments(samples: list[SampleSignal]) -> list[dict[str, Any]]:
    full_values = [s.full_change for s in samples if s.full_change is not None]
    subtitle_values = [s.subtitle_change for s in samples if s.subtitle_change is not None]
    if not full_values:
        return []
    full_threshold = float(np.percentile(np.array(full_values), 90))
    subtitle_threshold = float(np.percentile(np.array(subtitle_values), 90)) if subtitle_values else full_threshold
    candidates: list[dict[str, Any]] = []
    for sample in samples:
        reasons = []
        if sample.full_change is not None and sample.full_change >= full_threshold:
            reasons.append("full_change_p90")
        if sample.subtitle_change is not None and sample.subtitle_change >= subtitle_threshold:
            reasons.append("subtitle_change_p90")
        if reasons:
            candidates.append(
                {
                    "video_time_s": sample.video_time_s,
                    "sample_index": sample.sample_index,
                    "source_frame_index": sample.source_frame_index,
                    "reasons": reasons,
                    "full_change": sample.full_change,
                    "subtitle_change": sample.subtitle_change,
                }
            )
    return candidates


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Video Signal Benchmark",
        "",
        "## Scope",
        "",
        "- This benchmark measures fast video-signal processing: decode, sampling, region change, and candidate cut points.",
        "- It does not claim semantic video understanding. OCR, ASR, and VLM stages must be benchmarked separately.",
        "",
        "## Performance",
        "",
        f"- source_video: `{report['source_video']}`",
        f"- decoded_frames: `{report['decoded_frames']}`",
        f"- sampled_frames: `{report['sampled_frames']}`",
        f"- video_duration_s: `{report['video_duration_s']}`",
        f"- wall_s: `{report['wall_s']:.3f}`",
        f"- decode_and_signal_fps: `{report['decode_and_signal_fps']:.3f}`",
        f"- realtime_factor: `{report['realtime_factor']:.3f}x`",
        "",
        "## Change Summary",
        "",
    ]
    for region in ["full_change", "top_change", "center_change", "subtitle_change", "bottom_change"]:
        summary = report["change_summary"].get(region, {})
        lines.append(
            f"- {region}: p50={summary.get('p50')}, p90={summary.get('p90')}, max={summary.get('max')}"
        )
    lines.extend(["", "## Candidate Cut Points", ""])
    for item in report.get("candidate_segments", [])[:40]:
        lines.append(
            f"- t={item.get('video_time_s')}s frame={item.get('source_frame_index')} "
            f"reason={','.join(item.get('reasons', []))} "
            f"full={item.get('full_change')} subtitle={item.get('subtitle_change')}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast video-signal benchmark for saved phone screen streams.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--sample-interval-s", type=float, default=0.5)
    parser.add_argument("--max-duration-s", type=float, default=None)
    args = parser.parse_args()

    source = Path(args.source)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    container = av.open(str(source))
    stream = container.streams.video[0]
    decoded = 0
    samples: list[SampleSignal] = []
    first_t: float | None = None
    last_t: float | None = None
    next_sample_t = 0.0
    prev_features: dict[str, np.ndarray | None] = {name: None for name in REGIONS}

    for packet in container.demux(stream):
        for frame in packet.decode():
            decoded += 1
            vt = frame_time_seconds(frame)
            if vt is not None:
                first_t = vt if first_t is None else min(first_t, vt)
                last_t = vt if last_t is None else max(last_t, vt)
            rel_t = (vt - first_t) if vt is not None and first_t is not None else None
            if args.max_duration_s is not None and rel_t is not None and rel_t > args.max_duration_s:
                break
            if rel_t is None:
                rel_t = decoded / 30.0
            if rel_t + 1e-9 < next_sample_t:
                continue

            image = frame.to_ndarray(format="bgr24")
            features = {name: feature_image(image, name) for name in REGIONS}
            changes = {
                name: mean_abs_change(prev_features[name], features[name])
                for name in REGIONS
            }
            prev_features = features
            samples.append(
                SampleSignal(
                    sample_index=len(samples) + 1,
                    source_frame_index=decoded,
                    video_time_s=vt,
                    full_change=changes["full"],
                    top_change=changes["top"],
                    center_change=changes["center"],
                    subtitle_change=changes["subtitle_band"],
                    bottom_change=changes["bottom"],
                    full_luma=float(np.mean(features["full"])),
                    subtitle_luma=float(np.mean(features["subtitle_band"])),
                )
            )
            while next_sample_t <= rel_t + 1e-9:
                next_sample_t += args.sample_interval_s
        if args.max_duration_s is not None and last_t is not None and first_t is not None:
            if last_t - first_t > args.max_duration_s:
                break
    container.close()
    wall_s = time.perf_counter() - t0

    duration_s = None
    if first_t is not None and last_t is not None and last_t >= first_t:
        duration_s = last_t - first_t
    change_summary = {
        "full_change": summarize([s.full_change for s in samples if s.full_change is not None]),
        "top_change": summarize([s.top_change for s in samples if s.top_change is not None]),
        "center_change": summarize([s.center_change for s in samples if s.center_change is not None]),
        "subtitle_change": summarize([s.subtitle_change for s in samples if s.subtitle_change is not None]),
        "bottom_change": summarize([s.bottom_change for s in samples if s.bottom_change is not None]),
    }
    report: dict[str, Any] = {
        "source_video": str(source),
        "sample_interval_s": args.sample_interval_s,
        "decoded_frames": decoded,
        "sampled_frames": len(samples),
        "video_duration_s": duration_s,
        "wall_s": wall_s,
        "decode_and_signal_fps": decoded / wall_s if wall_s > 0 else None,
        "sample_signal_fps": len(samples) / wall_s if wall_s > 0 else None,
        "realtime_factor": duration_s / wall_s if duration_s and wall_s > 0 else None,
        "change_summary": change_summary,
        "candidate_segments": candidate_segments(samples),
        "samples": [asdict(sample) for sample in samples],
        "notes": [
            "This is the fast signal layer for segmentation and process evidence.",
            "Candidate cut points are dynamic quantile markers, not final semantic boundaries.",
            "Use ASR/VLM/OCR after this layer, with latency budget and asynchronous queues.",
        ],
    }
    (out_dir / "video_signal_benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_markdown(out_dir / "video_signal_benchmark.md", report)
    print(json.dumps({
        "out_dir": str(out_dir),
        "decoded_frames": decoded,
        "sampled_frames": len(samples),
        "video_duration_s": duration_s,
        "wall_s": wall_s,
        "decode_and_signal_fps": report["decode_and_signal_fps"],
        "realtime_factor": report["realtime_factor"],
        "candidate_count": len(report["candidate_segments"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
