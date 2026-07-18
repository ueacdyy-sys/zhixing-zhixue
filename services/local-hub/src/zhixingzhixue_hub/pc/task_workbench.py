"""PC 学习任务的独立入口。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from zhixingzhixue_hub.core.event_validator import EventValidationError, validate_event


class PCTaskValidationError(ValueError):
    """Raised when a PC task lacks its own traceability boundary."""


def _required_text(task: Mapping[str, Any], field: str) -> str:
    value = task.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PCTaskValidationError(f"{field}_required")
    return value.strip()


def _timezone_timestamp(task: Mapping[str, Any], field: str) -> str:
    value = _required_text(task, field)
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as error:
        raise PCTaskValidationError(f"{field}_must_be_iso8601") from error
    if timestamp.tzinfo is None:
        raise PCTaskValidationError(f"{field}_must_include_timezone")
    return value


def _knowledge_tags(task: Mapping[str, Any]) -> list[str]:
    tags = task.get("knowledge_tags")
    if not isinstance(tags, list) or not tags:
        raise PCTaskValidationError("knowledge_tags_required")
    if not all(isinstance(tag, str) and tag.strip() for tag in tags):
        raise PCTaskValidationError("knowledge_tags_must_be_a_non_empty_string_list")
    return [tag.strip() for tag in tags]


def create_pc_task_session(task: Mapping[str, Any]) -> dict[str, Any]:
    """Create an active PC learning task without a phone prerequisite."""
    source = _required_text(task, "source")
    if source != "pc":
        raise PCTaskValidationError("source_must_be_pc")

    return {
        "session_id": _required_text(task, "session_id"),
        "task_id": _required_text(task, "task_id"),
        "task_type": _required_text(task, "task_type"),
        "goal": _required_text(task, "goal"),
        "knowledge_tags": _knowledge_tags(task),
        "started_at": _timezone_timestamp(task, "started_at"),
        "source": "pc",
        "entry_point": "PC_INDEPENDENT",
        "status": "ACTIVE",
    }


def _parse_timezone_timestamp(payload: Mapping[str, Any], field: str) -> datetime:
    value = _timezone_timestamp(payload, field)
    return datetime.fromisoformat(value)


def _require_task_match(task: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    task_id = _required_text(task, "task_id")
    if _required_text(payload, "task_id") != task_id:
        raise PCTaskValidationError("task_id_must_match_active_pc_task")
    return task_id


def add_pc_task_phase(task: Mapping[str, Any], phase: Mapping[str, Any]) -> dict[str, Any]:
    """Add a time-bounded phase to an existing PC task without external prerequisites."""
    task_id = _require_task_match(task, phase)
    if _required_text(phase, "source") != "pc":
        raise PCTaskValidationError("source_must_be_pc")
    started_at = _timezone_timestamp(phase, "started_at")
    ended_at = phase.get("ended_at")
    if ended_at is not None:
        start = _parse_timezone_timestamp(phase, "started_at")
        end = _parse_timezone_timestamp(phase, "ended_at")
        if end < start:
            raise PCTaskValidationError("ended_at_must_not_precede_started_at")
    return {
        "phase_id": _required_text(phase, "phase_id"),
        "session_id": _required_text(task, "session_id"),
        "task_id": task_id,
        "phase_type": _required_text(phase, "phase_type"),
        "started_at": started_at,
        "ended_at": ended_at,
        "source": "pc",
    }


def record_pc_learning_behavior(
    task: Mapping[str, Any], behavior: Mapping[str, Any]
) -> dict[str, Any]:
    """Record a PC-originated, replayable behavior without inferring learner state."""
    try:
        event = validate_event(behavior)
    except EventValidationError as error:
        raise PCTaskValidationError(str(error)) from error

    task_id = _require_task_match(task, event)
    if event["session_id"] != _required_text(task, "session_id"):
        raise PCTaskValidationError("session_id_must_match_active_pc_task")
    if event["source"] != "pc":
        raise PCTaskValidationError("source_must_be_pc")
    if event["event_type"] not in {
        "read",
        "seek",
        "search",
        "edit",
        "pause",
        "revisit",
        "submit",
        "self_report",
    }:
        raise PCTaskValidationError("event_type_not_allowed_for_pc_learning_behavior")

    evidence_uri = _required_text(event, "evidence_uri")
    if not evidence_uri.startswith("local://pc/"):
        raise PCTaskValidationError("evidence_uri_must_use_local_pc_uri")
    return {
        "event_id": _required_text(event, "event_id"),
        "session_id": _required_text(event, "session_id"),
        "task_id": task_id,
        "phase_id": _required_text(event, "phase_id"),
        "modality": _required_text(event, "modality"),
        "event_type": _required_text(event, "event_type"),
        "start_ts": _timezone_timestamp(event, "start_ts"),
        "end_ts": _timezone_timestamp(event, "end_ts"),
        "confidence": event["confidence"],
        "quality_flags": list(event["quality_flags"]),
        "evidence_uri": evidence_uri,
        "privacy_level": _required_text(event, "privacy_level"),
        "review_status": _required_text(event, "review_status"),
        "source": "pc",
        "learning_diagnosis": None,
        "interest_conclusion": None,
        "interpretation": None,
    }


def list_session_evidence_cards(
    task: Mapping[str, Any], cards: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Expose existing same-session cards to the PC workbench as a read model."""
    session_id = _required_text(task, "session_id")
    visible_cards: list[dict[str, Any]] = []
    for envelope in cards:
        if envelope.get("origin_source") != "phone" or envelope.get("session_id") != session_id:
            continue
        card = envelope.get("card")
        if isinstance(card, Mapping):
            visible_cards.append(dict(card))
    return visible_cards
