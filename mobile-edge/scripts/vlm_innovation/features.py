"""Evidence-derived Router features with explicit availability masks."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

from .dataset import load_manifest


FEATURE_NAMES = (
    "ui_interference",
    "ui_interference_available",
    "ocr_density",
    "ocr_detection_count",
    "platform_ui_text_fraction",
    "asr_density",
    "audio_text_available",
    "asr_confidence",
    "asr_confidence_available",
    "vlm_output_density",
    "vlm_ascii_fraction",
    "cross_modal_token_overlap",
    "content_change",
    "content_change_available",
    "queue_pressure",
    "queue_pressure_available",
)

_PLATFORM_UI = re.compile(r"(关注|点赞|评论|弹幕|搜索|详情页|播放|粉丝|作者|收藏|转发|推荐|直播|下载|登录)")
_TOKENS = re.compile(r"[\w\u4e00-\u9fff]+")


def _bounded_length(value: str, scale: int = 320) -> float:
    return min(1.0, len(value.strip()) / scale)


def _tokens(value: str) -> set[str]:
    return {item.lower() for item in _TOKENS.findall(value) if len(item) > 1}


def _ocr_text_and_count(payload: dict[str, Any]) -> tuple[str, int]:
    values: list[str] = []
    count = 0
    for sample in payload.get("result", {}).get("samples", []):
        for raw in sample.get("raw", []):
            if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], str):
                values.append(raw[1])
                count += 1
    return " ".join(values), count


def _asr_text_and_confidence(payload: dict[str, Any]) -> tuple[str, float, bool]:
    segments = payload.get("result", {}).get("segments", [])
    text = " ".join(str(segment.get("text", "")) for segment in segments if isinstance(segment, dict))
    confidences = [float(segment[key]) for segment in segments if isinstance(segment, dict) for key in ("confidence", "avg_logprob") if isinstance(segment.get(key), (int, float))]
    if not confidences:
        return text, 0.0, False
    # avg_logprob cannot be interpreted as probability; it is normalised only
    # to provide a bounded Router input alongside its availability mask.
    value = sum(confidences) / len(confidences)
    return text, min(1.0, max(0.0, value if 0.0 <= value <= 1.0 else math.exp(min(0.0, value)))), True


def _ui_score(value: Any) -> tuple[float, bool]:
    if not isinstance(value, str):
        return 0.0, False
    if "重度" in value:
        return 1.0, True
    if "中度" in value:
        return 0.55, True
    if "轻度" in value:
        return 0.25, True
    if "无" in value:
        return 0.0, True
    return 0.0, False


def extract_record_features(record: dict[str, Any], dataset_root: Path) -> dict[str, Any]:
    root = dataset_root.resolve()
    evidence = record["evidence"]
    ocr = json.loads((root / evidence["ocr"]).read_text(encoding="utf-8"))
    asr = json.loads((root / evidence["asr"]).read_text(encoding="utf-8"))
    vlm = json.loads((root / evidence["vlm"]).read_text(encoding="utf-8"))
    ocr_text, ocr_count = _ocr_text_and_count(ocr)
    asr_text, asr_confidence, asr_confidence_available = _asr_text_and_confidence(asr)
    vlm_text = str(vlm.get("raw_model_text", ""))
    ui_score, ui_available = _ui_score(record.get("manual_diagnostic", {}).get("ui_interference"))
    ui_matches = len(_PLATFORM_UI.findall(ocr_text))
    ocr_tokens, asr_tokens, vlm_tokens = _tokens(ocr_text), _tokens(asr_text), _tokens(vlm_text)
    cross_source = (ocr_tokens | asr_tokens) and vlm_tokens
    overlap = len((ocr_tokens | asr_tokens) & vlm_tokens) / len(vlm_tokens) if cross_source else 0.0
    ascii_fraction = sum(char.isascii() and char.isalpha() for char in vlm_text) / max(1, sum(not char.isspace() for char in vlm_text))
    values = (
        ui_score,
        float(ui_available),
        _bounded_length(ocr_text),
        min(1.0, ocr_count / 40.0),
        min(1.0, ui_matches / max(1, ocr_count)),
        _bounded_length(asr_text),
        float(bool(asr_text.strip())),
        asr_confidence,
        float(asr_confidence_available),
        _bounded_length(vlm_text, 96),
        ascii_fraction,
        overlap,
        0.0,
        0.0,
        0.0,
        0.0,
    )
    return {
        "record_id": record["record_id"],
        "source_video_group": record["source_video_group"],
        "split": record["split"],
        "window_id": record["window_id"],
        "feature_names": list(FEATURE_NAMES),
        "features": list(values),
        "feature_provenance": {
            "content_change": "unavailable_from_single_window_artifacts; requires sequential visual encoder",
            "queue_pressure": "unavailable_from_offline_dataset; runtime-only feature",
            "ui_interference": "manual_diagnostic_when_present; otherwise unavailable",
        },
    }


def build_feature_rows(dataset_root: Path) -> Iterable[dict[str, Any]]:
    for record in load_manifest(dataset_root):
        yield extract_record_features(record, dataset_root)
