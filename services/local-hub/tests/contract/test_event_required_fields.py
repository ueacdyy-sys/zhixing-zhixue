import pytest

from zhixingzhixue_hub.core.event_validator import EventValidationError, validate_event


def valid_event() -> dict[str, object]:
    return {
        "event_id": "evt_001",
        "session_id": "ses_001",
        "task_id": "task_001",
        "source": "phone",
        "modality": "media",
        "event_type": "revisit",
        "start_ts": "2026-07-17T14:00:00+08:00",
        "end_ts": "2026-07-17T14:00:15+08:00",
        "confidence": 0.82,
        "quality_flags": [],
        "evidence_uri": "local://capture/ses_001/keyframes/0001.jpg",
        "privacy_level": "local_only",
        "review_status": "auto",
    }


def test_event_with_required_cross_entry_evidence_fields_is_accepted() -> None:
    event = validate_event(valid_event())

    assert event["session_id"] == "ses_001"
    assert event["source"] == "phone"
    assert event["evidence_uri"].startswith("local://")


@pytest.mark.parametrize(
    "field",
    ["session_id", "source", "start_ts", "end_ts", "quality_flags", "evidence_uri"],
)
def test_event_missing_required_evidence_field_is_rejected(field: str) -> None:
    event = valid_event()
    event.pop(field)

    with pytest.raises(EventValidationError, match=field):
        validate_event(event)
