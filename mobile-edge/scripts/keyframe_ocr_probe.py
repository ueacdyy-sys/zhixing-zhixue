from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import cv2
from rapidocr_onnxruntime import RapidOCR
from unicode_image_io import read_image, write_image


@dataclass
class OcrFrameResult:
    file: str
    region: str
    width: int
    height: int
    wall_s: float
    engine_elapse: list[float] | None
    item_count: int
    text: list[str]
    confidences: list[float]


REGIONS = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "top_35pct": (0.0, 0.0, 1.0, 0.35),
    "middle_45pct": (0.0, 0.20, 1.0, 0.65),
    "bottom_35pct": (0.0, 0.65, 1.0, 1.0),
    "center_text_band": (0.0, 0.08, 1.0, 0.86),
}


def crop_region(image, region: str):
    if region not in REGIONS:
        raise ValueError(f"unknown region: {region}; choices={sorted(REGIONS)}")
    h, w = image.shape[:2]
    x1p, y1p, x2p, y2p = REGIONS[region]
    x1, y1, x2, y2 = int(w * x1p), int(h * y1p), int(w * x2p), int(h * y2p)
    return image[y1:y2, x1:x2]


def run_ocr_on_image(engine: RapidOCR, image_path: Path, region: str, temp_dir: Path) -> OcrFrameResult:
    image = read_image(image_path)
    if image is None:
        raise RuntimeError(f"failed to read image: {image_path}")
    crop = crop_region(image, region)
    crop_path = temp_dir / f"{image_path.stem}_{region}.jpg"
    if not write_image(crop_path, crop):
        raise RuntimeError(f"failed to write OCR crop: {crop_path}")
    t0 = time.perf_counter()
    result, elapse = engine(str(crop_path))
    wall_s = time.perf_counter() - t0
    texts: list[str] = []
    confs: list[float] = []
    for item in result or []:
        texts.append(str(item[1]))
        try:
            confs.append(float(item[2]))
        except Exception:
            confs.append(0.0)
    return OcrFrameResult(
        file=str(image_path),
        region=region,
        width=int(crop.shape[1]),
        height=int(crop.shape[0]),
        wall_s=wall_s,
        engine_elapse=list(elapse) if elapse is not None else None,
        item_count=len(texts),
        text=texts,
        confidences=confs,
    )


def summarize(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "max": None, "mean": None}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
        "mean": statistics.mean(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR probe for sampled keyframes.")
    parser.add_argument("--frames-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--region", choices=sorted(REGIONS), default="full")
    parser.add_argument("--max-frames", type=int, default=5)
    args = parser.parse_args()

    frames_dir = Path(args.frames_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = sorted(frames_dir.glob("*.jpg"))
    if args.max_frames:
        frames = frames[: args.max_frames]
    if not frames:
        raise RuntimeError(f"no jpg frames found: {frames_dir}")

    init_start = time.perf_counter()
    engine = RapidOCR()
    init_s = time.perf_counter() - init_start
    results: list[OcrFrameResult] = []
    with TemporaryDirectory(prefix="ocr_probe_") as td:
        temp_dir = Path(td)
        for frame in frames:
            results.append(run_ocr_on_image(engine, frame, args.region, temp_dir))

    wall_times = [r.wall_s for r in results]
    report: dict[str, Any] = {
        "frames_dir": str(frames_dir),
        "region": args.region,
        "max_frames": args.max_frames,
        "engine_init_s": init_s,
        "frame_count": len(results),
        "wall_s": summarize(wall_times),
        "results": [asdict(r) for r in results],
        "notes": [
            "OCR is a downstream semantic probe; it should be gated by frame deduplication/change detection.",
            "Full-frame OCR on CPU may be too slow for every 0.75s keyframe; use crop, lower frequency, or async pipeline.",
        ],
    }
    (out_dir / "ocr_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "out_dir": str(out_dir),
        "engine_init_s": init_s,
        "frame_count": len(results),
        "wall_s": report["wall_s"],
        "first_text": results[0].text[:12] if results else [],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
