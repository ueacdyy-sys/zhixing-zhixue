from __future__ import annotations

import pytest

from zhixingzhixue_hub.analysis.fast_path import build_fast_path_candidate
from zhixingzhixue_hub.timeline.aligner import TimelineAlignmentError, build_pc_timeline


def pc_task() -> dict[str, str]:
    return {"session_id": "ses-pc-001", "task_id": "task-pc-001"}


def pc_phase() -> dict[str, str]:
    return {
        "phase_id": "phase-pc-001",
        "session_id": "ses-pc-001",
        "task_id": "task-pc-001",
        "phase_type": "watch_and_note",
        "started_at": "2026-07-17T20:00:00+08:00",
        "ended_at": "2026-07-17T21:00:00+08:00",
        "source": "pc",
    }

def pc_event(
    *, event_id: str, event_type: str, start_ts: str, end_ts: str
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "session_id": "ses-pc-001",
        "task_id": "task-pc-001",
        "phase_id": "phase-pc-001",
        "source": "pc",
        "modality": "behavior",
        "event_type": event_type,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "confidence": 0.9,
        "quality_flags": [],
        "evidence_uri": f"local://pc/ses-pc-001/events/{event_id}.json",
        "privacy_level": "local_only",
        "review_status": "auto",
    }


def test_pc_course_search_and_writing_events_are_sorted_into_replayable_timeline() -> None:
    timeline = build_pc_timeline(
        pc_task(),
        [
            pc_event(
                event_id="evt-write-001",
                event_type="edit",
                start_ts="2026-07-17T20:10:00+08:00",
                end_ts="2026-07-17T20:12:00+08:00",
            ),
            pc_event(
                event_id="evt-course-001",
                event_type="seek",
                start_ts="2026-07-17T20:00:00+08:00",
                end_ts="2026-07-17T20:01:00+08:00",
            ),
            pc_event(
                event_id="evt-search-001",
                event_type="search",
                start_ts="2026-07-17T20:04:00+08:00",
                end_ts="2026-07-17T20:05:00+08:00",
            ),
        ],
        phases=[pc_phase()],
    )

    assert timeline["session_id"] == "ses-pc-001"
    assert timeline["task_id"] == "task-pc-001"
    assert [item["event_id"] for item in timeline["entries"]] == [
        "evt-course-001",
        "evt-search-001",
        "evt-write-001",
    ]
    assert all(item["replay_uri"].startswith("local://pc/") for item in timeline["entries"])
    assert timeline["entries"][0]["confidence"] == 0.9
    assert "interpretation" not in timeline


def test_pc_timeline_rejects_cross_task_or_non_pc_event() -> None:
    cross_task = pc_event(
        event_id="evt-other-task-001",
        event_type="read",
        start_ts="2026-07-17T20:00:00+08:00",
        end_ts="2026-07-17T20:01:00+08:00",
    )
    cross_task["task_id"] = "task-other-001"

    with pytest.raises(TimelineAlignmentError, match="task_id_must_match_timeline_task"):
        build_pc_timeline(pc_task(), [cross_task], phases=[pc_phase()])

    non_pc = pc_event(
        event_id="evt-phone-001",
        event_type="read",
        start_ts="2026-07-17T20:00:00+08:00",
        end_ts="2026-07-17T20:01:00+08:00",
    )
    non_pc["source"] = "phone"
    with pytest.raises(TimelineAlignmentError, match="source_must_be_pc"):
        build_pc_timeline(pc_task(), [non_pc], phases=[pc_phase()])


def test_pc_timeline_rejects_event_outside_its_phase_time_range() -> None:
    outside_phase = pc_event(
        event_id="evt-outside-phase-001",
        event_type="edit",
        start_ts="2026-07-17T21:01:00+08:00",
        end_ts="2026-07-17T21:02:00+08:00",
    )

    with pytest.raises(TimelineAlignmentError, match="event_must_fit_within_phase_time_range"):
        build_pc_timeline(pc_task(), [outside_phase], phases=[pc_phase()])


def test_fast_path_keeps_pc_timeline_as_candidate_without_conclusion_card_or_learning_work() -> None:
    timeline = build_pc_timeline(
        pc_task(),
        [
            pc_event(
                event_id="evt-course-001",
                event_type="seek",
                start_ts="2026-07-17T20:00:00+08:00",
                end_ts="2026-07-17T20:01:00+08:00",
            )
        ],
        phases=[pc_phase()],
    )

    candidate = build_fast_path_candidate(timeline)

    assert candidate["status"] == "CANDIDATE_ONLY"
    assert candidate["source_mode"] == "PC_TIMELINE_FAST_PATH"
    assert candidate["candidate_id"] == build_fast_path_candidate(timeline)["candidate_id"]
    assert candidate["evidence_refs"] == ["local://pc/ses-pc-001/events/evt-course-001.json"]
    for forbidden_field in (
        "learning_diagnosis",
        "interest_conclusion",
        "knowledge_conclusion",
        "evidence_card",
        "facts",
        "action",
        "practice",
        "quiz",
        "forced_task",
    ):
        assert forbidden_field not in candidate
    assert candidate["requires_slow_path"] is True
