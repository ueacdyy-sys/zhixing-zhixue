"""PC 事实事件的可回放时间轴对齐。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from zhixingzhixue_hub.core.event_validator import EventValidationError, validate_event


class TimelineAlignmentError(ValueError):
    """Raised when an event cannot join the requested PC task timeline."""


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TimelineAlignmentError(f"{field}_required")
    return value.strip()


def _validated_pc_event(task: Mapping[str, Any], raw_event: Mapping[str, Any]) -> dict[str, Any]:
    try:
        event = validate_event(raw_event)
    except EventValidationError as error:
        raise TimelineAlignmentError(str(error)) from error

    if event["session_id"] != _required_text(task, "session_id"):
        raise TimelineAlignmentError("session_id_must_match_timeline_session")
    if event["task_id"] != _required_text(task, "task_id"):
        raise TimelineAlignmentError("task_id_must_match_timeline_task")
    if event["source"] != "pc":
        raise TimelineAlignmentError("source_must_be_pc")
    if not isinstance(event.get("phase_id"), str) or not event["phase_id"].strip():
        raise TimelineAlignmentError("phase_id_required")
    if not event["evidence_uri"].startswith("local://pc/"):
        raise TimelineAlignmentError("evidence_uri_must_use_local_pc_uri")
    return event


def _validated_pc_phase(task: Mapping[str, Any], raw_phase: Mapping[str, Any]) -> dict[str, Any]:
    if _required_text(raw_phase, "session_id") != _required_text(task, "session_id"):
        raise TimelineAlignmentError("phase_session_id_must_match_timeline_session")
    if _required_text(raw_phase, "task_id") != _required_text(task, "task_id"):
        raise TimelineAlignmentError("phase_task_id_must_match_timeline_task")
    if _required_text(raw_phase, "source") != "pc":
        raise TimelineAlignmentError("phase_source_must_be_pc")
    phase_id = _required_text(raw_phase, "phase_id")
    phase_type = _required_text(raw_phase, "phase_type")
    started_at = _required_text(raw_phase, "started_at")
    ended_at = _required_text(raw_phase, "ended_at")
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
    except ValueError as error:
        raise TimelineAlignmentError("phase_time_must_be_iso8601") from error
    if start.tzinfo is None or end.tzinfo is None:
        raise TimelineAlignmentError("phase_time_must_include_timezone")
    if end < start:
        raise TimelineAlignmentError("phase_ended_at_must_not_precede_started_at")
    return {
        "phase_id": phase_id,
        "phase_type": phase_type,
        "started_at": started_at,
        "ended_at": ended_at,
        "start": start,
        "end": end,
    }


def build_pc_timeline(
    task: Mapping[str, Any],
    events: Iterable[Mapping[str, Any]],
    *,
    phases: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Sort PC facts into a replayable, task-scoped timeline.

    It performs no interpretation: every entry is an event with a local replay
    anchor and remains independent from phone collection or platform adapters.
    """
    session_id = _required_text(task, "session_id")
    task_id = _required_text(task, "task_id")
    validated_phases = [_validated_pc_phase(task, phase) for phase in phases]
    phase_by_id = {phase["phase_id"]: phase for phase in validated_phases}
    if len(phase_by_id) != len(validated_phases):
        raise TimelineAlignmentError("phase_id_must_be_unique")

    validated_events = [_validated_pc_event(task, event) for event in events]
    for event in validated_events:
        phase = phase_by_id.get(event["phase_id"])
        if phase is None:
            raise TimelineAlignmentError("phase_id_must_exist_in_timeline")
        event_start = datetime.fromisoformat(event["start_ts"])
        event_end = datetime.fromisoformat(event["end_ts"])
        if event_start < phase["start"] or event_end > phase["end"]:
            raise TimelineAlignmentError("event_must_fit_within_phase_time_range")
    ordered_events = sorted(
        validated_events,
        key=lambda event: (
            datetime.fromisoformat(event["start_ts"]),
            datetime.fromisoformat(event["end_ts"]),
            event["phase_id"],
            event["event_id"],
        ),
    )
    entries = [
        {
            "event_id": event["event_id"],
            "phase_id": event["phase_id"],
            "event_type": event["event_type"],
            "start_ts": event["start_ts"],
            "end_ts": event["end_ts"],
            "confidence": event["confidence"],
            "quality_flags": list(event["quality_flags"]),
            "replay_uri": event["evidence_uri"],
        }
        for event in ordered_events
    ]
    return {
        "session_id": session_id,
        "task_id": task_id,
        "source": "pc",
        "phases": [
            {
                "phase_id": phase["phase_id"],
                "phase_type": phase["phase_type"],
                "started_at": phase["started_at"],
                "ended_at": phase["ended_at"],
            }
            for phase in validated_phases
        ],
        "entries": entries,
    }
