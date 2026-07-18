from __future__ import annotations

import pytest

from zhixingzhixue_hub.pc.task_workbench import PCTaskValidationError, create_pc_task_session


def pc_video_course_task() -> dict[str, object]:
    return {
        "session_id": "ses-pc-001",
        "task_id": "task-pc-001",
        "task_type": "video_course",
        "goal": "完成算法课程第 3 节并整理关键概念。",
        "knowledge_tags": ["算法", "动态规划"],
        "started_at": "2026-07-17T19:30:00+08:00",
        "source": "pc",
    }


def test_pc_can_start_a_learning_task_without_any_phone_session_or_capture() -> None:
    task = create_pc_task_session(pc_video_course_task())

    assert task["task_id"] == "task-pc-001"
    assert task["session_id"] == "ses-pc-001"
    assert task["entry_point"] == "PC_INDEPENDENT"
    assert task["status"] == "ACTIVE"
    assert task["source"] == "pc"
    assert "phone_session_id" not in task
    assert "phone_capture_id" not in task
    assert "evidence_card" not in task
    assert "interpretation" not in task
    assert "practice" not in task


@pytest.mark.parametrize("field", ["session_id", "task_id", "task_type", "goal", "knowledge_tags", "started_at"])
def test_pc_task_requires_its_own_traceability_fields(field: str) -> None:
    task = pc_video_course_task()
    task.pop(field)

    with pytest.raises(PCTaskValidationError, match=field):
        create_pc_task_session(task)


def test_pc_task_rejects_non_pc_source_and_timezone_free_start_time() -> None:
    wrong_source = pc_video_course_task()
    wrong_source["source"] = "phone"
    with pytest.raises(PCTaskValidationError, match="source"):
        create_pc_task_session(wrong_source)

    timezone_free = pc_video_course_task()
    timezone_free["started_at"] = "2026-07-17T19:30:00"
    with pytest.raises(PCTaskValidationError, match="started_at"):
        create_pc_task_session(timezone_free)
