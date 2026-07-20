"""Framework-independent online projection of immutable fused visit evidence.

This module deliberately materialises only candidate evidence.  It does not
classify a learner, infer an interest, or decide L2–L4.  A user action is
required for every learning-stage transition; L1 is merely eligible when the
currently viewed visit has complete, aligned trimodal evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import FusedCandidate, FusionMode, SourceContext


class SemanticStateError(ValueError):
    """Raised when an event would rewrite or cross-contaminate a visit state."""


@dataclass(frozen=True)
class SemanticWindowFact:
    """One immutable, evidence-backed semantic unit in media-time order."""

    window_id: str
    start_pts_ns: int
    end_pts_ns: int
    evidence_uris: tuple[str, ...]
    fused_at_ns: int
    fusion_mode: FusionMode
    classification: str = "CANDIDATE_ONLY"

    @classmethod
    def from_candidate(cls, candidate: FusedCandidate) -> "SemanticWindowFact":
        if candidate.classification != "CANDIDATE_ONLY":
            raise SemanticStateError("non_candidate_classification")
        if not candidate.evidence_uris or any(not item.startswith("local://") for item in candidate.evidence_uris):
            raise SemanticStateError("candidate_evidence_invalid")
        return cls(
            window_id=candidate.window_id,
            start_pts_ns=candidate.start_pts_ns,
            end_pts_ns=candidate.end_pts_ns,
            evidence_uris=candidate.evidence_uris,
            fused_at_ns=candidate.fused_at_ns,
            fusion_mode=candidate.fusion_mode,
        )


@dataclass(frozen=True)
class VisitSemanticSnapshot:
    """Read model for one visit; history remains after the visit is closed."""

    visit_id: str
    source_context: SourceContext
    windows: tuple[SemanticWindowFact, ...]
    is_open: bool
    closed_at_pts_ns: int | None = None
    classification: str = "CANDIDATE_ONLY"

    @property
    def can_offer_l1(self) -> bool:
        return self.is_open and any(item.fusion_mode is FusionMode.TRIMODAL for item in self.windows)

    @property
    def l1_ineligibility_reason(self) -> str | None:
        if self.can_offer_l1:
            return None
        if not self.is_open:
            return "VISIT_CLOSED"
        return "NO_COMPLETE_TRIMODAL_EVIDENCE"


class VisitSemanticProjector:
    """Projects fused evidence without changing the immutable source ledger.

    Only the outer interaction-state adapter may choose when to close a visit.
    Starting another visit while one is open is rejected rather than silently
    merging unrelated content or discarding the old visit's pending evidence.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, VisitSemanticSnapshot] = {}
        self._current_visit_id: str | None = None

    @property
    def current_visit_id(self) -> str | None:
        return self._current_visit_id

    def snapshot(self, visit_id: str) -> VisitSemanticSnapshot | None:
        return self._snapshots.get(visit_id)

    def apply(self, candidate: FusedCandidate) -> VisitSemanticSnapshot:
        existing = self._snapshots.get(candidate.visit_id)
        if existing is None:
            if self._current_visit_id is not None:
                raise SemanticStateError("active_visit_conflict")
            existing = VisitSemanticSnapshot(
                visit_id=candidate.visit_id,
                source_context=candidate.source_context,
                windows=(),
                is_open=True,
            )
            self._current_visit_id = candidate.visit_id
        if existing.source_context is not candidate.source_context:
            raise SemanticStateError("visit_source_context_mismatch")
        if not existing.is_open:
            raise SemanticStateError("visit_closed")
        if any(item.window_id == candidate.window_id for item in existing.windows):
            raise SemanticStateError("duplicate_window")

        fact = SemanticWindowFact.from_candidate(candidate)
        windows = tuple(sorted((*existing.windows, fact), key=lambda item: (item.start_pts_ns, item.end_pts_ns, item.window_id)))
        projected = VisitSemanticSnapshot(
            visit_id=existing.visit_id,
            source_context=existing.source_context,
            windows=windows,
            is_open=True,
        )
        self._snapshots[candidate.visit_id] = projected
        return projected

    def close(self, visit_id: str, *, closed_at_pts_ns: int) -> VisitSemanticSnapshot:
        existing = self._snapshots.get(visit_id)
        if existing is None:
            raise SemanticStateError("unknown_visit")
        if not existing.is_open:
            raise SemanticStateError("visit_closed")
        if closed_at_pts_ns < 0 or (
            existing.windows and closed_at_pts_ns < existing.windows[-1].end_pts_ns
        ):
            raise SemanticStateError("invalid_visit_close_pts")
        closed = VisitSemanticSnapshot(
            visit_id=existing.visit_id,
            source_context=existing.source_context,
            windows=existing.windows,
            is_open=False,
            closed_at_pts_ns=closed_at_pts_ns,
        )
        self._snapshots[visit_id] = closed
        if self._current_visit_id == visit_id:
            self._current_visit_id = None
        return closed
