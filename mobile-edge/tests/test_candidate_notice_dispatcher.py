from __future__ import annotations

import unittest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from candidate_notice_dispatcher import _l1_eligibility


class CandidateNoticeEligibilityTests(unittest.TestCase):
    def test_l1_requires_fresh_current_trimodal_candidate_not_dwell_time(self) -> None:
        self.assertEqual(
            (True, "CURRENT_TRIMODAL_CANDIDATE"),
            _l1_eligibility(fusion_mode="TRIMODAL", is_current_visit=True, is_fresh=True),
        )
        self.assertEqual(
            (False, "TRIMODAL_EVIDENCE_REQUIRED"),
            _l1_eligibility(fusion_mode="VISUAL_TEXT_NO_AUDIO", is_current_visit=True, is_fresh=True),
        )
        self.assertEqual(
            (False, "VISIT_NO_LONGER_ACTIVE"),
            _l1_eligibility(fusion_mode="TRIMODAL", is_current_visit=False, is_fresh=True),
        )
        self.assertEqual(
            (False, "LIVE_EDGE_LAG_EXCEEDED"),
            _l1_eligibility(fusion_mode="TRIMODAL", is_current_visit=True, is_fresh=False),
        )
