"""手机端低干扰用户回执的领域记录。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any


SUPPORTED_RECEIPT_ACTIONS = {"save", "watch_later", "dismiss"}


def _reference_id(receipt: Mapping[str, Any], field: str) -> str | None:
    value = receipt.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _timezone_timestamp(receipt: Mapping[str, Any]) -> str:
    value = receipt.get("recorded_at")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("recorded_at_required")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("recorded_at_must_be_iso8601") from error
    if timestamp.tzinfo is None:
        raise ValueError("recorded_at_must_include_timezone")
    return value


def write_phone_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one explicit student action without deriving a learner conclusion."""
    capture_id = _reference_id(receipt, "capture_id")
    evidence_card_id = _reference_id(receipt, "evidence_card_id")
    if capture_id is None and evidence_card_id is None:
        raise ValueError("capture_id_or_evidence_card_id_required")
    if capture_id is not None and evidence_card_id is not None:
        raise ValueError("exactly_one_evidence_reference_required")

    action = receipt.get("action")
    if not isinstance(action, str) or action not in SUPPORTED_RECEIPT_ACTIONS:
        raise ValueError("supported_action_required")

    return {
        "status": "RECORDED",
        "capture_id": capture_id,
        "evidence_card_id": evidence_card_id,
        "action": action,
        "recorded_at": _timezone_timestamp(receipt),
    }
