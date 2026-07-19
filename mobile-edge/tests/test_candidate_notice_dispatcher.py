from __future__ import annotations

import unittest

from candidate_notice_dispatcher import _interest_level


class CandidateNoticeLevelTests(unittest.TestCase):
    def test_l0_to_l3_dwell_boundaries(self) -> None:
        self.assertEqual("L0", _interest_level(2.99))
        self.assertEqual("L1", _interest_level(3.0))
        self.assertEqual("L1", _interest_level(7.99))
        self.assertEqual("L2", _interest_level(8.0))
        self.assertEqual("L2", _interest_level(20.0))
        self.assertEqual("L3", _interest_level(20.01))

