from __future__ import annotations

from zhixingzhixue_hub.validation_chains import run_pc_validation_chain, run_phone_validation_chain


def test_phone_public_media_chain_produces_traceable_card_and_voluntary_receipt() -> None:
    result = run_phone_validation_chain()

    assert result["chain"] == "phone_public_media"
    assert result["session_status"] == "SEMANTIC_ANALYSIS_PENDING"
    assert result["card"]["downgrade_reason"] is None
    assert result["receipt"]["status"] == "RECORDED"
    assert result["receipt"]["action"] == "save"
    assert result["evidence_refs"] == ["local://captures/cap-validation-phone-001/segment.mkv"]


def test_pc_learning_chain_produces_timeline_candidate_quality_log_and_export_without_teacher_state() -> None:
    result = run_pc_validation_chain()

    assert result["chain"] == "pc_independent_learning"
    assert result["task"]["entry_point"] == "PC_INDEPENDENT"
    assert [entry["event_id"] for entry in result["timeline"]["entries"]] == ["evt-validation-pc-001"]
    assert result["candidate"]["status"] == "CANDIDATE_ONLY"
    assert result["quality_log"]["decision"] == "RECORD_ONLY"
    assert result["card"]["interpretation"] is None
    assert result["card"]["confidence"] == "low"
    assert result["export"]["schema_version"] == "1.0"
    assert result["export"]["card_refs"] == [result["card"]["card_id"]]
    assert result["export"]["quality_refs"] == [result["quality_log"]["quality_log_id"]]
    assert "teacher_ui" not in result["export"]
