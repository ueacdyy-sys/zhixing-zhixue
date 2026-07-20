from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.contracts import FusedCandidate, FusionMode, SourceContext  # noqa: E402
from realtime_runtime.semantic_state import (  # noqa: E402
    SemanticStateError,
    VisitSemanticProjector,
)


def candidate(
    window_id: str,
    visit_id: str,
    *,
    start: int,
    end: int,
    fusion_mode: FusionMode = FusionMode.TRIMODAL,
) -> FusedCandidate:
    return FusedCandidate(
        window_id=window_id,
        visit_id=visit_id,
        source_context=SourceContext.PHONE_DAILY,
        start_pts_ns=start,
        end_pts_ns=end,
        evidence_uris=("local://ocr.json", "local://asr.json", "local://vlm.json"),
        fused_at_ns=end + 100,
        fusion_mode=fusion_mode,
    )


class VisitSemanticProjectorTests(unittest.TestCase):
    def test_appends_immutable_windows_in_media_pts_order_not_model_completion_order(self) -> None:
        projector = VisitSemanticProjector()

        projector.apply(candidate("win-later", "visit-a", start=20, end=30))
        snapshot = projector.apply(candidate("win-earlier", "visit-a", start=10, end=20))

        self.assertEqual(["win-earlier", "win-later"], [entry.window_id for entry in snapshot.windows])
        self.assertTrue(snapshot.can_offer_l1)
        self.assertEqual("CANDIDATE_ONLY", snapshot.classification)

    def test_incomplete_or_no_audio_window_cannot_offer_l1(self) -> None:
        projector = VisitSemanticProjector()

        snapshot = projector.apply(
            candidate(
                "win-no-audio",
                "visit-a",
                start=10,
                end=20,
                fusion_mode=FusionMode.VISUAL_TEXT_NO_AUDIO,
            )
        )

        self.assertFalse(snapshot.can_offer_l1)
        self.assertEqual("NO_COMPLETE_TRIMODAL_EVIDENCE", snapshot.l1_ineligibility_reason)

    def test_visit_isolation_and_close_preserve_history_but_remove_current_prompt_eligibility(self) -> None:
        projector = VisitSemanticProjector()
        projector.apply(candidate("win-a", "visit-a", start=10, end=20))
        closed = projector.close("visit-a", closed_at_pts_ns=20)
        next_visit = projector.apply(candidate("win-b", "visit-b", start=30, end=40))

        self.assertEqual(["win-a"], [entry.window_id for entry in closed.windows])
        self.assertFalse(closed.can_offer_l1)
        self.assertEqual(["win-b"], [entry.window_id for entry in next_visit.windows])
        self.assertEqual("visit-b", projector.current_visit_id)

    def test_rejects_cross_context_duplicate_and_post_close_mutation(self) -> None:
        projector = VisitSemanticProjector()
        projector.apply(candidate("win-a", "visit-a", start=10, end=20))
        with self.assertRaisesRegex(SemanticStateError, "duplicate_window"):
            projector.apply(candidate("win-a", "visit-a", start=10, end=20))
        projector.close("visit-a", closed_at_pts_ns=20)
        with self.assertRaisesRegex(SemanticStateError, "visit_closed"):
            projector.apply(candidate("win-b", "visit-a", start=20, end=30))


if __name__ == "__main__":
    unittest.main()
