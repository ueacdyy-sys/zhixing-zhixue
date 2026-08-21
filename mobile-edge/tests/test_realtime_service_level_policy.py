from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.realtime_slo import (  # noqa: E402
    DeviceModelConfiguration,
    RealtimeInputSource,
    RealtimeMeasurement,
    RealtimeServiceLevelPolicy,
    RealtimeStatus,
    evaluate_realtime_service_level,
    measurement_from_e2e_artifacts,
)


HASH = hashlib.sha256(b"approved-benchmark").hexdigest()
RAW_LOG_HASH = hashlib.sha256(b"raw-device-log").hexdigest()


class RealtimeServiceLevelPolicyTests(unittest.TestCase):
    def configuration(self) -> DeviceModelConfiguration:
        return DeviceModelConfiguration(
            device_model="Pixel 8",
            android_api_level=35,
            capture_build_hash="a" * 64,
            pc_model="ThinkPad P1",
            model_id="smolvlm2-500m-video-instruct",
            model_artifact_hash="b" * 64,
            runtime_version="torch-2.6-cuda",
        )

    def policy(self, **overrides: object) -> RealtimeServiceLevelPolicy:
        values: dict[str, object] = {
            "policy_id": "slo-pixel8-smolvlm2-v1",
            "configuration": self.configuration(),
            "approved_benchmark_report_sha256": HASH,
            "minimum_continuous_input_ns": 60_000_000_000,
            "minimum_samples": 20,
            "maximum_p95_latency_ns": 4_000_000_000,
            "maximum_latency_ns": 6_000_000_000,
            "minimum_input_windows_per_second": 0.20,
            "minimum_processed_windows_per_second": 0.20,
            "maximum_queue_depth": 9,
            "measurement_window_ns": 60_000_000_000,
            "approved_overload_actions": ("BACKPRESSURE_PAUSED", "RECORD_ONLY"),
        }
        values.update(overrides)
        return RealtimeServiceLevelPolicy(**values)

    def measurement(self, **overrides: object) -> RealtimeMeasurement:
        values: dict[str, object] = {
            "input_source": RealtimeInputSource.REAL_DEVICE_CONTINUOUS_STREAM,
            "configuration": self.configuration(),
            "raw_observation_log_sha256": RAW_LOG_HASH,
            "device_stream_attestation_sha256": "c" * 64,
            "started_monotonic_ns": 100,
            "ended_monotonic_ns": 60_000_000_100,
            "input_window_count": 24,
            "processed_window_count": 22,
            "latency_samples_ns": tuple(2_000_000_000 for _ in range(22)),
            "maximum_queue_depth": 4,
            "overload_state": "NORMAL",
            "overload_action": "NONE_REQUIRED",
            "continuous_input_verified": True,
            "observed_continuous_input_ns": 60_000_000_000,
        }
        values.update(overrides)
        return RealtimeMeasurement(**values)

    def test_absent_policy_is_not_realtime_and_never_uses_product_defaults(self) -> None:
        decision = evaluate_realtime_service_level(None, self.measurement())

        self.assertEqual(RealtimeStatus.NOT_REALTIME, decision.status)
        self.assertEqual(("policy_missing",), decision.reasons)

    def test_replay_or_simulation_cannot_claim_realtime_even_with_good_metrics(self) -> None:
        decision = evaluate_realtime_service_level(
            self.policy(), self.measurement(input_source=RealtimeInputSource.REPLAY)
        )

        self.assertEqual(RealtimeStatus.NOT_REALTIME, decision.status)
        self.assertIn("input_source_not_real_device", decision.reasons)

    def test_same_configuration_real_continuous_stream_with_all_metrics_can_pass(self) -> None:
        decision = evaluate_realtime_service_level(self.policy(), self.measurement())

        self.assertEqual(RealtimeStatus.REALTIME, decision.status)
        self.assertEqual((), decision.reasons)
        self.assertEqual(2_000_000_000, decision.metrics.p95_latency_ns)
        self.assertEqual(4, decision.metrics.maximum_queue_depth)

    def test_required_metric_or_attestation_gaps_fail_closed(self) -> None:
        decision = evaluate_realtime_service_level(
            self.policy(),
            self.measurement(raw_observation_log_sha256=None, device_stream_attestation_sha256=None),
        )

        self.assertEqual(RealtimeStatus.NOT_REALTIME, decision.status)
        self.assertIn("raw_observation_log_missing", decision.reasons)
        self.assertIn("device_stream_attestation_missing", decision.reasons)

    def test_duration_sample_latency_throughput_queue_and_overload_are_independent_gates(self) -> None:
        decision = evaluate_realtime_service_level(
            self.policy(),
            self.measurement(
                ended_monotonic_ns=20_000_000_100,
                observed_continuous_input_ns=20_000_000_000,
                input_window_count=2,
                processed_window_count=1,
                latency_samples_ns=tuple(7_000_000_000 for _ in range(5)),
                maximum_queue_depth=10,
                overload_state="BACKPRESSURE",
                overload_action="UNDECLARED_ACTION",
            ),
        )

        self.assertEqual(RealtimeStatus.NOT_REALTIME, decision.status)
        self.assertTrue(
            {
                "continuous_input_duration_below_policy",
                "sample_count_below_policy",
                "p95_latency_exceeds_policy",
                "maximum_latency_exceeds_policy",
                "input_throughput_below_policy",
                "processed_throughput_below_policy",
                "queue_depth_exceeds_policy",
                "overload_action_unapproved",
            }.issubset(decision.reasons)
        )

    def test_configuration_mismatch_cannot_borrow_another_device_model_approval(self) -> None:
        other = DeviceModelConfiguration(
            **{**self.configuration().__dict__, "device_model": "Pixel 9"}
        )
        decision = evaluate_realtime_service_level(self.policy(), self.measurement(configuration=other))

        self.assertEqual(RealtimeStatus.NOT_REALTIME, decision.status)
        self.assertIn("device_model_configuration_mismatch", decision.reasons)

    def test_declared_phone_duration_cannot_replace_observed_continuous_input_proof(self) -> None:
        decision = evaluate_realtime_service_level(
            self.policy(), self.measurement(continuous_input_verified=False)
        )

        self.assertEqual(RealtimeStatus.NOT_REALTIME, decision.status)
        self.assertIn("continuous_input_not_proven", decision.reasons)

    def test_policy_requires_a_real_approval_reference_and_declared_overload_actions(self) -> None:
        with self.assertRaisesRegex(ValueError, "approved_benchmark_report_hash_invalid"):
            self.policy(approved_benchmark_report_sha256="")
        with self.assertRaisesRegex(ValueError, "approved_overload_actions_missing"):
            self.policy(approved_overload_actions=())

    def test_measurement_uses_raw_runtime_artifacts_and_device_attestation_not_a_cli_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ledger = root / "evidence_ledger.sqlite"
            progress = root / "online_progress.jsonl"
            attestation = root / "device-stream-attestation.json"
            with closing(sqlite3.connect(ledger)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE fragments (
                        pc_arrival_first_ns INTEGER NOT NULL,
                        pc_sealed_ns INTEGER NOT NULL,
                        start_pts_ns INTEGER NOT NULL,
                        end_pts_ns INTEGER NOT NULL,
                        gap_before INTEGER NOT NULL
                    );
                    CREATE TABLE semantic_windows (created_ns INTEGER NOT NULL, fused_at_ns INTEGER);
                    """
                )
                connection.executemany(
                    "INSERT INTO fragments VALUES (?, ?, ?, ?, ?)",
                    ((1_000_000_000, 2_000_000_000, 0, 2_000_000_000, 0), (3_000_000_000, 4_000_000_000, 2_000_000_000, 4_000_000_000, 0)),
                )
                connection.executemany(
                    "INSERT INTO semantic_windows VALUES (?, ?)",
                    ((2_000_000_000, 4_000_000_000), (3_000_000_000, 5_000_000_000)),
                )
                connection.commit()
            progress.write_text(
                '{"pc_monotonic_ns":1000000000,"queue_depth":2}\n'
                '{"pc_monotonic_ns":5000000000,"queue_depth":4}\n',
                encoding="utf-8",
            )
            attestation.write_text(
                json.dumps(
                    {
                        "input_source": "REAL_DEVICE_CONTINUOUS_STREAM",
                        "configuration": self.policy().to_dict()["configuration"],
                        "capture_session_id": "session-1",
                        "stream_started_monotonic_ns": 1_000_000_000,
                        "stream_ended_monotonic_ns": 5_000_000_000,
                        "raw_device_log_sha256": "d" * 64,
                    }
                ),
                encoding="utf-8",
            )

            measurement = measurement_from_e2e_artifacts(
                ledger_path=ledger,
                progress_path=progress,
                device_stream_attestation_path=attestation,
                expected_capture_session_id="session-1",
            )

        self.assertEqual(RealtimeInputSource.REAL_DEVICE_CONTINUOUS_STREAM, measurement.input_source)
        self.assertEqual(2, measurement.input_window_count)
        self.assertEqual(2, measurement.processed_window_count)
        self.assertEqual((2_000_000_000, 2_000_000_000), measurement.latency_samples_ns)
        self.assertEqual(4, measurement.maximum_queue_depth)
        self.assertEqual("NORMAL", measurement.overload_state)
        self.assertEqual("NONE_REQUIRED", measurement.overload_action)
        self.assertTrue(measurement.continuous_input_verified)
        self.assertEqual(64, len(measurement.raw_observation_log_sha256 or ""))

    def test_attestation_for_another_capture_session_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attestation = root / "device-stream-attestation.json"
            attestation.write_text(
                json.dumps(
                    {
                        "input_source": "REAL_DEVICE_CONTINUOUS_STREAM",
                        "configuration": self.policy().to_dict()["configuration"],
                        "capture_session_id": "other-session",
                        "stream_started_monotonic_ns": 1,
                        "stream_ended_monotonic_ns": 2,
                        "raw_device_log_sha256": "d" * 64,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "device_stream_attestation_session_mismatch"):
                measurement_from_e2e_artifacts(
                    ledger_path=root / "missing.sqlite",
                    progress_path=root / "missing.jsonl",
                    device_stream_attestation_path=attestation,
                    expected_capture_session_id="session-1",
                )


if __name__ == "__main__":
    unittest.main()
