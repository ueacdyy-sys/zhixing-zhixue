from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR


REGIONS = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "top_35pct": (0.0, 0.0, 1.0, 0.35),
    "middle_55pct": (0.0, 0.18, 1.0, 0.73),
    "bottom_40pct": (0.0, 0.60, 1.0, 1.0),
    "subtitle_band": (0.0, 0.48, 1.0, 0.86),
}


@dataclass
class RegionOcr:
    region: str
    wall_s: float
    item_count: int
    text: list[str]
    confidences: list[float]


@dataclass
class FrameUnderstanding:
    file: str
    index: int
    source_index: int | None
    video_time_s: float | None
    hamming_from_previous_kept: int | None
    width: int
    height: int
    regions: list[RegionOcr]


def crop_region(image: np.ndarray, region: str) -> np.ndarray:
    h, w = image.shape[:2]
    x1p, y1p, x2p, y2p = REGIONS[region]
    x1, y1, x2, y2 = int(w * x1p), int(h * y1p), int(w * x2p), int(h * y2p)
    return image[y1:y2, x1:x2]


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", "", value)
    value = value.strip("·.,，。:：;；|丨[]【】()（）<>《》“”\"'")
    return value


def useful_terms(texts: list[str]) -> list[str]:
    terms: list[str] = []
    for raw in texts:
        text = clean_text(raw)
        if not text:
            continue
        for token in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_+-]{2,}|\d+(?:\.\d+)?", text):
            if len(token) >= 2:
                terms.append(token)
    return terms


def summarize(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "max": None, "mean": None}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
        "mean": statistics.mean(values),
    }


def load_sampler_frames(capture_dir: Path) -> dict[str, dict[str, Any]]:
    report_path = capture_dir / "sampler_report.json"
    if not report_path.exists():
        return {}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    frames = {}
    for frame in report.get("frames", []):
        frames[Path(frame.get("file", "")).name] = frame
    return frames


def make_contact_sheet(frames: list[Path], out_path: Path, max_frames: int = 12) -> None:
    selected = frames[:max_frames]
    if not selected:
        return
    thumbs = []
    for i, frame in enumerate(selected, start=1):
        img = cv2.imread(str(frame))
        if img is None:
            continue
        thumb_h = 360
        scale = thumb_h / img.shape[0]
        thumb_w = max(1, int(round(img.shape[1] * scale)))
        thumb = cv2.resize(img, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
        cv2.putText(
            thumb,
            f"#{i}",
            (12, 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        thumbs.append(thumb)
    if not thumbs:
        return
    cols = min(4, len(thumbs))
    rows = int(np.ceil(len(thumbs) / cols))
    cell_h = max(t.shape[0] for t in thumbs)
    cell_w = max(t.shape[1] for t in thumbs)
    sheet = np.full((rows * cell_h, cols * cell_w, 3), 255, dtype=np.uint8)
    for i, thumb in enumerate(thumbs):
        r, c = divmod(i, cols)
        y, x = r * cell_h, c * cell_w
        sheet[y : y + thumb.shape[0], x : x + thumb.shape[1]] = thumb
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), sheet)


def ocr_region(engine: RapidOCR, image: np.ndarray, region: str, temp_dir: Path, stem: str) -> RegionOcr:
    crop = crop_region(image, region)
    crop_path = temp_dir / f"{stem}_{region}.jpg"
    cv2.imwrite(str(crop_path), crop)
    t0 = time.perf_counter()
    result, _elapse = engine(str(crop_path))
    wall_s = time.perf_counter() - t0
    texts: list[str] = []
    confs: list[float] = []
    for item in result or []:
        texts.append(str(item[1]))
        try:
            confs.append(float(item[2]))
        except Exception:
            confs.append(0.0)
    return RegionOcr(
        region=region,
        wall_s=wall_s,
        item_count=len(texts),
        text=texts,
        confidences=confs,
    )


def write_markdown(out_path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# 真实浏览内容理解探针",
        "",
        "## 结论边界",
        "",
        "- 本报告只证明当前采集样本上的画面关键帧、OCR文本和耗时表现。",
        "- 本报告不把OCR等同于完整视频理解；若没有本地视觉语言模型或音频流，主题判断只能作为候选证据。",
        "- 本报告不使用平台硬编码规则判断是否短视频场景。",
        "",
        "## 性能摘要",
        "",
        f"- 关键帧数量：`{report['frame_count']}`",
        f"- OCR区域：`{', '.join(report['regions'])}`",
        f"- OCR初始化耗时：`{report['engine_init_s']:.3f}s`",
        f"- 单区域OCR耗时中位数：`{report['ocr_wall_s']['median']}`",
        f"- 单区域OCR耗时均值：`{report['ocr_wall_s']['mean']}`",
        f"- OCR总耗时：`{report['ocr_total_wall_s']:.3f}s`",
        "",
        "## 高频可见词",
        "",
    ]
    for term, count in report.get("top_terms", [])[:30]:
        lines.append(f"- `{term}`：{count}")
    lines.extend(["", "## 按帧证据", ""])
    for frame in report.get("frames", []):
        lines.append(
            f"### 帧 {frame['index']} | t={frame.get('video_time_s')} | "
            f"hash_delta={frame.get('hamming_from_previous_kept')}"
        )
        any_text = False
        for region in frame["regions"]:
            texts = [clean_text(t) for t in region["text"] if clean_text(t)]
            if texts:
                any_text = True
                joined = " / ".join(texts[:20])
                lines.append(f"- `{region['region']}`：{joined}")
        if not any_text:
            lines.append("- 未识别到稳定文本。")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate OCR and timing evidence from sampled live browsing keyframes.")
    parser.add_argument("--capture-dir", required=True)
    parser.add_argument("--frames-dir", default=None)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--regions", default="subtitle_band,bottom_40pct,top_35pct")
    parser.add_argument("--max-frames", type=int, default=12)
    parser.add_argument("--selection", choices=["first", "evenly"], default="first")
    parser.add_argument("--min-confidence", type=float, default=0.45)
    args = parser.parse_args()

    capture_dir = Path(args.capture_dir)
    frames_dir = Path(args.frames_dir) if args.frames_dir else capture_dir / "keyframes"
    if not frames_dir.exists() and (capture_dir / "frames").exists():
        frames_dir = capture_dir / "frames"
    if not frames_dir.exists():
        raise RuntimeError(f"keyframes dir not found: {frames_dir}")
    out_dir = Path(args.out_dir) if args.out_dir else capture_dir / "content_understanding"
    out_dir.mkdir(parents=True, exist_ok=True)
    regions = [r.strip() for r in args.regions.split(",") if r.strip()]
    unknown = [r for r in regions if r not in REGIONS]
    if unknown:
        raise RuntimeError(f"unknown regions: {unknown}; choices={sorted(REGIONS)}")

    frames = sorted(frames_dir.glob("*.jpg"))
    if args.max_frames and len(frames) > args.max_frames:
        if args.selection == "evenly":
            indices = np.linspace(0, len(frames) - 1, num=args.max_frames, dtype=int)
            frames = [frames[int(i)] for i in indices]
        else:
            frames = frames[: args.max_frames]
    if not frames:
        raise RuntimeError(f"no jpg frames found: {frames_dir}")

    sampler_map = load_sampler_frames(capture_dir)
    make_contact_sheet(frames, out_dir / "contact_sheet.jpg", max_frames=args.max_frames)

    init_start = time.perf_counter()
    engine = RapidOCR()
    engine_init_s = time.perf_counter() - init_start

    frame_results: list[FrameUnderstanding] = []
    ocr_times: list[float] = []
    all_confident_texts: list[str] = []
    ocr_total_start = time.perf_counter()
    with TemporaryDirectory(prefix="content_understanding_") as td:
        temp_dir = Path(td)
        for i, frame_path in enumerate(frames, start=1):
            image = cv2.imread(str(frame_path))
            if image is None:
                continue
            meta = sampler_map.get(frame_path.name, {})
            region_results: list[RegionOcr] = []
            for region in regions:
                rr = ocr_region(engine, image, region, temp_dir, frame_path.stem)
                region_results.append(rr)
                ocr_times.append(rr.wall_s)
                for text, conf in zip(rr.text, rr.confidences):
                    if conf >= args.min_confidence:
                        all_confident_texts.append(text)
            frame_results.append(
                FrameUnderstanding(
                    file=str(frame_path),
                    index=i,
                    source_index=meta.get("index"),
                    video_time_s=meta.get("video_time_s"),
                    hamming_from_previous_kept=meta.get("hamming_from_previous_kept"),
                    width=int(image.shape[1]),
                    height=int(image.shape[0]),
                    regions=region_results,
                )
            )
    ocr_total_wall_s = time.perf_counter() - ocr_total_start

    term_counts = Counter(useful_terms(all_confident_texts))
    report: dict[str, Any] = {
        "capture_dir": str(capture_dir),
        "frames_dir": str(frames_dir),
        "created_at_unix": time.time(),
        "frame_count": len(frame_results),
        "regions": regions,
        "engine_init_s": engine_init_s,
        "ocr_total_wall_s": ocr_total_wall_s,
        "ocr_wall_s": summarize(ocr_times),
        "top_terms": term_counts.most_common(50),
        "frames": [asdict(frame) for frame in frame_results],
        "artifacts": {
            "contact_sheet": str(out_dir / "contact_sheet.jpg"),
            "json": str(out_dir / "understanding_report.json"),
            "markdown": str(out_dir / "understanding_report.md"),
        },
        "notes": [
            "This is evidence aggregation, not a final semantic model.",
            "A real-time product pipeline should run OCR/VLM asynchronously after frame deduplication and dwell segmentation.",
            "No platform-specific scene guard rule is used in this script.",
        ],
    }
    (out_dir / "understanding_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_markdown(out_dir / "understanding_report.md", report)
    print(json.dumps({
        "out_dir": str(out_dir),
        "frame_count": report["frame_count"],
        "regions": regions,
        "engine_init_s": engine_init_s,
        "ocr_wall_s": report["ocr_wall_s"],
        "top_terms": report["top_terms"][:15],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
