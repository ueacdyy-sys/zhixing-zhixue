"""Pure current-visit notification policy; platform delivery is an outer adapter."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import FusedCandidate, FusionMode


@dataclass(frozen=True)
class NotificationDecision:
    eligible: bool
    reason: str


def notification_eligibility(
    candidate: FusedCandidate,
    *,
    active_visit_id: str | None,
    live_edge_pts_ns: int,
    maximum_lag_ns: int,
) -> NotificationDecision:
    if maximum_lag_ns < 0 or live_edge_pts_ns < candidate.end_pts_ns:
        raise ValueError("notification_clock_invalid")
    if candidate.visit_id != active_visit_id:
        return NotificationDecision(False, "VISIT_NO_LONGER_ACTIVE")
    if candidate.fusion_mode is not FusionMode.TRIMODAL:
        return NotificationDecision(False, "TRIMODAL_EVIDENCE_REQUIRED")
    if live_edge_pts_ns - candidate.end_pts_ns > maximum_lag_ns:
        return NotificationDecision(False, "LIVE_EDGE_LAG_EXCEEDED")
    return NotificationDecision(True, "CURRENT_TRIMODAL_CANDIDATE")
