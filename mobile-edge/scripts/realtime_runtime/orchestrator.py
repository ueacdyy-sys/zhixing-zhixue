"""Application service that connects sealed-media adapters to the durable ledger."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import SealedFragment, SourceContext, Visit, VisitClosureReason
from .ledger import SealedWindowLedger
from .visit import PlannedWindow, VisitWindowPlanner


@dataclass(frozen=True)
class IngestResult:
    planned_window: PlannedWindow | None
    opened_visit_id: str | None
    closed_visit_id: str | None


class RealtimeIngestor:
    """Persists every sealed fragment before scheduling any semantic work.

    Content transitions are adapter facts (for example from a scene-change
    detector), never platform-specific rules.  Closing a visit only changes
    notification eligibility; all already sealed windows remain in the ledger.
    """

    def __init__(
        self,
        ledger: SealedWindowLedger,
        *,
        session_id: str,
        source_context: SourceContext,
        fragments_per_window: int = 3,
        window_hop_fragments: int = 1,
        require_full_window: bool = False,
    ) -> None:
        self._ledger = ledger
        self._planner = VisitWindowPlanner(
            session_id=session_id,
            source_context=source_context,
            fragments_per_window=fragments_per_window,
            window_hop_fragments=window_hop_fragments,
            require_full_window=require_full_window,
        )

    @property
    def active_visit_id(self) -> str | None:
        return self._planner.active_visit_id

    def ingest(
        self,
        fragment: SealedFragment,
        *,
        now_ns: int,
        content_transition: bool = False,
    ) -> IngestResult:
        if now_ns < 0:
            raise ValueError("ingest_now_ns_invalid")
        self._ledger.append_fragment(fragment)
        prior_visit = self._planner.active_visit_id
        opened_visit: str | None = None
        closed_visit: str | None = None
        if prior_visit is None or content_transition:
            if prior_visit is not None:
                self._ledger.close_visit(
                    prior_visit,
                    end_pts_ns=fragment.start_pts_ns,
                    reason=VisitClosureReason.CONTENT_SWITCH,
                )
                closed_visit = prior_visit
            opened_visit = self._planner.begin_visit()
            self._ledger.open_visit(
                Visit(
                    visit_id=opened_visit,
                    session_id=fragment.session_id,
                    source_context=fragment.source_context,
                    start_pts_ns=fragment.start_pts_ns,
                )
            )
        planned = self._planner.ingest(fragment)
        if planned is not None:
            self._ledger.create_window(planned.window, fusion_mode=planned.fusion_mode, created_ns=now_ns)
        return IngestResult(planned, opened_visit, closed_visit)

    def close_session(self, *, end_pts_ns: int) -> str | None:
        visit_id = self._planner.active_visit_id
        if visit_id is not None:
            self._ledger.close_visit(visit_id, end_pts_ns=end_pts_ns, reason=VisitClosureReason.SESSION_ENDED)
        return visit_id

    def flush_tail(self, *, now_ns: int) -> PlannedWindow | None:
        planned = self._planner.flush_tail()
        if planned is not None:
            self._ledger.create_window(planned.window, fusion_mode=planned.fusion_mode, created_ns=now_ns)
        return planned
