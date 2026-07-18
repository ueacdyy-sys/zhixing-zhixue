"""构建可版本化、与教师 UI 解耦的本地证据导出包。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from zhixingzhixue_hub.core.event_validator import EventValidationError, validate_event


class EvidenceExportError(ValueError):
    """Raised when a record cannot safely join an evidence export package."""


SCHEMA_VERSION = "1.0"
CARD_REQUIRED_FIELDS = {
    "card_id",
    "window_id",
    "facts",
    "interpretation",
    "counterevidence",
    "uncertainty",
    "confidence",
    "action",
    "review_status",
    "downgrade_reason",
}
EVENT_EXPORT_FIELDS = (
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
QUALITY_LOG_EXPORT_FIELDS = (
    "quality_log_id",
    "rule_version",
    "session_id",
    "capture_id",
    "source",
    "modality",
    "decision",
    "canonical_flags",
    "reasons",
    "blocked_operations",
    "evidence_uri",
    "recorded_at",
)


def _required_text(payload: Mapping[str, Any], field: str, error_prefix: str = "") -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceExportError(f"{error_prefix}{field}_required")
    return value.strip()


def _timezone_timestamp(value: str) -> str:
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as error:
        raise EvidenceExportError("created_at_must_be_iso8601") from error
    if timestamp.tzinfo is None:
        raise EvidenceExportError("created_at_must_include_timezone")
    return value


def _validate_events(session_id: str, events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    for raw_event in events:
        try:
            event = validate_event(raw_event)
        except EventValidationError as error:
            raise EvidenceExportError(str(error)) from error
        if event["session_id"] != session_id:
            raise EvidenceExportError("event_session_id_must_match_export_session")
        if event["event_id"] in event_ids:
            raise EvidenceExportError("event_id_must_be_unique")
        event_ids.add(event["event_id"])
        validated.append({field: event[field] for field in EVENT_EXPORT_FIELDS})
    return validated


def _validate_cards(session_id: str, envelopes: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    card_ids: set[str] = set()
    for envelope in envelopes:
        if envelope.get("session_id") != session_id:
            raise EvidenceExportError("card_session_id_must_match_export_session")
        card = envelope.get("card")
        if not isinstance(card, Mapping) or not CARD_REQUIRED_FIELDS.issubset(card):
            raise EvidenceExportError("complete_evidence_card_required")
        _required_text(card, "card_id", "card_")
        if card["card_id"] in card_ids:
            raise EvidenceExportError("card_id_must_be_unique")
        card_ids.add(card["card_id"])
        facts = card.get("facts")
        if not isinstance(facts, list) or not all(isinstance(fact, str) and fact.strip() for fact in facts):
            raise EvidenceExportError("card_facts_must_be_a_non_empty_string_list")
        evidence_refs = envelope.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs or not all(
            isinstance(uri, str) and uri.startswith("local://") for uri in evidence_refs
        ):
            raise EvidenceExportError("card_evidence_refs_must_use_local_uris")
        origin_source = _required_text(envelope, "origin_source", "card_")
        validated.append(
            {
                "session_id": session_id,
                "origin_source": origin_source,
                "evidence_refs": sorted(set(evidence_refs)),
                "card": dict(card),
            }
        )
    return validated


def _validate_quality_logs(session_id: str, logs: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    log_ids: set[str] = set()
    for log in logs:
        if log.get("session_id") != session_id:
            raise EvidenceExportError("quality_log_session_id_must_match_export_session")
        log_id = _required_text(log, "quality_log_id", "quality_log_")
        if log_id in log_ids:
            raise EvidenceExportError("quality_log_id_must_be_unique")
        log_ids.add(log_id)
        _required_text(log, "decision", "quality_log_")
        evidence_uri = log.get("evidence_uri")
        if evidence_uri is not None and (
            not isinstance(evidence_uri, str) or not evidence_uri.startswith("local://")
        ):
            raise EvidenceExportError("quality_log_evidence_uri_must_use_local_uri_or_be_null")
        validated.append({field: log.get(field) for field in QUALITY_LOG_EXPORT_FIELDS})
    return validated


def _evidence_refs(
    events: Iterable[Mapping[str, Any]], cards: Iterable[Mapping[str, Any]], logs: Iterable[Mapping[str, Any]]
) -> list[str]:
    refs: set[str] = {
        event["evidence_uri"]
        for event in events
        if isinstance(event.get("evidence_uri"), str) and event["evidence_uri"].startswith("local://")
    }
    for envelope in cards:
        refs.update(envelope["evidence_refs"])
    for log in logs:
        uri = log.get("evidence_uri")
        if isinstance(uri, str) and uri.startswith("local://"):
            refs.add(uri)
    return sorted(refs)


def build_evidence_export(
    *,
    session_id: str,
    events: Iterable[Mapping[str, Any]],
    card_envelopes: Iterable[Mapping[str, Any]],
    quality_logs: Iterable[Mapping[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    """Create a versioned evidence package without a teacher UI dependency."""
    export_session_id = _required_text({"session_id": session_id}, "session_id")
    created_at = _timezone_timestamp(created_at)
    validated_events = _validate_events(export_session_id, events)
    validated_cards = _validate_cards(export_session_id, card_envelopes)
    validated_quality_logs = _validate_quality_logs(export_session_id, quality_logs)
    event_refs = [event["event_id"] for event in validated_events]
    card_refs = [envelope["card"]["card_id"] for envelope in validated_cards]
    quality_refs = [log["quality_log_id"] for log in validated_quality_logs]
    export_seed = "|".join((export_session_id, SCHEMA_VERSION, created_at, *event_refs, *card_refs, *quality_refs))
    return {
        "export_id": str(uuid5(NAMESPACE_URL, export_seed)),
        "schema_version": SCHEMA_VERSION,
        "session_id": export_session_id,
        "created_at": created_at,
        "event_refs": event_refs,
        "card_refs": card_refs,
        "quality_refs": quality_refs,
        "evidence_refs": _evidence_refs(validated_events, validated_cards, validated_quality_logs),
        "events": validated_events,
        "evidence_cards": validated_cards,
        "quality_logs": validated_quality_logs,
    }
