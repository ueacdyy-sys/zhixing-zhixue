from __future__ import annotations

import pytest

from zhixingzhixue_hub.learning.l0_l4_gate import gate_mobile_learning_offer
from zhixingzhixue_hub.phone.receipt import write_phone_receipt


def single_dwell_candidate() -> dict[str, object]:
    return {
        "capture_id": "cap-phone-dwell-001",
        "status": "CANDIDATE_ONLY",
        "source_mode": "MOBILE_SCREEN_KEYFRAME_OCR",
        "evidence_refs": ["capture://cap-phone-dwell-001/keyframes/0001.jpg"],
        "ocr_excerpt": "一个公开媒体内容线索",
    }


def test_single_dwell_candidate_cannot_generate_practice_quiz_or_forced_task() -> None:
    offer = gate_mobile_learning_offer(single_dwell_candidate())

    assert offer["decision"] == "NO_PRACTICE"
    assert offer["practice"] is None
    assert offer["quiz"] is None
    assert offer["forced_task"] is None
    assert offer["allowed_actions"] == ["save", "watch_later", "dismiss"]


@pytest.mark.parametrize("requested_action", ["practice", "quiz", "forced_task", "microtask"])
def test_single_dwell_candidate_rejects_a_request_for_learning_work(requested_action: str) -> None:
    with pytest.raises(ValueError, match="learning_work_not_allowed_for_candidate"):
        gate_mobile_learning_offer(single_dwell_candidate(), requested_action=requested_action)


@pytest.mark.parametrize("action", ["save", "watch_later", "dismiss"])
def test_student_can_write_a_low_interruption_receipt_for_candidate(action: str) -> None:
    receipt = write_phone_receipt(
        {
            "capture_id": "cap-phone-dwell-001",
            "action": action,
            "recorded_at": "2026-07-17T18:12:30+08:00",
        }
    )

    assert receipt == {
        "status": "RECORDED",
        "capture_id": "cap-phone-dwell-001",
        "evidence_card_id": None,
        "action": action,
        "recorded_at": "2026-07-17T18:12:30+08:00",
    }


def test_receipt_requires_an_evidence_reference_timestamp_and_supported_action() -> None:
    with pytest.raises(ValueError, match="capture_id_or_evidence_card_id_required"):
        write_phone_receipt(
            {"action": "save", "recorded_at": "2026-07-17T18:12:30+08:00"}
        )

    with pytest.raises(ValueError, match="supported_action_required"):
        write_phone_receipt(
            {
                "capture_id": "cap-phone-dwell-001",
                "action": "start_practice",
                "recorded_at": "2026-07-17T18:12:30+08:00",
            }
        )

    with pytest.raises(ValueError, match="exactly_one_evidence_reference_required"):
        write_phone_receipt(
            {
                "capture_id": "cap-phone-dwell-001",
                "evidence_card_id": "card-001",
                "action": "save",
                "recorded_at": "2026-07-17T18:12:30+08:00",
            }
        )

    with pytest.raises(ValueError, match="recorded_at_must_include_timezone"):
        write_phone_receipt(
            {
                "capture_id": "cap-phone-dwell-001",
                "action": "save",
                "recorded_at": "2026-07-17T18:12:30",
            }
        )
