from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import realtime_queue_probe


BOUND_LIVE_REPORT = (
    ROOT
    / "captures"
    / "live_av_bound_session_20260711_160806"
    / "live_timeline_report.json"
)
REPLAY_WITHOUT_AUDIO_REPORT = (
    ROOT
    / "captures"
    / "rtsp_timeline_replay_no_prewarm_v4_20260709_153546"
    / "live_timeline_report.json"
)


class RealtimeQueueProbeGateTests(unittest.TestCase):
    def invoke_cli(
        self, timeline_report: Path, out_dir: Path, extra_args: list[str] | None = None
    ) -> subprocess.CompletedProcess:
        args = [
            sys.executable,
            str(SCRIPTS / "realtime_queue_probe.py"),
            "--timeline-report",
            str(timeline_report),
            "--out-dir",
            str(out_dir),
        ]
        args.extend(extra_args or [])
        return subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def run_cli_result(self, timeline_report: Path) -> tuple[subprocess.CompletedProcess, dict]:
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = self.invoke_cli(timeline_report, Path(temp_dir))
            report = json.loads(
                (Path(temp_dir) / "queue_probe_report.json").read_text(
                    encoding="utf-8"
                )
            )
            return completed, report

    def run_cli(self, timeline_report: Path) -> dict:
        completed, report = self.run_cli_result(timeline_report)
        self.assertEqual(0, completed.returncode, completed.stderr)
        return report

    def test_bound_capture_id_propagates_to_report_tasks_and_pending_gates(self):
        timeline = json.loads(BOUND_LIVE_REPORT.read_text(encoding="utf-8"))
        report = self.run_cli(BOUND_LIVE_REPORT)

        capture_id = timeline["capture_id"]
        self.assertEqual(capture_id, report["capture_id"])
        self.assertEqual(14, report["gate_summary"]["segments_total"])
        self.assertEqual(0, report["gate_summary"]["microtask_allowed_segments"])
        self.assertEqual(14, report["gate_summary"]["microtask_pending_segments"])
        self.assertTrue(report["tasks"])
        self.assertTrue(
            all(task["capture_id"] == capture_id for task in report["tasks"])
        )
        self.assertTrue(
            all(
                decision["capture_id"] == capture_id
                and decision["status"] == "pending_semantic_evidence"
                and not decision["allowed_to_generate_microtask"]
                for decision in report["gate_decisions"]
            )
        )

    def test_report_provenance_and_task_ids_bind_capture_and_probe_run(self):
        timeline_bytes = BOUND_LIVE_REPORT.read_bytes()
        timeline = json.loads(timeline_bytes)
        report = self.run_cli(BOUND_LIVE_REPORT)

        self.assertEqual("queue_probe_report.v2", report["schema_version"])
        self.assertEqual("realtime_queue_probe", report["tool"]["name"])
        self.assertTrue(report["tool"]["version"])
        self.assertTrue(report["rule_version"])
        self.assertRegex(report["generated_at"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertRegex(report["probe_run_id"], r"^qpr_[0-9a-f]{32}$")
        self.assertEqual(
            str(BOUND_LIVE_REPORT.resolve()), report["input_timeline"]["path"]
        )
        self.assertEqual(
            hashlib.sha256(timeline_bytes).hexdigest(),
            report["input_timeline"]["sha256"],
        )
        task_ids = [task["task_id"] for task in report["tasks"]]
        self.assertEqual(len(task_ids), len(set(task_ids)))
        self.assertTrue(report["task_summary"]["task_ids_unique"])
        for task in report["tasks"]:
            self.assertEqual(timeline["capture_id"], task["capture_id"])
            self.assertEqual(report["probe_run_id"], task["probe_run_id"])
            self.assertIn(task["capture_id"], task["task_id"])
            self.assertIn(task["probe_run_id"], task["task_id"])
            self.assertIn(task["stage"], task["task_id"])
        self.assertTrue(
            all(
                gate["capture_id"] == timeline["capture_id"]
                and gate["probe_run_id"] == report["probe_run_id"]
                for gate in report["gate_decisions"]
            )
        )

    def test_identity_samples_and_ffprobe_shape_errors_are_structured(self):
        valid = json.loads(BOUND_LIVE_REPORT.read_text(encoding="utf-8"))
        cases = {}

        invalid_capture = copy.deepcopy(valid)
        invalid_capture["capture_id"] = ""
        cases["capture_id"] = (invalid_capture, "capture_id_invalid")

        whitespace_capture = copy.deepcopy(valid)
        whitespace_capture["capture_id"] = f" {valid['capture_id']} "
        whitespace_capture["raw_recording"]["capture_id"] = whitespace_capture["capture_id"]
        cases["capture_id_whitespace"] = (
            whitespace_capture,
            "capture_id_invalid",
        )

        invalid_raw = copy.deepcopy(valid)
        invalid_raw["raw_recording"] = []
        cases["raw_recording"] = (invalid_raw, "raw_recording_object_required")

        raw_mismatch = copy.deepcopy(valid)
        raw_mismatch["raw_recording"]["capture_id"] = "cap_other"
        cases["raw_mismatch"] = (raw_mismatch, "raw_capture_id_mismatch")

        invalid_samples = copy.deepcopy(valid)
        invalid_samples["samples"] = {}
        cases["samples_type"] = (invalid_samples, "samples_list_required")

        invalid_sample_index = copy.deepcopy(valid)
        invalid_sample_index["samples"][0]["sample_index"] = 0
        cases["sample_index"] = (invalid_sample_index, "sample_index_invalid")

        duplicate_sample = copy.deepcopy(valid)
        duplicate_sample["samples"][1]["sample_index"] = duplicate_sample["samples"][0]["sample_index"]
        cases["sample_duplicate"] = (duplicate_sample, "sample_indices_not_unique")

        invalid_ffprobe = copy.deepcopy(valid)
        invalid_ffprobe["raw_recording"]["ffprobe"] = []
        cases["ffprobe_type"] = (invalid_ffprobe, "ffprobe_object_required")

        invalid_streams = copy.deepcopy(valid)
        invalid_streams["raw_recording"]["ffprobe"]["streams"] = {}
        cases["streams_type"] = (invalid_streams, "ffprobe_streams_list_required")

        invalid_stream_item = copy.deepcopy(valid)
        invalid_stream_item["raw_recording"]["ffprobe"]["streams"] = ["audio"]
        cases["stream_item"] = (invalid_stream_item, "ffprobe_stream_object_required")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for name, (timeline, expected_code) in cases.items():
                with self.subTest(name=name):
                    timeline_path = temp / f"{name}.json"
                    out_dir = temp / f"{name}-out"
                    timeline_path.write_text(json.dumps(timeline), encoding="utf-8")
                    completed = self.invoke_cli(timeline_path, out_dir)

                    self.assertEqual(2, completed.returncode, completed.stderr)
                    self.assertNotIn("Traceback", completed.stderr)
                    report = json.loads(
                        (out_dir / "queue_probe_report.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual("input_error", report["execution_status"])
                    self.assertIn(
                        expected_code, [error["code"] for error in report["errors"]]
                    )
                    self.assertEqual([], report["tasks"])

    def test_bad_json_missing_file_and_non_object_top_level_are_atomic_input_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            corrupt = temp / "corrupt.json"
            corrupt.write_text("{bad-json", encoding="utf-8")
            non_object = temp / "array.json"
            non_object.write_text("[]", encoding="utf-8")
            missing = temp / "missing.json"
            cases = {
                "corrupt": (corrupt, "timeline_json_invalid"),
                "missing": (missing, "timeline_file_unreadable"),
                "non_object": (non_object, "timeline_top_level_object_required"),
            }
            for name, (timeline_path, expected_code) in cases.items():
                with self.subTest(name=name):
                    out_dir = temp / f"{name}-out"
                    out_dir.mkdir()
                    (out_dir / "queue_probe_report.json").write_text(
                        "stale", encoding="utf-8"
                    )
                    (out_dir / "queue_probe_report.md").write_text(
                        "stale", encoding="utf-8"
                    )
                    completed = self.invoke_cli(timeline_path, out_dir)

                    self.assertEqual(2, completed.returncode, completed.stderr)
                    self.assertNotIn("Traceback", completed.stderr)
                    report = json.loads(
                        (out_dir / "queue_probe_report.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual("input_error", report["execution_status"])
                    self.assertEqual(expected_code, report["errors"][0]["code"])
                    self.assertFalse((out_dir / "queue_probe_report.md").exists())
                    self.assertEqual("", (out_dir / "queue_tasks.jsonl").read_text())
                    self.assertEqual([], list(out_dir.glob("*.tmp")))

    def test_numeric_parameters_must_be_positive_and_finite(self):
        flags = [
            "--visual-fast-path-budget-ms",
            "--segment-decision-budget-ms",
            "--microtask-deadline-s",
            "--ocr-ms-per-frame",
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for flag in flags:
                for value in ["0", "-1", "nan", "inf"]:
                    with self.subTest(flag=flag, value=value):
                        out_dir = temp / f"{flag[2:]}-{value}"
                        completed = self.invoke_cli(
                            BOUND_LIVE_REPORT, out_dir, [flag, value]
                        )
                        self.assertEqual(2, completed.returncode, completed.stderr)
                        report = json.loads(
                            (out_dir / "queue_probe_report.json").read_text(
                                encoding="utf-8"
                            )
                        )
                        self.assertEqual("input_error", report["execution_status"])
                        self.assertEqual(
                            "numeric_parameter_invalid", report["errors"][0]["code"]
                        )

    def test_atomic_replace_is_used_for_each_success_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "out"
            original_replace = Path.replace
            replacements = []

            def recording_replace(path, target):
                replacements.append((Path(path), Path(target)))
                return original_replace(path, target)

            with mock.patch.object(Path, "replace", recording_replace):
                exit_code = realtime_queue_probe.main(
                    [
                        "--timeline-report",
                        str(BOUND_LIVE_REPORT),
                        "--out-dir",
                        str(out_dir),
                    ]
                )

            self.assertEqual(0, exit_code)
            targets = {target.name for _, target in replacements}
            self.assertEqual(
                {"queue_probe_report.json", "queue_tasks.jsonl", "queue_probe_report.md"},
                targets,
            )
            self.assertTrue(all(source.parent == target.parent for source, target in replacements))
            self.assertEqual([], list(out_dir.glob("*.tmp")))

    def test_quality_budget_failure_is_recorded_but_probe_exit_stays_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            completed = self.invoke_cli(
                BOUND_LIVE_REPORT,
                out_dir,
                ["--visual-fast-path-budget-ms", "0.0001"],
            )
            report = json.loads(
                (out_dir / "queue_probe_report.json").read_text(encoding="utf-8")
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("quality_gate_failed", report["execution_status"])
        self.assertEqual(14, report["gate_summary"]["microtask_pending_segments"])
        self.assertEqual(0, report["gate_summary"]["microtask_allowed_segments"])

    def test_invalid_segments_fail_structurally_before_any_task_is_queued(self):
        valid = json.loads(BOUND_LIVE_REPORT.read_text(encoding="utf-8"))
        valid["samples"] = []
        first = copy.deepcopy(valid["segments"][0])
        second = copy.deepcopy(valid["segments"][1])
        duration = valid["timeline_duration_s"]
        cases = {
            "duplicate_index": (
                [{**first, "segment_index": 1}, {**second, "segment_index": 1}],
                "segment_indices_not_unique",
            ),
            "non_contiguous_index": (
                [{**first, "segment_index": 1}, {**second, "segment_index": 3}],
                "segment_indices_not_contiguous_1_based",
            ),
            "invalid_range": (
                [{**first, "start_s": 2.0, "end_s": 1.0}],
                "segment_time_range_invalid",
            ),
            "overlap": (
                [
                    {**first, "segment_index": 1, "start_s": 0.0, "end_s": 2.0},
                    {**second, "segment_index": 2, "start_s": 1.5, "end_s": 3.0},
                ],
                "segments_overlap_or_out_of_order",
            ),
            "past_timeline": (
                [{**first, "start_s": 0.0, "end_s": duration + 0.1}],
                "segment_end_exceeds_timeline_duration",
            ),
            "missing_evidence": (
                [{**first, "evidence_files": []}],
                "segment_evidence_files_required",
            ),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for name, (segments, expected_code) in cases.items():
                with self.subTest(name=name):
                    timeline = copy.deepcopy(valid)
                    timeline["segments"] = segments
                    timeline_path = temp / f"{name}.json"
                    timeline_path.write_text(json.dumps(timeline), encoding="utf-8")

                    completed, report = self.run_cli_result(timeline_path)

                    self.assertEqual(2, completed.returncode, completed.stderr)
                    self.assertEqual("input_error", report["status"])
                    self.assertEqual([], report["tasks"])
                    self.assertEqual([], report["gate_decisions"])
                    self.assertIn(
                        expected_code,
                        [error["code"] for error in report["errors"]],
                    )

    def test_audio_track_only_queues_asr_and_keeps_all_live_segments_pending(self):
        report = self.run_cli(BOUND_LIVE_REPORT)

        self.assertTrue(report["source_audio_present"])
        self.assertEqual(14, report["gate_summary"]["segments_total"])
        self.assertEqual(0, report["gate_summary"]["microtask_allowed_segments"])
        self.assertEqual(14, report["gate_summary"]["microtask_pending_segments"])
        self.assertEqual(0, report["gate_summary"]["microtask_blocked_segments"])
        self.assertEqual(
            {"awaiting_async_result": 14},
            report["gate_summary"]["pending_reason_counts"],
        )
        self.assertTrue(
            all(
                decision["status"] == "pending_semantic_evidence"
                and not decision["allowed_to_generate_microtask"]
                and "awaiting_async_result" in decision["reasons"]
                for decision in report["gate_decisions"]
            )
        )
        asr_tasks = [task for task in report["tasks"] if task["stage"] == "asr_async"]
        self.assertEqual(14, len(asr_tasks))
        self.assertTrue(all(task["status"] == "queued" for task in asr_tasks))

    def test_no_audio_or_vlm_stays_blocked_and_ocr_never_opens_gate(self):
        timeline = json.loads(
            REPLAY_WITHOUT_AUDIO_REPORT.read_text(encoding="utf-8")
        )
        timeline["capture_id"] = "cap_test_no_audio_replay"
        timeline["raw_recording"]["capture_id"] = timeline["capture_id"]
        timeline["segments"][-1]["end_s"] = timeline["timeline_duration_s"]
        with tempfile.TemporaryDirectory() as temp_dir:
            timeline_path = Path(temp_dir) / "valid_no_audio_replay.json"
            timeline_path.write_text(json.dumps(timeline), encoding="utf-8")
            report = self.run_cli(timeline_path)

        segment_count = report["gate_summary"]["segments_total"]
        self.assertFalse(report["source_audio_present"])
        self.assertEqual(0, report["gate_summary"]["microtask_allowed_segments"])
        self.assertEqual(0, report["gate_summary"]["microtask_pending_segments"])
        self.assertEqual(
            segment_count, report["gate_summary"]["microtask_blocked_segments"]
        )
        self.assertTrue(
            all(
                decision["status"] == "blocked_insufficient_semantic_evidence"
                and not decision["allowed_to_generate_microtask"]
                for decision in report["gate_decisions"]
            )
        )
        self.assertTrue(
            any(task["stage"] == "ocr_auxiliary" for task in report["tasks"])
        )


if __name__ == "__main__":
    unittest.main()
