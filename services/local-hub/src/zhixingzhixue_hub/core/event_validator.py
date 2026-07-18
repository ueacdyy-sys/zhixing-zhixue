"""跨入口事件的纯领域验证。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any


class EventValidationError(ValueError):
    """Raised when an event cannot safely enter the evidence timeline."""


REQUIRED_FIELDS = (
    "event_id",
    "session_id",
    "task_id",
    "source",
    "modality",
    "event_type",
    "start_ts",
    "end_ts",
    "confidence",
    "quality_flags",
    "evidence_uri",
    "privacy_level",
    "review_status",
)
ALLOWED_SOURCES = {"pc", "phone", "glasses", "wearable"}


def _required_text(event: Mapping[str, Any], field: str) -> str:
    value = event.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EventValidationError(f"{field} is required")
    return value


def _parse_timestamp(event: Mapping[str, Any], field: str) -> datetime:
    value = _required_text(event, field)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise EventValidationError(f"{field} must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise EventValidationError(f"{field} must include timezone")
    return parsed


def validate_event(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the immutable evidence envelope before any timeline processing."""
    event = dict(payload)
    for field in REQUIRED_FIELDS:
        if field not in event:
            raise EventValidationError(f"{field} is required")

    for field in ("event_id", "session_id", "task_id", "modality", "event_type"):
        _required_text(event, field)

    source = _required_text(event, "source")
    if source not in ALLOWED_SOURCES:
        raise EventValidationError("source is not supported")

    start = _parse_timestamp(event, "start_ts")
    end = _parse_timestamp(event, "end_ts")
    if end < start:
        raise EventValidationError("end_ts must not precede start_ts")

    confidence = event["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise EventValidationError("confidence must be numeric")
    if not 0 <= float(confidence) <= 1:
        raise EventValidationError("confidence must be within [0, 1]")

    quality_flags = event["quality_flags"]
    if not isinstance(quality_flags, list) or not all(
        isinstance(flag, str) and flag.strip() for flag in quality_flags
    ):
        raise EventValidationError("quality_flags must be a string list")

    evidence_uri = _required_text(event, "evidence_uri")
    if not evidence_uri.startswith("local://"):
        raise EventValidationError("evidence_uri must use local://")

    _required_text(event, "privacy_level")
    _required_text(event, "review_status")
    return event
