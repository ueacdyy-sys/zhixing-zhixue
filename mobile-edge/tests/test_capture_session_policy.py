from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from capture_session_policy import CaptureMode, CaptureSessionPolicy, CaptureOutputState  # noqa: E402


class CaptureSessionPolicyTests(unittest.TestCase):
    def test_full_continuous_mode_allows_every_foreground_application(self) -> None:
        policy = CaptureSessionPolicy.create(CaptureMode.FULL_CONTINUOUS, ())

        decision = policy.decide("tv.danmaku.bili")

        self.assertEqual(CaptureOutputState.STREAMING_ALLOWED, decision.output_state)
        self.assertEqual("FULL_CONTINUOUS", decision.reason)

    def test_selected_apps_mode_blocks_unselected_application_without_ending_session(self) -> None:
        policy = CaptureSessionPolicy.create(CaptureMode.SELECTED_APPS, ("tv.danmaku.bili", "com.ss.android.ugc.aweme"))

        blocked = policy.decide("com.android.settings")
        allowed = policy.decide("tv.danmaku.bili")

        self.assertEqual(CaptureOutputState.STREAMING_BLOCKED, blocked.output_state)
        self.assertEqual("FOREGROUND_APP_NOT_SELECTED", blocked.reason)
        self.assertEqual(CaptureOutputState.STREAMING_ALLOWED, allowed.output_state)

    def test_selected_apps_mode_rejects_empty_or_duplicate_package_allowlist(self) -> None:
        with self.assertRaisesRegex(ValueError, "selected_apps_requires_packages"):
            CaptureSessionPolicy.create(CaptureMode.SELECTED_APPS, ())
        with self.assertRaisesRegex(ValueError, "selected_app_packages_must_be_unique"):
            CaptureSessionPolicy.create(CaptureMode.SELECTED_APPS, ("tv.danmaku.bili", "tv.danmaku.bili"))

    def test_interruption_preserves_completed_evidence_and_marks_only_open_window_incomplete(self) -> None:
        policy = CaptureSessionPolicy.create(CaptureMode.FULL_CONTINUOUS, ())

        outcome = policy.interruption_outcome("PC_OBSERVED_SOURCE_DISCONNECT")

        self.assertTrue(outcome.preserve_completed_evidence)
        self.assertTrue(outcome.mark_open_window_incomplete)
        self.assertEqual("INTERRUPTED", outcome.session_state)
        self.assertEqual("PC_OBSERVED_SOURCE_DISCONNECT", outcome.reason)


if __name__ == "__main__":
    unittest.main()
