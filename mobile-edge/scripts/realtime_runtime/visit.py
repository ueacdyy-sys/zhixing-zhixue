"""Pure visit and semantic-window planning over immutable sealed fragments."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .contracts import AudioStatus, FusionMode, Lane, SealedFragment, SemanticWindow, SourceContext


@dataclass(frozen=True)
class PlannedWindow:
    window: SemanticWindow
    fusion_mode: FusionMode


class VisitWindowPlanner:
    """Plans one bounded semantic window per sealed fragment without dropping history.

    A caller supplies an externally observed content transition before the first
    fragment of the new visit.  The planner never infers a platform, a topic,
    or a user preference from that boundary.
    """

    def __init__(
        self,
        *,
        session_id: str,
        source_context: SourceContext,
        fragments_per_window: int = 3,
        window_hop_fragments: int = 1,
        require_full_window: bool = False,
    ) -> None:
        if not session_id or fragments_per_window < 1 or window_hop_fragments < 1:
            raise ValueError("planner_configuration_invalid")
        self._session_id = session_id
        self._source_context = source_context
        self._fragments_per_window = fragments_per_window
        self._window_hop_fragments = window_hop_fragments
        self._require_full_window = require_full_window
        self._visit_number = 0
        self._window_number = 0
        self._visit_id: str | None = None
        self._fragments: deque[SealedFragment] = deque(maxlen=fragments_per_window)
        self._fragments_since_visit_start = 0
        self._last_emission_end_pts_ns: int | None = None

    @property
    def active_visit_id(self) -> str | None:
        return self._visit_id

    def begin_visit(self) -> str:
        self._visit_number += 1
        self._visit_id = f"{self._session_id}:visit:{self._visit_number:04d}"
        self._fragments.clear()
        self._fragments_since_visit_start = 0
        self._last_emission_end_pts_ns = None
        return self._visit_id

    def ingest(self, fragment: SealedFragment, *, content_transition: bool = False) -> PlannedWindow | None:
        if fragment.session_id != self._session_id or fragment.source_context != self._source_context:
            raise ValueError("fragment_scope_mismatch")
        if self._visit_id is None or content_transition:
            self.begin_visit()
        if self._fragments and fragment.start_pts_ns < self._fragments[-1].end_pts_ns:
            raise ValueError("fragment_pts_regression")
        self._fragments.append(fragment)
        self._fragments_since_visit_start += 1
        if self._require_full_window:
            if len(self._fragments) < self._fragments_per_window:
                return None
            emission_offset = self._fragments_since_visit_start - self._fragments_per_window
        else:
            emission_offset = self._fragments_since_visit_start - 1
        if emission_offset % self._window_hop_fragments:
            return None
        selected = tuple(self._fragments)
        return self._plan(selected)

    def flush_tail(self) -> PlannedWindow | None:
        """Schedule the final short sealed tail; never silently discard it."""

        if not self._fragments:
            return None
        selected = tuple(
            item
            for item in self._fragments
            if self._last_emission_end_pts_ns is None or item.start_pts_ns >= self._last_emission_end_pts_ns
        )
        if not selected:
            return None
        return self._plan(selected)

    def _plan(self, selected: tuple[SealedFragment, ...]) -> PlannedWindow:
        self._window_number += 1
        statuses = {item.audio_status for item in selected}
        if AudioStatus.AUDIO_INTEGRITY_UNRESOLVED in statuses:
            fusion_mode = FusionMode.EVIDENCE_INCOMPLETE
            lanes = (Lane.ASR, Lane.OCR, Lane.VLM)
        elif AudioStatus.NO_AUDIO_TRACK_VERIFIED in statuses or any(not item.has_same_source_audio for item in selected):
            fusion_mode = FusionMode.VISUAL_TEXT_NO_AUDIO
            lanes = (Lane.OCR, Lane.VLM)
        else:
            fusion_mode = FusionMode.TRIMODAL
            lanes = (Lane.ASR, Lane.OCR, Lane.VLM)
        self._last_emission_end_pts_ns = selected[-1].end_pts_ns
        return PlannedWindow(
            window=SemanticWindow(
                window_id=f"{self._session_id}:window:{self._window_number:06d}",
                session_id=self._session_id,
                visit_id=self._visit_id,
                source_context=self._source_context,
                start_pts_ns=selected[0].start_pts_ns,
                end_pts_ns=selected[-1].end_pts_ns,
                fragment_hashes=tuple(item.media_sha256 for item in selected),
                required_lanes=lanes,
            ),
            fusion_mode=fusion_mode,
        )
