from __future__ import annotations

import unittest

from touch_transition_monitor import VerticalSwipeDetector


class VerticalSwipeDetectorTests(unittest.TestCase):
    def test_only_completed_large_vertical_swipe_emits_transition(self) -> None:
        detector = VerticalSwipeDetector(240)
        self.assertIsNone(detector.consume("EV_ABS ABS_MT_POSITION_Y 00000800", pc_monotonic_ns=1))
        self.assertIsNone(detector.consume("EV_ABS ABS_MT_POSITION_Y 00000200", pc_monotonic_ns=2))
        event = detector.consume("EV_ABS ABS_MT_TRACKING_ID ffffffff", pc_monotonic_ns=3)
        self.assertEqual(event["event_type"], "ContentTransitionCandidate")
        self.assertEqual(event["delta_y_px"], -1536)

    def test_tap_like_motion_does_not_emit_transition(self) -> None:
        detector = VerticalSwipeDetector(240)
        detector.consume("EV_ABS ABS_MT_POSITION_Y 00000200", pc_monotonic_ns=1)
        detector.consume("EV_ABS ABS_MT_POSITION_Y 00000280", pc_monotonic_ns=2)
        self.assertIsNone(detector.consume("EV_KEY BTN_TOUCH 00000000", pc_monotonic_ns=3))

