from __future__ import annotations

import pytest

from zhixingzhixue_hub.quality.modality_gate import (
    ModalityGateError,
    assess_modality_quality,
    create_downgrade_log,
)


def modality_evidence(
    *,
    source: str = "wearable",
    flags: list[str] | None = None,
    connection_status: str = "connected",
    quality: str = "usable",
    alignment_residual_ms: int = 100,
    evidence_uri: str | None = "local://captures/cap-quality-001/segment.bin",
) -> dict[str, object]:
    return {
        "session_id": "ses-quality-001",
        "capture_id": "cap-quality-001",
        "source": source,
        "modality": "eeg_trend" if source == "wearable" else "first_person_video",
        "evidence_uri": evidence_uri,
        "connection_status": connection_status,
        "quality": quality,
        "alignment_residual_ms": alignment_residual_ms,
        "quality_flags": flags or [],
    }


@pytest.mark.parametrize(
    ("source", "quality_flag", "canonical_flag"),
    [
        ("glasses", "occluded", "signal_quality_low"),
        ("wearable", "connection_lost", "evidence_incomplete"),
        ("wearable", "artifact", "signal_quality_low"),
        ("wearable", "time_uncertain", "time_uncertain"),
    ],
)
def test_low_quality_modality_is_excluded_from_fusion_and_recorded(
    source: str, quality_flag: str, canonical_flag: str
) -> None:
    gate = assess_modality_quality(modality_evidence(source=source, flags=[quality_flag]))

    assert gate["status"] == "RECORD_ONLY"
    assert gate["fusion_eligible"] is False
    assert gate["interaction_mode"] == "RECORD_ONLY"
    assert gate["canonical_flags"] == [canonical_flag]
    assert gate["reason_codes"] == [quality_flag]

    log = create_downgrade_log(gate, recorded_at="2026-07-17T21:00:00+08:00")
    assert log["capture_id"] == "cap-quality-001"
    assert log["reasons"] == [quality_flag]
    assert log["canonical_flags"] == [canonical_flag]
    assert log["decision"] == "RECORD_ONLY"
    assert log["recorded_at"] == "2026-07-17T21:00:00+08:00"


def test_usable_wearable_remains_trend_and_quality_assistance_only() -> None:
    gate = assess_modality_quality(modality_evidence())

    assert gate["status"] == "FUSION_ELIGIBLE"
    assert gate["fusion_eligible"] is True
    assert gate["allowed_use"] == "TREND_AND_QUALITY_ASSISTANCE_ONLY"
    assert gate["blocked_operations"] == [
        "ability_claim",
        "attention_diagnosis",
        "medical_claim",
        "psychological_claim",
    ]


def test_disconnected_or_time_uncertain_modality_is_not_fused_and_has_a_stable_quality_log() -> None:
    disconnected = assess_modality_quality(
        modality_evidence(connection_status="disconnected", quality="unavailable", evidence_uri=None)
    )
    assert disconnected["status"] == "EXCLUDED"
    assert disconnected["canonical_flags"] == ["evidence_incomplete"]
    assert disconnected["blocked_operations"] == [
        "fusion",
        "learning_work",
        "semantic_interpretation",
        "window_or_card_creation",
    ]

    time_uncertain = assess_modality_quality(modality_evidence(alignment_residual_ms=2001))
    assert time_uncertain["status"] == "RECORD_ONLY"
    assert time_uncertain["canonical_flags"] == ["time_uncertain"]

    first_log = create_downgrade_log(time_uncertain, recorded_at="2026-07-17T21:00:00+08:00")
    second_log = create_downgrade_log(time_uncertain, recorded_at="2026-07-17T21:00:00+08:00")
    assert first_log["quality_log_id"] == second_log["quality_log_id"]

    low_quality = assess_modality_quality(modality_evidence(flags=["artifact"], quality="degraded"))
    with pytest.raises(ModalityGateError, match="recorded_at_must_include_timezone"):
        create_downgrade_log(low_quality, recorded_at="2026-07-17T21:00:00")
