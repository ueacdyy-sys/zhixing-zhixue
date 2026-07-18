"""手机日常入口的保守学习建议门控。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


VOLUNTARY_RECEIPT_ACTIONS = ("save", "watch_later", "dismiss")
LEARNING_WORK_ACTIONS = {"practice", "quiz", "forced_task", "microtask"}


def gate_mobile_learning_offer(
    evidence: Mapping[str, Any], *, requested_action: str | None = None
) -> dict[str, Any]:
    """Return only voluntary receipt actions for phone public-media evidence.

    A candidate, a pending semantic-analysis job, or an unknown evidence state may
    never produce practice, quiz, microtask, or forced-task work.  The function is
    intentionally independent of Android UI and persistence adapters.
    """
    if requested_action in LEARNING_WORK_ACTIONS:
        raise ValueError("learning_work_not_allowed_for_candidate")
    if requested_action is not None and requested_action not in VOLUNTARY_RECEIPT_ACTIONS:
        raise ValueError("unsupported_mobile_receipt_action")

    status = evidence.get("status") or evidence.get("analysis_status")
    if status not in {"CANDIDATE_ONLY", "SEMANTIC_ANALYSIS_PENDING"}:
        return {
            "decision": "NO_PRACTICE",
            "practice": None,
            "quiz": None,
            "forced_task": None,
            "allowed_actions": list(VOLUNTARY_RECEIPT_ACTIONS),
            "reason": "evidence_state_not_eligible_for_learning_work",
        }

    return {
        "decision": "NO_PRACTICE",
        "practice": None,
        "quiz": None,
        "forced_task": None,
        "allowed_actions": list(VOLUNTARY_RECEIPT_ACTIONS),
        "reason": "candidate_or_pending_evidence_requires_user_volition",
    }
