from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_realtime_e2e import _acquire_capture_owner_lock, _child_visible_path, _counts, _ingress_terminal_error, _release_capture_owner_lock, _settlement_outcome, _stop_when_supervisor_is_gone, _write_realtime_slo_report, main  # noqa: E402


class RealtimeE2ESettlementTests(unittest.TestCase):
    def test_incomplete_evidence_is_reported_but_does_not_be_counted_as_fusion_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger_path = Path(temp_dir) / "ledger.sqlite3"
            with closing(sqlite3.connect(ledger_path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE semantic_windows (fusion_mode TEXT NOT NULL, fused_at_ns INTEGER);
                    CREATE TABLE jobs (state TEXT NOT NULL);
                    """
                )
                connection.executemany(
                    "INSERT INTO semantic_windows VALUES (?, ?)",
                    (("TRIMODAL", 10), ("EVIDENCE_INCOMPLETE", None)),
                )
                connection.commit()

            counts = _counts(ledger_path)

        self.assertEqual(2, counts["windows"])
        self.assertEqual(1, counts["fusion_eligible_windows"])
        self.assertEqual(1, counts["evidence_incomplete_windows"])
        self.assertEqual(1, counts["fused"])
        self.assertEqual(0, counts["unresolved_jobs"])

    def test_clock_sampling_cannot_be_accidentally_enabled_for_unbounded_product_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                sys,
                "argv",
                [
                    "run_realtime_e2e.py",
                    "--source", "rtsp://10.0.0.2:8554/screen",
                    "--session-id", "capture-1",
                    "--capture-generation", "1",
                    "--output-dir", str(Path(temp_dir) / "capture"),
                    "--enable-clock-sampling",
                ],
            ):
                with self.assertRaisesRegex(SystemExit, "clock_sampling_requires_finite_duration"):
                    main()

    def test_missing_gateway_owner_writes_the_existing_stop_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            signal = Path(temp_dir) / "runner.stop-requested"

            with patch("run_realtime_e2e._process_is_alive", return_value=False):
                stopped = _stop_when_supervisor_is_gone(12345, signal)

            self.assertTrue(stopped)
            self.assertTrue(signal.is_file())

    def test_live_gateway_owner_does_not_stop_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            signal = Path(temp_dir) / "runner.stop-requested"

            with patch("run_realtime_e2e._process_is_alive", return_value=True):
                stopped = _stop_when_supervisor_is_gone(12345, signal)

            self.assertFalse(stopped)
            self.assertFalse(signal.exists())

    def test_supervisor_owner_requires_a_stop_signal_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                sys,
                "argv",
                [
                    "run_realtime_e2e.py",
                    "--source", "rtsp://10.0.0.2:8554/screen",
                    "--session-id", "capture-1",
                    "--capture-generation", "1",
                    "--output-dir", str(Path(temp_dir) / "capture"),
                    "--supervisor-pid", "12345",
                ],
            ):
                with self.assertRaisesRegex(SystemExit, "supervisor_pid_requires_stop_signal_file"):
                    main()

    def test_capture_owner_lock_prevents_second_live_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock = Path(temp_dir) / "owner.json"
            first = _acquire_capture_owner_lock(lock)
            self.assertIsNotNone(first)
            with self.assertRaisesRegex(RuntimeError, "capture_owner_conflict"):
                _acquire_capture_owner_lock(lock)
            _release_capture_owner_lock(lock, first)
            self.assertFalse(lock.exists())

    def test_stop_contract_path_is_absolute_for_ingress_with_a_different_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            relative_signal = root / "artifacts" / ".stop-requested"
            self.assertEqual(str(relative_signal.resolve()), _child_visible_path(relative_signal))
            self.assertTrue(Path(_child_visible_path(relative_signal)).is_absolute())

    def test_terminal_unfused_windows_are_reported_as_failure_not_waited_forever(self) -> None:
        state = {
            "windows": 36,
            "fusion_eligible_windows": 22,
            "evidence_incomplete_windows": 14,
            "fused": 13,
            "unresolved_jobs": 0,
        }
        self.assertEqual("FAILED_UNFUSED_WINDOWS", _settlement_outcome(state))

    def test_ingress_receipt_preserves_transport_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            (output / "ingress_report.json").write_text('{"terminal_error":"unexpected_transport_loss"}', encoding="utf-8")
            self.assertEqual("unexpected_transport_loss", _ingress_terminal_error(output))

    def test_missing_slo_policy_or_phone_attestation_is_written_as_not_realtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            report = _write_realtime_slo_report(
                output=output,
                policy_path=None,
                device_stream_attestation_path=None,
                capture_session_id="capture-1",
            )

            persisted = __import__("json").loads((output / "realtime_slo_report.json").read_text(encoding="utf-8"))

        self.assertEqual("NOT_REALTIME", report["status"])
        self.assertIn("policy_missing", report["reasons"])
        self.assertIn("device_stream_attestation_missing", report["reasons"])
        self.assertEqual(report, persisted)


if __name__ == "__main__":
    unittest.main()
