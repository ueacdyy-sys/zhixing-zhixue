from __future__ import annotations

import pytest

from zhixingzhixue_hub.export.evidence_package import EvidenceExportError, build_evidence_export


def event() -> dict[str, object]:
    return {
        "event_id": "evt-pc-001",
        "session_id": "ses-export-001",
        "task_id": "task-pc-001",
        "source": "pc",
        "modality": "behavior",
        "event_type": "edit",
        "start_ts": "2026-07-17T21:00:00+08:00",
        "end_ts": "2026-07-17T21:02:00+08:00",
        "confidence": 0.9,
        "quality_flags": [],
        "evidence_uri": "local://pc/ses-export-001/events/evt-pc-001.json",
        "privacy_level": "local_only",
        "review_status": "auto",
    }


def card_envelope() -> dict[str, object]:
    return {
        "session_id": "ses-export-001",
        "origin_source": "pc",
        "evidence_refs": ["local://pc/ses-export-001/events/evt-pc-001.json"],
        "card": {
            "card_id": "card-001",
            "window_id": "window-001",
            "facts": ["可回放事实 | evidence_uri=local://pc/ses-export-001/events/evt-pc-001.json"],
            "interpretation": None,
            "counterevidence": [],
            "uncertainty": ["仅有一条事实事件。"],
            "confidence": "low",
            "action": "查看证据边界后自行决定。",
            "review_status": "auto",
            "downgrade_reason": "evidence_incomplete",
        },
    }


def quality_log() -> dict[str, object]:
    return {
        "quality_log_id": "quality-log-001",
        "rule_version": "1.0",
        "session_id": "ses-export-001",
        "capture_id": "cap-wearable-001",
        "source": "wearable",
        "modality": "eeg_trend",
        "decision": "RECORD_ONLY",
        "canonical_flags": ["signal_quality_low"],
        "reasons": ["artifact"],
        "blocked_operations": ["fusion"],
        "evidence_uri": "local://captures/cap-wearable-001/raw.bin",
        "recorded_at": "2026-07-17T21:03:00+08:00",
    }


def test_versioned_evidence_export_contains_session_events_cards_quality_and_local_refs() -> None:
    package = build_evidence_export(
        session_id="ses-export-001",
        events=[event()],
        card_envelopes=[card_envelope()],
        quality_logs=[quality_log()],
        created_at="2026-07-17T21:05:00+08:00",
    )

    assert package["schema_version"] == "1.0"
    assert isinstance(package["export_id"], str) and package["export_id"]
    assert package["session_id"] == "ses-export-001"
    assert package["event_refs"] == ["evt-pc-001"]
    assert package["card_refs"] == ["card-001"]
    assert package["quality_refs"] == ["quality-log-001"]
    assert package["evidence_refs"] == [
        "local://captures/cap-wearable-001/raw.bin",
        "local://pc/ses-export-001/events/evt-pc-001.json",
    ]
    assert package["events"] == [event()]
    assert package["evidence_cards"] == [card_envelope()]
    assert package["quality_logs"] == [quality_log()]
    for forbidden_field in ("teacher_ui", "teacher_login", "teacher_review", "credential"):
        assert forbidden_field not in package


def test_export_rejects_cross_session_records_and_timezone_free_creation_time() -> None:
    foreign_event = event()
    foreign_event["session_id"] = "ses-other-001"
    with pytest.raises(EvidenceExportError, match="event_session_id_must_match_export_session"):
        build_evidence_export(
            session_id="ses-export-001",
            events=[foreign_event],
            card_envelopes=[],
            quality_logs=[],
            created_at="2026-07-17T21:05:00+08:00",
        )

    with pytest.raises(EvidenceExportError, match="created_at_must_include_timezone"):
        build_evidence_export(
            session_id="ses-export-001",
            events=[],
            card_envelopes=[],
            quality_logs=[],
            created_at="2026-07-17T21:05:00",
        )


def test_export_rejects_duplicate_ids_and_nonlocal_card_evidence_reference() -> None:
    duplicate = event()
    duplicate["event_id"] = "evt-pc-001"
    with pytest.raises(EvidenceExportError, match="event_id_must_be_unique"):
        build_evidence_export(
            session_id="ses-export-001",
            events=[event(), duplicate],
            card_envelopes=[],
            quality_logs=[],
            created_at="2026-07-17T21:05:00+08:00",
        )

    invalid_card = card_envelope()
    invalid_card["evidence_refs"] = ["https://example.invalid/evidence"]
    with pytest.raises(EvidenceExportError, match="card_evidence_refs_must_use_local_uris"):
        build_evidence_export(
            session_id="ses-export-001",
            events=[],
            card_envelopes=[invalid_card],
            quality_logs=[],
            created_at="2026-07-17T21:05:00+08:00",
        )
