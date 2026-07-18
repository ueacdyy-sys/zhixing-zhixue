"""低质量模态的保守融合门控。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5


class ModalityGateError(ValueError):
    """Raised when a quality report cannot be recorded safely."""


ALLOWED_SOURCES = {"phone", "pc", "glasses", "wearable"}
CANONICAL_FLAG_ORDER = ("signal_quality_low", "time_uncertain", "evidence_incomplete")
WEARABLE_BLOCKED_OPERATIONS = [
    "ability_claim",
    "attention_diagnosis",
    "medical_claim",
    "psychological_claim",
]


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ModalityGateError(f"{field}_required")
    return value.strip()


def _raw_flags(evidence: Mapping[str, Any]) -> list[str]:
    flags = evidence.get("quality_flags", [])
    if not isinstance(flags, list) or not all(isinstance(flag, str) and flag.strip() for flag in flags):
        raise ModalityGateError("quality_flags_must_be_a_string_list")
    return sorted({flag.strip() for flag in flags})


def _local_evidence_uri(evidence: Mapping[str, Any]) -> str | None:
    value = evidence.get("evidence_uri")
    return value if isinstance(value, str) and value.startswith("local://") else None


def _numeric_residual(evidence: Mapping[str, Any], field: str) -> float | None:
    value = evidence.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _canonical_flags(reason_codes: list[str]) -> list[str]:
    reasons = set(reason_codes)
    canonical: set[str] = set()
    if reasons & {"occluded", "artifact", "low_snr", "dropped_frames", "quality_degraded", "quality_unknown"}:
        canonical.add("signal_quality_low")
    if reasons & {"alignment_residual_exceeded", "sync_marker_residual_exceeded", "time_uncertain"}:
        canonical.add("time_uncertain")
    if reasons & {"connection_lost", "connection_disconnected", "evidence_missing", "quality_unavailable"}:
        canonical.add("evidence_incomplete")
    return [flag for flag in CANONICAL_FLAG_ORDER if flag in canonical]


def assess_modality_quality(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Classify one modality without making a learner-state inference.

    `RECORD_ONLY` keeps replayable raw evidence but blocks fusion and explanations.
    `EXCLUDED` keeps only its quality log because the evidence itself is unusable.
    """
    source = _required_text(evidence, "source")
    if source not in ALLOWED_SOURCES:
        raise ModalityGateError("source_not_supported")
    connection_status = evidence.get("connection_status")
    quality = evidence.get("quality")
    reasons = _raw_flags(evidence)
    evidence_uri = _local_evidence_uri(evidence)
    alignment_residual = _numeric_residual(evidence, "alignment_residual_ms")
    sync_residual = _numeric_residual(evidence, "sync_marker_residual_ms")

    if connection_status == "disconnected":
        reasons.append("connection_disconnected")
    elif connection_status != "connected":
        reasons.append("connection_unknown")
    if quality == "unavailable":
        reasons.append("quality_unavailable")
    elif quality == "degraded":
        reasons.append("quality_degraded")
    elif quality != "usable":
        reasons.append("quality_unknown")
    if evidence_uri is None:
        reasons.append("evidence_missing")
    if alignment_residual is None or alignment_residual > 2000:
        reasons.append("alignment_residual_exceeded")
    if sync_residual is not None and sync_residual > 1000:
        reasons.append("sync_marker_residual_exceeded")

    reason_codes = sorted(set(reasons))
    canonical_flags = _canonical_flags(reason_codes)
    base = {
        "session_id": _required_text(evidence, "session_id"),
        "capture_id": _required_text(evidence, "capture_id"),
        "source": source,
        "modality": _required_text(evidence, "modality"),
        "evidence_uri": evidence_uri,
        "reason_codes": reason_codes,
        "canonical_flags": canonical_flags,
        "rule_version": "1.0",
    }
    wearable_blocks = WEARABLE_BLOCKED_OPERATIONS if source == "wearable" else []

    if {"connection_disconnected", "quality_unavailable", "evidence_missing"} & set(reason_codes):
        return {
            **base,
            "status": "EXCLUDED",
            "fusion_eligible": False,
            "interaction_mode": "LOG_ONLY",
            "blocked_operations": [
                "fusion",
                "learning_work",
                "semantic_interpretation",
                "window_or_card_creation",
            ],
        }
    if canonical_flags:
        return {
            **base,
            "status": "RECORD_ONLY",
            "fusion_eligible": False,
            "interaction_mode": "RECORD_ONLY",
            "blocked_operations": ["fusion", "learning_work", "semantic_interpretation", *wearable_blocks],
        }

    allowed_use = (
        "TREND_AND_QUALITY_ASSISTANCE_ONLY" if source == "wearable" else "FACTUAL_EVIDENCE_ONLY"
    )
    return {
        **base,
        "status": "FUSION_ELIGIBLE",
        "fusion_eligible": True,
        "interaction_mode": "FUSION_ALLOWED",
        "allowed_use": allowed_use,
        "blocked_operations": wearable_blocks,
    }


def create_downgrade_log(gate: Mapping[str, Any], *, recorded_at: str) -> dict[str, Any]:
    """Create a deterministic, time-bound quality decision log."""
    try:
        timestamp = datetime.fromisoformat(recorded_at)
    except ValueError as error:
        raise ModalityGateError("recorded_at_must_be_iso8601") from error
    if timestamp.tzinfo is None:
        raise ModalityGateError("recorded_at_must_include_timezone")
    decision = gate.get("status")
    if decision not in {"FUSION_ELIGIBLE", "RECORD_ONLY", "EXCLUDED"}:
        raise ModalityGateError("quality_decision_required")
    reasons = gate.get("reason_codes")
    canonical_flags = gate.get("canonical_flags")
    if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
        raise ModalityGateError("reason_codes_must_be_a_string_list")
    if not isinstance(canonical_flags, list) or not all(isinstance(flag, str) for flag in canonical_flags):
        raise ModalityGateError("canonical_flags_must_be_a_string_list")

    capture_id = _required_text(gate, "capture_id")
    rule_version = _required_text(gate, "rule_version")
    log_seed = "|".join((capture_id, rule_version, decision, recorded_at, *reasons))
    return {
        "quality_log_id": str(uuid5(NAMESPACE_URL, log_seed)),
        "rule_version": rule_version,
        "session_id": _required_text(gate, "session_id"),
        "capture_id": capture_id,
        "source": _required_text(gate, "source"),
        "modality": _required_text(gate, "modality"),
        "decision": decision,
        "canonical_flags": list(canonical_flags),
        "reasons": list(reasons),
        "blocked_operations": list(gate.get("blocked_operations", [])),
        "evidence_uri": gate.get("evidence_uri"),
        "recorded_at": recorded_at,
    }
