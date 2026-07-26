"""Strict B0-B3 evaluator for real, video-isolated prediction logs."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

from .contracts import InnovationContractError


class Variant(StrEnum):
    B0 = "B0_SINGLE_VLM"
    B1 = "B1_TEMPORAL_EXPERTS"
    B2 = "B2_EVIDENCE_AWARE_CACHE"
    B3 = "B3_EXPERTS_AND_CACHE"


@dataclass(frozen=True)
class Prediction:
    variant: Variant
    record_id: str
    source_video_group: str
    content_correct: bool
    hallucination: bool
    ui_false_positive: bool
    conflict_correct: bool | None
    reject_correct: bool
    latency_ms: float
    gpu_memory_peak_mb: float
    gpu_utilization_pct: float | None
    cache_hit: bool | None
    cache_recompute_ms: float | None
    content_type: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Prediction":
        required = ("variant", "record_id", "source_video_group", "content_correct", "hallucination", "ui_false_positive", "reject_correct", "latency_ms", "gpu_memory_peak_mb", "content_type")
        missing = [name for name in required if name not in value]
        if missing:
            raise InnovationContractError("prediction_missing:" + ",".join(missing))
        return cls(
            variant=Variant(value["variant"]), record_id=str(value["record_id"]), source_video_group=str(value["source_video_group"]),
            content_correct=bool(value["content_correct"]), hallucination=bool(value["hallucination"]), ui_false_positive=bool(value["ui_false_positive"]),
            conflict_correct=None if value.get("conflict_correct") is None else bool(value["conflict_correct"]),
            reject_correct=bool(value["reject_correct"]), latency_ms=float(value["latency_ms"]), gpu_memory_peak_mb=float(value["gpu_memory_peak_mb"]),
            gpu_utilization_pct=None if value.get("gpu_utilization_pct") is None else float(value["gpu_utilization_pct"]),
            cache_hit=None if value.get("cache_hit") is None else bool(value["cache_hit"]),
            cache_recompute_ms=None if value.get("cache_recompute_ms") is None else float(value["cache_recompute_ms"]), content_type=str(value["content_type"]),
        )


def _quantile(values: list[float], level: float) -> float | None:
    if not values:
        return None
    ranked = sorted(values)
    position = (len(ranked) - 1) * level
    left, right = int(position), min(len(ranked) - 1, int(position) + 1)
    return ranked[left] + (ranked[right] - ranked[left]) * (position - left)


def _rate(values: Iterable[bool]) -> float | None:
    items = list(values)
    return sum(items) / len(items) if items else None


def evaluate(predictions: Iterable[Prediction]) -> dict[str, Any]:
    rows = list(predictions)
    grouped: dict[Variant, list[Prediction]] = defaultdict(list)
    for row in rows:
        grouped[row.variant].append(row)
    missing = [variant.value for variant in Variant if variant not in grouped]
    if missing:
        raise InnovationContractError("ablation_variants_missing:" + ",".join(missing))
    reference_ids = {row.record_id for row in grouped[Variant.B0]}
    reference_groups = {row.source_video_group for row in grouped[Variant.B0]}
    if len(reference_groups) < 3:
        raise InnovationContractError("ablation_requires_at_least_three_independent_video_groups")
    for variant, values in grouped.items():
        if {row.record_id for row in values} != reference_ids:
            raise InnovationContractError(f"ablation_record_set_mismatch:{variant.value}")
        if {row.source_video_group for row in values} != reference_groups:
            raise InnovationContractError(f"ablation_video_group_mismatch:{variant.value}")
    results: dict[str, Any] = {}
    for variant, values in grouped.items():
        latency = [row.latency_ms for row in values]
        recompute = [row.cache_recompute_ms for row in values if row.cache_recompute_ms is not None]
        conflict = [row.conflict_correct for row in values if row.conflict_correct is not None]
        by_type: dict[str, dict[str, float | None]] = {}
        for content_type in sorted({row.content_type for row in values}):
            typed = [row for row in values if row.content_type == content_type]
            by_type[content_type] = {"content_accuracy": _rate(row.content_correct for row in typed), "hallucination_rate": _rate(row.hallucination for row in typed)}
        results[variant.value] = {
            "records": len(values),
            "content_accuracy": _rate(row.content_correct for row in values),
            "hallucination_rate": _rate(row.hallucination for row in values),
            "ui_false_positive_rate": _rate(row.ui_false_positive for row in values),
            "conflict_accuracy": _rate(conflict),
            "reject_accuracy": _rate(row.reject_correct for row in values),
            "latency_ms": {"p50": _quantile(latency, 0.50), "p95": _quantile(latency, 0.95), "max": max(latency)},
            "gpu_memory_peak_mb": max(row.gpu_memory_peak_mb for row in values),
            "gpu_utilization_pct_mean": statistics.fmean(row.gpu_utilization_pct for row in values if row.gpu_utilization_pct is not None) if any(row.gpu_utilization_pct is not None for row in values) else None,
            "cache_hit_rate": _rate(row.cache_hit for row in values if row.cache_hit is not None),
            "cache_recompute_ms_mean": statistics.fmean(recompute) if recompute else None,
            "by_content_type": by_type,
        }
    return {"status": "COMPARABLE_ABLATION_COMPLETE", "video_groups": len(reference_groups), "records_per_variant": len(reference_ids), "variants": results}


def load_predictions(path: Path) -> list[Prediction]:
    return [Prediction.from_dict(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
