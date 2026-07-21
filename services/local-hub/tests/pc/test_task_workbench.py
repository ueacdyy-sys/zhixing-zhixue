from __future__ import annotations

from zhixingzhixue_hub.pc.task_workbench import (
    add_pc_task_phase,
    create_pc_task_session,
    list_session_evidence_cards,
    record_pc_learning_behavior,
)


def active_pc_task() -> dict[str, object]:
    return create_pc_task_session(
        {
            "session_id": "ses-pc-001",
            "task_id": "task-pc-001",
            "task_type": "video_course",
            "goal": "完成算法课程第 3 节并整理关键概念。",
            "knowledge_tags": ["算法"],
            "started_at": "2026-07-17T19:30:00+08:00",
            "source": "pc",
        }
    )


def test_pc_task_records_its_own_phase_and_replayable_learning_behavior() -> None:
    task = active_pc_task()
    phase = add_pc_task_phase(
        task,
        {
            "phase_id": "phase-pc-001",
            "task_id": "task-pc-001",
            "phase_type": "watch",
            "started_at": "2026-07-17T19:30:00+08:00",
            "ended_at": "2026-07-17T19:45:00+08:00",
            "source": "pc",
        },
    )
    behavior = record_pc_learning_behavior(
        task,
        {
            "event_id": "evt-pc-001",
            "task_id": "task-pc-001",
            "phase_id": "phase-pc-001",
            "session_id": "ses-pc-001",
            "source": "pc",
            "modality": "behavior",
            "event_type": "seek",
            "start_ts": "2026-07-17T19:34:00+08:00",
            "end_ts": "2026-07-17T19:34:03+08:00",
            "confidence": 0.9,
            "quality_flags": [],
            "evidence_uri": "local://pc/ses-pc-001/events/evt-pc-001.json",
            "privacy_level": "local_only",
            "review_status": "auto",
        },
    )

    assert phase["source"] == "pc"
    assert phase["task_id"] == "task-pc-001"
    assert behavior["source"] == "pc"
    assert behavior["evidence_uri"].startswith("local://pc/")
    assert behavior["learning_diagnosis"] is None
    assert behavior["interpretation"] is None
    assert "practice" not in behavior


def test_pc_can_read_existing_phone_evidence_cards_for_the_same_session_without_phone_prerequisite() -> None:
    task = active_pc_task()
    phone_card = {
        "card_id": "card-phone-001",
        "window_id": "window-phone-001",
        "facts": ["可回放的公开媒体事实"],
        "interpretation": None,
        "counterevidence": [],
        "uncertainty": ["需要学生确认"],
        "confidence": "low",
        "action": "查看后自行决定。",
        "review_status": "auto",
        "downgrade_reason": "evidence_incomplete",
    }
    cards = [
        {"origin_source": "phone", "session_id": "ses-pc-001", "card": phone_card},
        {"origin_source": "phone", "session_id": "ses-other-001", "card": {"card_id": "card-other-001"}},
        {"origin_source": "pc", "session_id": "ses-pc-001", "card": {"card_id": "card-pc-001"}},
    ]

    visible = list_session_evidence_cards(task, cards)

    assert visible == [phone_card]
    assert visible[0] is not phone_card
    assert list_session_evidence_cards(task, []) == []
