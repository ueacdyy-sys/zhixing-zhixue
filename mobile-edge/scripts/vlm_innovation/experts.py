"""Independent evidence experts used as Router inputs, never final learner judgements."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .dataset import load_manifest


_WORDS = re.compile(r"[\w\u4e00-\u9fff]+")
_UI_WORDS = re.compile(r"(关注|点赞|评论|弹幕|搜索|详情页|播放|粉丝|作者|收藏|转发|推荐|直播|下载|登录|投币)")


def _tokens(value: str) -> set[str]:
    return {part.lower() for part in _WORDS.findall(value) if len(part) >= 2}


def _ocr_items(payload: dict[str, Any]) -> list[tuple[list[Any], str, float]]:
    items: list[tuple[list[Any], str, float]] = []
    for sample in payload.get("result", {}).get("samples", []):
        for raw in sample.get("raw", []):
            if isinstance(raw, list) and len(raw) > 2 and isinstance(raw[0], list) and isinstance(raw[1], str):
                try:
                    confidence = float(raw[2])
                except (ValueError, TypeError):
                    confidence = 0.0
                items.append((raw[0], raw[1], confidence))
    return items


class VisualSceneExpert:
    """Measures visual continuity and exposes existing VLM observation as evidence."""

    def evaluate(self, video: Path, vlm: dict[str, Any]) -> dict[str, Any]:
        try:
            import cv2
        except ImportError:
            return {"available": False, "reason": "opencv_unavailable", "content_change": None}
        capture = cv2.VideoCapture(str(video))
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frames: list[Any] = []
        for index in sorted({0, max(0, count // 2), max(0, count - 1)}):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if ok:
                frames.append(frame)
        capture.release()
        if len(frames) < 2:
            return {"available": False, "reason": "insufficient_decoded_frames", "content_change": None, "frame_width": width, "frame_height": height}
        histograms = [cv2.normalize(cv2.calcHist([frame], [0], None, [32], [0, 256]), None).flatten() for frame in frames]
        deltas = [float(cv2.compareHist(left, right, cv2.HISTCMP_BHATTACHARYYA)) for left, right in zip(histograms, histograms[1:])]
        return {
            "available": True,
            "sampled_frames": len(frames),
            "frame_width": width,
            "frame_height": height,
            "content_change": min(1.0, sum(deltas) / len(deltas)),
            "raw_vlm_observation": vlm.get("raw_model_text", ""),
            "observation_boundary": "raw VLM output is an input observation, not a gold scene label",
        }


class OcrScreenTextExpert:
    def evaluate(self, ocr: dict[str, Any], *, width: int, height: int) -> dict[str, Any]:
        values = _ocr_items(ocr)
        ui_count = 0
        text: list[str] = []
        confidences: list[float] = []
        for box, value, confidence in values:
            text.append(value)
            confidences.append(confidence)
            ys = [float(point[1]) for point in box if isinstance(point, list) and len(point) > 1]
            near_edge = bool(ys) and (min(ys) <= height * 0.08 or max(ys) >= height * 0.88)
            if near_edge or _UI_WORDS.search(value):
                ui_count += 1
        return {
            "detections": len(values),
            "mean_confidence": sum(confidences) / len(confidences) if confidences else None,
            "text": " ".join(text),
            "ui_like_detection_ratio": ui_count / len(values) if values else 0.0,
            "observation_boundary": "geometric and lexicon UI indicators are Router features, not final text-source labels",
        }


class AsrSemanticExpert:
    def evaluate(self, asr: dict[str, Any]) -> dict[str, Any]:
        segments = [item for item in asr.get("result", {}).get("segments", []) if isinstance(item, dict)]
        text = " ".join(str(item.get("text", "")) for item in segments).strip()
        timestamped = sum(1 for item in segments if any(key in item for key in ("start", "start_s", "start_ms")))
        return {
            "segments": len(segments),
            "text": text,
            "text_available": bool(text),
            "timestamped_segment_ratio": timestamped / len(segments) if segments else 0.0,
            "quality": "unavailable_without_human_or_calibrated_asr_quality_label",
        }


class UiNoiseExpert:
    def evaluate(self, *, visual: dict[str, Any], ocr: dict[str, Any]) -> dict[str, Any]:
        visual_change = visual.get("content_change")
        return {
            "ui_interference_estimate": ocr["ui_like_detection_ratio"],
            "ui_interference_available": bool(ocr["detections"]),
            "stable_ui_hint": bool(visual_change is not None and visual_change < 0.08 and ocr["ui_like_detection_ratio"] >= 0.5),
            "boundary": "must be reconciled with V2 regions and manual UI-interference label before supervision",
        }


class CrossModalConsistencyExpert:
    def evaluate(self, *, ocr: dict[str, Any], asr: dict[str, Any], visual: dict[str, Any]) -> dict[str, Any]:
        evidence_tokens = _tokens(ocr["text"]) | _tokens(asr["text"])
        vlm_tokens = _tokens(str(visual.get("raw_vlm_observation", "")))
        overlap = len(evidence_tokens & vlm_tokens) / len(vlm_tokens) if vlm_tokens else 0.0
        return {
            "ocr_asr_vlm_token_overlap": overlap,
            "has_cross_modal_evidence": bool(evidence_tokens and vlm_tokens),
            "conflict_signal": 1.0 - overlap if evidence_tokens and vlm_tokens else None,
            "boundary": "low lexical overlap is a conflict candidate requiring label review, not proof of hallucination",
        }


def extract_expert_row(record: dict[str, Any], dataset_root: Path) -> dict[str, Any]:
    root = dataset_root.resolve()
    evidence = record["evidence"]
    ocr = json.loads((root / evidence["ocr"]).read_text(encoding="utf-8"))
    asr = json.loads((root / evidence["asr"]).read_text(encoding="utf-8"))
    vlm = json.loads((root / evidence["vlm"]).read_text(encoding="utf-8"))
    visual = VisualSceneExpert().evaluate(root / record["video"], vlm)
    ocr_out = OcrScreenTextExpert().evaluate(ocr, width=int(visual.get("frame_width") or 1), height=int(visual.get("frame_height") or 1))
    asr_out = AsrSemanticExpert().evaluate(asr)
    ui_out = UiNoiseExpert().evaluate(visual=visual, ocr=ocr_out)
    consistency = CrossModalConsistencyExpert().evaluate(visual=visual, ocr=ocr_out, asr=asr_out)
    return {
        "record_id": record["record_id"], "source_video_group": record["source_video_group"], "split": record["split"], "window_id": record["window_id"],
        "experts": {"visual_scene": visual, "ocr_screen_text": ocr_out, "asr_semantic": asr_out, "ui_noise": ui_out, "cross_modal_consistency": consistency},
        "classification": "CANDIDATE_ONLY",
    }


def build_expert_rows(dataset_root: Path) -> list[dict[str, Any]]:
    return [extract_expert_row(record, dataset_root) for record in load_manifest(dataset_root)]
