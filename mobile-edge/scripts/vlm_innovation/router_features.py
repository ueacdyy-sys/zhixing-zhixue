"""Assemble complete Router vectors without inventing missing runtime signals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import InnovationContractError
from .dataset import write_jsonl


FEATURE_NAMES = (
    "ui_interference", "ui_interference_available", "content_change", "content_change_available",
    "ocr_density", "ocr_ui_like_ratio", "asr_text_available", "asr_timestamped_ratio",
    "cross_modal_overlap", "cross_modal_conflict_available", "evidence_coverage", "evidence_coverage_available",
    "visual_history_quality", "visual_history_quality_available", "ocr_history_quality", "ocr_history_quality_available",
    "asr_history_quality", "asr_history_quality_available", "cache_hit", "cache_state_available",
    "cache_quality", "cache_quality_available", "gpu_budget_remaining", "gpu_budget_available",
    "queue_pressure", "queue_pressure_available",
)


@dataclass(frozen=True)
class RuntimeSignals:
    """Signals emitted by the live worker/Cache Manager for the same window."""

    evidence_coverage: float | None = None
    visual_history_quality: float | None = None
    ocr_history_quality: float | None = None
    asr_history_quality: float | None = None
    cache_hit: bool | None = None
    cache_quality: float | None = None
    gpu_budget_remaining: float | None = None
    queue_pressure: float | None = None

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if value is not None and name != "cache_hit" and not 0.0 <= float(value) <= 1.0:
                raise InnovationContractError(f"runtime_signal_outside_unit_interval:{name}")


def _value(value: float | None) -> tuple[float, float]:
    return (0.0, 0.0) if value is None else (float(value), 1.0)


def vector_from_experts(row: dict[str, Any], runtime: RuntimeSignals | None = None) -> dict[str, Any]:
    runtime = runtime or RuntimeSignals()
    experts = row.get("experts")
    if not isinstance(experts, dict):
        raise InnovationContractError("expert_row_missing_experts")
    visual, ocr, asr, ui, cross = (experts.get(name, {}) for name in ("visual_scene", "ocr_screen_text", "asr_semantic", "ui_noise", "cross_modal_consistency"))
    change = visual.get("content_change") if visual.get("available") else None
    ui_value = ui.get("ui_interference_estimate") if ui.get("ui_interference_available") else None
    overlap = cross.get("ocr_asr_vlm_token_overlap") if cross.get("has_cross_modal_evidence") else None
    evidence = runtime.evidence_coverage
    values = [
        *_value(ui_value), *_value(change), min(1.0, float(ocr.get("detections", 0)) / 40.0), float(ocr.get("ui_like_detection_ratio", 0.0)),
        float(bool(asr.get("text_available"))), float(asr.get("timestamped_segment_ratio", 0.0)),
        *_value(overlap), *_value(evidence), *_value(runtime.visual_history_quality), *_value(runtime.ocr_history_quality),
        *_value(runtime.asr_history_quality), (0.0 if runtime.cache_hit is None else float(runtime.cache_hit)), float(runtime.cache_hit is not None),
        *_value(runtime.cache_quality), *_value(runtime.gpu_budget_remaining), *_value(runtime.queue_pressure),
    ]
    if len(values) != len(FEATURE_NAMES):
        raise InnovationContractError("router_feature_layout_mismatch")
    return {
        "record_id": row["record_id"], "source_video_group": row["source_video_group"], "split": row["split"], "window_id": row["window_id"],
        "feature_names": list(FEATURE_NAMES), "features": values,
        "runtime_signal_boundary": "zero with availability=0 denotes unavailable, never a measured zero",
    }


def export_router_features(expert_path: Path, output: Path, runtime_path: Path | None = None) -> int:
    expert_rows = [json.loads(line) for line in expert_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    runtime_by_record: dict[str, RuntimeSignals] = {}
    if runtime_path is not None:
        for line in runtime_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                raw = json.loads(line)
                runtime_by_record[str(raw["record_id"])] = RuntimeSignals(**{key: raw.get(key) for key in RuntimeSignals.__dataclass_fields__})
    rows = [vector_from_experts(row, runtime_by_record.get(str(row["record_id"]))) for row in expert_rows]
    write_jsonl(rows, output)
    return len(rows)
