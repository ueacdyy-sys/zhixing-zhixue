import copy
import io
import hashlib
import inspect
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import semantic_evidence_gate
from semantic_evidence_gate import evaluate_evidence


RAW_FILE = "contract-test/capture.mkv"
CAPTURE_ID = "capture-contract-001"
FIXTURE_MEDIA_SHA256 = "f" * 64
QUALITY_THRESHOLDS = {
    "min_text_coverage_ratio": 0.5,
    "min_mean_avg_logprob": -0.6,
    "max_no_speech_prob": 0.6,
}


def passing_quality_summary(segment_count=1):
    return {
        "quality_status": "pass",
        "quality_reasons": [],
        "segment_count": segment_count,
        "valid_quality_segment_count": segment_count,
        "speech_segment_count": segment_count,
        "transcribed_segment_count": segment_count,
        "mean_avg_logprob": -0.2,
        "mean_no_speech_prob": 0.1,
        "max_no_speech_prob": 0.1,
        "text_coverage_ratio": 1.0,
        "invalid_quality_segment_ids": [],
        "quality_thresholds": dict(QUALITY_THRESHOLDS),
    }


def synthetic_timeline_report(
    *,
    error=None,
    segments=None,
    capture_id=CAPTURE_ID,
    timeline_duration_s=1.0,
    capture_wall_s=1.5,
):
    return {
        "source": "fixture://semantic-evidence-gate",
        "source_kind": "fixture",
        "fixture": True,
        "rtsp_url": None,
        "mode": "contract_test_fixture_timeline",
        "capture_id": capture_id,
        "timeline_duration_s": timeline_duration_s,
        "capture_wall_s": capture_wall_s,
        "sampled_frames": 8,
        "decoded_frames": 16,
        "segments": segments
        if segments is not None
        else [
            {
                "segment_index": 1,
                "start_s": 0.0,
                "end_s": 1.0,
                "evidence_files": ["frame-1.jpg"],
            }
        ],
        "raw_recording": {
            "file": RAW_FILE,
            "capture_id": capture_id,
            "sha256": FIXTURE_MEDIA_SHA256,
        },
        "error": error,
    }


def production_timeline_report(
    raw_file,
    *,
    source_kind="live_rtsp",
    error=None,
    segments=None,
    capture_id=CAPTURE_ID,
    timeline_duration_s=1.0,
    capture_wall_s=1.5,
    raw_overrides=None,
):
    raw_path = Path(raw_file)
    media_sha256 = (
        hashlib.sha256(raw_path.read_bytes()).hexdigest()
        if raw_path.is_file()
        else "0" * 64
    )
    raw_recording = {
        "file": str(raw_path),
        "capture_id": capture_id,
        "sha256": media_sha256,
    }
    raw_recording.update(raw_overrides or {})
    return {
        "source": "rtsp://127.0.0.1:8554/screen",
        "source_kind": source_kind,
        "rtsp_url": "rtsp://127.0.0.1:8554/screen",
        "mode": "passive_rtsp_live_visual_timeline",
        "capture_id": capture_id,
        "timeline_duration_s": timeline_duration_s,
        "capture_wall_s": capture_wall_s,
        "sampled_frames": 8,
        "decoded_frames": 16,
        "segments": segments
        if segments is not None
        else [
            {
                "segment_index": 1,
                "start_s": 0.0,
                "end_s": 1.0,
                "evidence_files": ["frame-1.jpg"],
            }
        ],
        "raw_recording": raw_recording,
        "error": error,
    }


def synthetic_audio_inventory(state="present", *, path=RAW_FILE, capture_id=CAPTURE_ID):
    if state == "present":
        item = {
            "path": path,
            "capture_id": capture_id,
            "audio_stream_count": 1,
            "error": None,
        }
        summary = {"files_with_audio": 1, "files_without_audio": 0, "probe_errors": 0}
    elif state == "absent":
        item = {
            "path": path,
            "capture_id": capture_id,
            "audio_stream_count": 0,
            "error": None,
        }
        summary = {"files_with_audio": 0, "files_without_audio": 1, "probe_errors": 0}
    elif state == "unknown":
        item = {
            "path": path,
            "capture_id": capture_id,
            "size_bytes": 100,
            "error": "ffprobe failed",
        }
        summary = {"files_with_audio": 0, "files_without_audio": 0, "probe_errors": 1}
    else:
        raise ValueError(state)
    return {"summary": {"scanned_files": 1, **summary}, "files": [item]}


def synthetic_semantic_result(
    kind="asr",
    *,
    report_capture_id=CAPTURE_ID,
    report_media_sha256=FIXTURE_MEDIA_SHA256,
    **overrides,
):
    result = {
        "capture_id": CAPTURE_ID,
        "source_media_sha256": report_media_sha256,
        "segment_index": 1,
        "status": "success",
        "start_s": 0.1,
        "end_s": 0.9,
        "model_id": f"{kind}-model-under-contract-test",
        "evidence_refs": [f"{kind}://segment-1/result-1"],
    }
    result["text" if kind == "asr" else "summary"] = "non-empty semantic evidence"
    result.update(overrides)
    report = {
        "capture_id": report_capture_id,
        "source_media_sha256": report_media_sha256,
        "results": [result],
    }
    if kind == "asr":
        result.update(
            {
                "quality_status": "pass",
                "quality_reasons": [],
                "quality_summary": passing_quality_summary(),
            }
        )
        report.update(
            {
                "quality_status": "pass",
                "quality_reasons": [],
                "quality_thresholds": dict(QUALITY_THRESHOLDS),
                "quality_summary": passing_quality_summary(),
                "alignment_summary": {
                    "raw_segment_count": 1,
                    "assigned_raw_segment_count": 1,
                    "unassigned_raw_segment_ids": [],
                },
            }
        )
    return report


def synthetic_ocr_report():
    return {
        "results": [
            {
                "segment_index": 1,
                "status": "success",
                "text": "visible words",
                "start_s": 0.1,
                "end_s": 0.9,
                "evidence_refs": ["ocr://segment-1/result-1"],
            }
        ]
    }


def evaluate_fixture(
    timeline_report=None,
    audio_inventory=None,
    **kwargs,
):
    kwargs.pop("expected_capture_id", None)
    return evaluate_evidence(
        timeline_report or synthetic_timeline_report(),
        audio_inventory or synthetic_audio_inventory("absent"),
        execution_scope="contract_test",
        contract_test=True,
        **kwargs,
    )


class SemanticEvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self._production_temp = tempfile.TemporaryDirectory()
        self.production_raw_file = (
            Path(self._production_temp.name) / "captured-live-media.mkv"
        )
        self.production_raw_file.write_bytes(b"bound live transport media\x00\x01")
        self.production_media_sha256 = hashlib.sha256(
            self.production_raw_file.read_bytes()
        ).hexdigest()

    def tearDown(self):
        self._production_temp.cleanup()

    def production_timeline(self, **kwargs):
        return production_timeline_report(self.production_raw_file, **kwargs)

    def production_semantic_result(self, kind="asr", **overrides):
        report_media_sha256 = overrides.pop(
            "report_media_sha256", self.production_media_sha256
        )
        return synthetic_semantic_result(
            kind,
            report_media_sha256=report_media_sha256,
            **overrides,
        )

    def canonical_live_timeline(self):
        timeline = self.production_timeline()
        manifest_id = "manifest_22222222-2222-4222-8222-222222222222"
        manifest_file = Path(self._production_temp.name) / "capture_manifest.json"
        timeline.update(
            {
                "mode": "deferred_canonical_raw_timeline",
                "acquisition_source_kind": "live_rtsp",
                "analysis_source_kind": "canonical_raw_replay",
                "analysis_wall_s": 0.25,
                "trust_level": "content_hash_bound",
                "production_usable": True,
                "manifest_id": manifest_id,
                "manifest_file": str(manifest_file),
            }
        )
        timeline["raw_recording"].update(
            {
                "canonical_file": str(self.production_raw_file.resolve()),
                "size_bytes": self.production_raw_file.stat().st_size,
            }
        )
        manifest = {
            "schema_version": "1.0",
            "manifest_id": manifest_id,
            "capture_id": CAPTURE_ID,
            "source_kind": "live_rtsp",
            "source": timeline["source"],
            "rtsp_url": timeline["rtsp_url"],
            "trust_level": "content_hash_bound",
            "raw_recording": {
                "canonical_file": str(self.production_raw_file.resolve()),
                "size_bytes": self.production_raw_file.stat().st_size,
                "sha256": self.production_media_sha256,
            },
            "artifacts": {
                "timeline_report": {
                    "file": "live_timeline_report.json",
                    "size_bytes": 1,
                    "sha256": "a" * 64,
                }
            },
        }
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        return timeline

    def segment(self, report, index=0):
        return report["segments"][index]

    def test_evaluate_exposes_expected_capture_id_trust_anchor(self):
        self.assertIn(
            "expected_capture_id", inspect.signature(evaluate_evidence).parameters
        )

    def test_ocr_is_auxiliary_and_never_opens_the_gate(self):
        report = evaluate_fixture(
            synthetic_timeline_report(),
            synthetic_audio_inventory("absent"),
            ocr_report=synthetic_ocr_report(),
            expected_capture_id=CAPTURE_ID,
        )

        segment = self.segment(report)
        self.assertEqual("blocked", segment["decision"])
        self.assertFalse(segment["production_allowed"])
        self.assertEqual([], segment["primary_evidence_refs"])
        self.assertEqual(
            ["ocr://segment-1/result-1"], segment["auxiliary_evidence_refs"]
        )
        self.assertIn("primary_semantic_evidence_missing", segment["evidence_gaps"])

    def test_present_audio_only_makes_asr_schedulable(self):
        report = evaluate_fixture(
            synthetic_timeline_report(),
            synthetic_audio_inventory("present"),
            expected_capture_id=CAPTURE_ID,
        )

        segment = self.segment(report)
        self.assertEqual("present", segment["audio_state"])
        self.assertFalse(segment["production_allowed"])
        self.assertIn("asr_result_missing_or_invalid", segment["evidence_gaps"])
        self.assertIn("audio_present_asr_schedulable", segment["reasons"])

    def test_audio_present_without_asr_records_gap_even_when_vlm_is_valid(self):
        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            vlm_results=self.production_semantic_result("vlm"),
            expected_capture_id=CAPTURE_ID,
        )

        segment = self.segment(report)
        self.assertTrue(segment["production_allowed"])
        self.assertIn("asr_result_missing_or_invalid", segment["evidence_gaps"])
        self.assertIn("valid_vlm_primary_evidence", segment["reasons"])

    def test_audio_inventory_requires_raw_path_or_capture_id_match(self):
        without_identity = synthetic_timeline_report(capture_id=None)
        without_identity["raw_recording"] = {"file": None}
        wrong_singleton = synthetic_audio_inventory(
            "present", path="C:/other/capture.mkv", capture_id="other-capture"
        )
        path_mismatch = synthetic_audio_inventory(
            "present", path="C:/other/capture.mkv", capture_id=None
        )

        cases = [
            (without_identity, wrong_singleton),
            (synthetic_timeline_report(), path_mismatch),
        ]
        for timeline, inventory in cases:
            with self.subTest(timeline=timeline, inventory=inventory):
                report = evaluate_fixture(
                    timeline, inventory, expected_capture_id=CAPTURE_ID
                )
                self.assertEqual("unknown", report["audio_state"])

        capture_scoped = synthetic_timeline_report()
        capture_scoped["raw_recording"] = {"file": None}
        matching_by_capture_id = synthetic_audio_inventory(
            "present", path="C:/other/capture.mkv", capture_id=CAPTURE_ID
        )
        report = evaluate_fixture(
            capture_scoped,
            matching_by_capture_id,
            expected_capture_id=CAPTURE_ID,
        )
        self.assertEqual("present", report["audio_state"])

        matching_capture_with_different_inventory_path = synthetic_audio_inventory(
            "present", path="contract-test/renamed-capture.mkv", capture_id=CAPTURE_ID
        )
        report = evaluate_fixture(
            synthetic_timeline_report(),
            matching_capture_with_different_inventory_path,
            expected_capture_id=CAPTURE_ID,
        )
        self.assertEqual("present", report["audio_state"])

    def test_vlm_configuration_or_file_presence_does_not_replace_a_valid_result(self):
        invalid_results = [
            synthetic_semantic_result("vlm", summary="  "),
            synthetic_semantic_result("vlm", model_id=""),
            synthetic_semantic_result("vlm", evidence_refs=[]),
            synthetic_semantic_result("vlm", segment_index=2),
            synthetic_semantic_result("vlm", start_s=1.01, end_s=1.1),
            synthetic_semantic_result("vlm", capture_id=None),
            synthetic_semantic_result("vlm", capture_id="other-capture"),
            {"configured": True, "result_file": "configured-output.json", "results": []},
        ]

        for invalid_vlm in invalid_results:
            with self.subTest(invalid_vlm=invalid_vlm):
                report = evaluate_fixture(
                    synthetic_timeline_report(),
                    synthetic_audio_inventory("absent"),
                    vlm_results=invalid_vlm,
                    expected_capture_id=CAPTURE_ID,
                )
                segment = self.segment(report)
                self.assertFalse(segment["production_allowed"])
                self.assertIn("vlm_result_missing_or_invalid", segment["evidence_gaps"])

    def test_successful_live_report_and_valid_asr_allow_production(self):
        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=self.production_semantic_result("asr"),
            expected_capture_id=CAPTURE_ID,
        )

        segment = self.segment(report)
        self.assertEqual("production_pass", segment["decision"])
        self.assertTrue(segment["production_allowed"])
        self.assertEqual(["asr://segment-1/result-1"], segment["primary_evidence_refs"])
        self.assertEqual("live_rtsp", segment["source_kind"])
        self.assertEqual("production", segment["execution_scope"])
        self.assertTrue(report["production_allowed"])
        self.assertEqual(CAPTURE_ID, report.get("capture_id"))
        self.assertEqual("content_hash_bound", report.get("trust_level"))

    def test_recorded_old_tiny_equivalent_thirteen_segments_are_not_quality_evidence(self):
        # Keep the historical tiny-segment regression self-contained.  Tests
        # must not depend on a cleaned capture directory from a prior run.
        old_results = [
            {"start_s": index * 0.1, "end_s": index * 0.1 + 0.05, "text": f"tiny-{index}"}
            for index in range(13)
        ]
        segments = [
            {
                "segment_index": index,
                "start_s": float(result["start_s"]),
                "end_s": float(result["end_s"]),
                "evidence_files": [f"frame-{index}.jpg"],
            }
            for index, result in enumerate(old_results, start=1)
        ]
        timeline = self.production_timeline(
            segments=segments,
            timeline_duration_s=segments[-1]["end_s"],
            capture_wall_s=segments[-1]["end_s"] + 0.5,
        )
        asr_report = {
            "capture_id": CAPTURE_ID,
            "source_media_sha256": self.production_media_sha256,
            "results": [],
        }
        for index, old_result in enumerate(old_results, start=1):
            result = copy.deepcopy(old_result)
            result.update(
                {
                    "capture_id": CAPTURE_ID,
                    "segment_index": index,
                    "source_media_sha256": self.production_media_sha256,
                }
            )
            for quality_field in (
                "quality_status",
                "quality_reasons",
                "quality_summary",
            ):
                result.pop(quality_field, None)
            asr_report["results"].append(result)

        report = evaluate_evidence(
            timeline,
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=asr_report,
            expected_capture_id=CAPTURE_ID,
        )

        self.assertFalse(report["production_allowed"])
        self.assertIn("asr_quality_missing_or_invalid", report["evidence_gaps"])
        self.assertEqual(13, len(report["asr_quality_audit"]["results"]))

    def test_asr_quality_missing_nonfinite_or_threshold_mismatch_is_blocked(self):
        invalid_reports = []

        missing_status = self.production_semantic_result("asr")
        missing_status.pop("quality_status")
        invalid_reports.append(missing_status)

        nonfinite_summary = self.production_semantic_result("asr")
        nonfinite_summary["quality_summary"]["mean_avg_logprob"] = float("nan")
        invalid_reports.append(nonfinite_summary)

        missing_thresholds = self.production_semantic_result("asr")
        missing_thresholds["quality_summary"].pop("quality_thresholds")
        invalid_reports.append(missing_thresholds)

        missing_result_summary = self.production_semantic_result("asr")
        missing_result_summary["results"][0].pop("quality_summary")
        invalid_reports.append(missing_result_summary)

        inconsistent_result_thresholds = self.production_semantic_result("asr")
        inconsistent_result_thresholds["results"][0]["quality_summary"][
            "quality_thresholds"
        ]["max_no_speech_prob"] = 0.9
        invalid_reports.append(inconsistent_result_thresholds)

        for invalid_asr in invalid_reports:
            with self.subTest(invalid_asr=invalid_asr):
                report = evaluate_evidence(
                    self.production_timeline(),
                    synthetic_audio_inventory(
                        "present", path=str(self.production_raw_file)
                    ),
                    asr_results=invalid_asr,
                    expected_capture_id=CAPTURE_ID,
                )

                self.assertFalse(report["production_allowed"])
                self.assertIn(
                    "asr_quality_missing_or_invalid", report["evidence_gaps"]
                )

    def test_failed_asr_quality_is_audited_and_cannot_be_bypassed_by_vlm(self):
        failed_asr = self.production_semantic_result("asr")
        failed_asr["quality_status"] = "fail"
        failed_asr["quality_reasons"] = ["mean_avg_logprob_below_threshold"]
        failed_asr["quality_summary"]["quality_status"] = "fail"
        failed_asr["quality_summary"]["quality_reasons"] = [
            "mean_avg_logprob_below_threshold"
        ]

        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=failed_asr,
            vlm_results=self.production_semantic_result("vlm"),
            expected_capture_id=CAPTURE_ID,
        )

        self.assertFalse(report["production_allowed"])
        self.assertIn("asr_quality_failed", report["evidence_gaps"])
        self.assertEqual(
            ["mean_avg_logprob_below_threshold"],
            report["asr_quality_audit"]["report"]["quality_reasons"],
        )

    def test_failed_asr_segment_quality_is_audited_and_blocked(self):
        failed_asr = self.production_semantic_result("asr")
        failed_result = failed_asr["results"][0]
        failed_result["quality_status"] = "fail"
        failed_result["quality_reasons"] = ["no_valid_speech_segments"]
        failed_result["quality_summary"]["quality_status"] = "fail"
        failed_result["quality_summary"]["quality_reasons"] = [
            "no_valid_speech_segments"
        ]

        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=failed_asr,
            expected_capture_id=CAPTURE_ID,
        )

        self.assertFalse(report["production_allowed"])
        self.assertIn("asr_quality_failed", report["evidence_gaps"])
        self.assertEqual(
            ["no_valid_speech_segments"],
            report["asr_quality_audit"]["results"][0]["quality_reasons"],
        )

    def test_fake_pass_with_real_tiny_mean_is_recomputed_and_failed(self):
        fake_pass = self.production_semantic_result("asr")
        for quality_summary in (
            fake_pass["quality_summary"],
            fake_pass["results"][0]["quality_summary"],
        ):
            quality_summary["mean_avg_logprob"] = -0.83383
            quality_summary["quality_status"] = "pass"
            quality_summary["quality_reasons"] = []

        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=fake_pass,
            expected_capture_id=CAPTURE_ID,
        )

        self.assertFalse(report["production_allowed"])
        self.assertIn("asr_quality_failed", report["evidence_gaps"])
        metric = report["asr_quality_audit"]["report"]["evaluated_metrics"][
            "mean_avg_logprob"
        ]
        self.assertEqual(-0.83383, metric["actual"])
        self.assertEqual(-0.6, metric["threshold"])
        self.assertFalse(metric["passed"])

    def test_production_uses_versioned_gate_policy_not_report_selected_thresholds(self):
        fake_pass = self.production_semantic_result("asr")
        attacker_thresholds = {
            "min_text_coverage_ratio": -1,
            "min_mean_avg_logprob": -100,
            "max_no_speech_prob": 2,
        }
        fake_pass["quality_thresholds"] = dict(attacker_thresholds)
        for quality_summary in (
            fake_pass["quality_summary"],
            fake_pass["results"][0]["quality_summary"],
        ):
            quality_summary["quality_thresholds"] = dict(attacker_thresholds)
            quality_summary["mean_avg_logprob"] = -10.0
            quality_summary["max_no_speech_prob"] = 0.9
            quality_summary["text_coverage_ratio"] = 0.1
            quality_summary["quality_status"] = "pass"
            quality_summary["quality_reasons"] = []

        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=fake_pass,
            expected_capture_id=CAPTURE_ID,
        )

        self.assertEqual("blocked", report["decision"])
        self.assertEqual(
            {
                "policy_id": "asr_quality_gate_v1",
                "min_text_coverage_ratio": 0.8,
                "min_mean_avg_logprob": -0.6,
                "max_no_speech_prob": 0.6,
            },
            report["quality_policy"],
        )
        audit = report["asr_quality_audit"]["report"]
        self.assertEqual(attacker_thresholds, audit["claimed_quality_thresholds"])
        self.assertEqual(-0.6, audit["evaluated_metrics"]["mean_avg_logprob"]["threshold"])
        self.assertIn(
            "mean_avg_logprob_below_threshold",
            audit["recomputed_quality_reasons"],
        )

    def test_top_quality_counts_equal_sum_of_timeline_result_summaries(self):
        impossible = self.production_semantic_result("asr")
        impossible["quality_summary"]["segment_count"] = 999
        impossible["quality_summary"]["valid_quality_segment_count"] = 999
        impossible["quality_summary"]["speech_segment_count"] = 999
        impossible["quality_summary"]["transcribed_segment_count"] = 999

        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=impossible,
            expected_capture_id=CAPTURE_ID,
        )

        self.assertEqual("blocked", report["decision"])
        self.assertIn("asr_quality_missing_or_invalid", report["evidence_gaps"])

    def test_valid_unassigned_raw_segment_is_quality_failure_and_vlm_cannot_bypass(self):
        asr_report = self.production_semantic_result("asr")
        top_summary = asr_report["quality_summary"]
        result_summary = asr_report["results"][0]["quality_summary"]
        for key in (
            "segment_count",
            "valid_quality_segment_count",
            "speech_segment_count",
            "transcribed_segment_count",
        ):
            top_summary[key] = 9
            result_summary[key] = 8
        asr_report["alignment_summary"] = {
            "raw_segment_count": 9,
            "assigned_raw_segment_count": 8,
            "unassigned_raw_segment_ids": [9],
        }

        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=asr_report,
            vlm_results=self.production_semantic_result("vlm"),
            expected_capture_id=CAPTURE_ID,
        )

        self.assertEqual("blocked", report["decision"])
        self.assertIn("asr_quality_failed", report["evidence_gaps"])
        self.assertNotIn("asr_quality_missing_or_invalid", report["evidence_gaps"])
        self.assertTrue(
            all(not segment["production_allowed"] for segment in report["segments"])
        )
        audit = report["asr_quality_audit"]
        self.assertEqual([9], audit["alignment_summary"]["unassigned_raw_segment_ids"])
        self.assertIn(
            "raw_segments_unaligned_to_timeline",
            audit["recomputed_quality_reasons"],
        )
        self.assertIn(
            "raw_segments_unaligned_to_timeline", report["asr_quality_reasons"]
        )

    def test_valid_v2_quality_rejection_is_not_misreported_as_missing_result(self):
        asr_report = self.production_semantic_result("asr")
        top_summary = asr_report["quality_summary"]
        result_summary = asr_report["results"][0]["quality_summary"]
        top_summary.update(
            {
                "quality_status": "fail",
                "quality_reasons": [
                    "raw_segment_time_out_of_bounds",
                    "raw_segments_unaligned_to_timeline",
                ],
                "segment_count": 17,
                "valid_quality_segment_count": 14,
                "speech_segment_count": 14,
                "transcribed_segment_count": 14,
                "invalid_quality_segment_ids": [15, 16, 17],
            }
        )
        for key in (
            "segment_count",
            "valid_quality_segment_count",
            "speech_segment_count",
            "transcribed_segment_count",
        ):
            result_summary[key] = 14
        asr_report.update(
            {
                "quality_status": "fail",
                "quality_reasons": [
                    "raw_segment_time_out_of_bounds",
                    "raw_segments_unaligned_to_timeline",
                ],
                "alignment_summary": {
                    "raw_segment_count": 17,
                    "assigned_raw_segment_count": 14,
                    "unassigned_raw_segment_ids": [15, 16, 17],
                },
            }
        )

        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=asr_report,
            vlm_results=self.production_semantic_result("vlm"),
            expected_capture_id=CAPTURE_ID,
        )

        segment = self.segment(report)
        self.assertEqual("blocked", report["decision"])
        self.assertIn("asr_quality_failed", segment["evidence_gaps"])
        self.assertIn(
            "asr_result_rejected_by_quality_gate", segment["evidence_gaps"]
        )
        self.assertIn("primary_semantic_evidence_missing", segment["evidence_gaps"])
        self.assertNotIn("asr_result_missing_or_invalid", segment["evidence_gaps"])
        self.assertNotIn("valid_vlm_primary_evidence", segment["reasons"])
        self.assertEqual([], segment["primary_evidence_refs"])

    def test_alignment_summary_missing_or_inconsistent_is_structurally_invalid(self):
        missing = self.production_semantic_result("asr")
        missing.pop("alignment_summary")

        raw_mismatch = self.production_semantic_result("asr")
        raw_mismatch["alignment_summary"]["raw_segment_count"] = 999

        assigned_mismatch = self.production_semantic_result("asr")
        assigned_mismatch["alignment_summary"]["assigned_raw_segment_count"] = 0

        wrong_id_count = self.production_semantic_result("asr")
        wrong_id_count["alignment_summary"] = {
            "raw_segment_count": 2,
            "assigned_raw_segment_count": 1,
            "unassigned_raw_segment_ids": [],
        }
        wrong_id_count["quality_summary"]["segment_count"] = 2

        duplicate_ids = self.production_semantic_result("asr")
        duplicate_ids["alignment_summary"] = {
            "raw_segment_count": 3,
            "assigned_raw_segment_count": 1,
            "unassigned_raw_segment_ids": [9, 9],
        }
        duplicate_ids["quality_summary"]["segment_count"] = 3

        for invalid_asr in (
            missing,
            raw_mismatch,
            assigned_mismatch,
            wrong_id_count,
            duplicate_ids,
        ):
            with self.subTest(invalid_asr=invalid_asr):
                report = evaluate_evidence(
                    self.production_timeline(),
                    synthetic_audio_inventory(
                        "present", path=str(self.production_raw_file)
                    ),
                    asr_results=invalid_asr,
                    expected_capture_id=CAPTURE_ID,
                )
                self.assertEqual("blocked", report["decision"])
                self.assertIn(
                    "asr_quality_missing_or_invalid", report["evidence_gaps"]
                )

    def test_invalid_quality_segment_ids_match_invalid_count_and_are_unique_ids(self):
        wrong_length = self.production_semantic_result("asr")
        for summary in (
            wrong_length["quality_summary"],
            wrong_length["results"][0]["quality_summary"],
        ):
            summary["valid_quality_segment_count"] = 0
            summary["speech_segment_count"] = 0
            summary["transcribed_segment_count"] = 0

        duplicate_ids = copy.deepcopy(wrong_length)
        for summary in (
            duplicate_ids["quality_summary"],
            duplicate_ids["results"][0]["quality_summary"],
        ):
            summary["segment_count"] = 2
            summary["invalid_quality_segment_ids"] = [7, 7]

        invalid_id_type = copy.deepcopy(wrong_length)
        for summary in (
            invalid_id_type["quality_summary"],
            invalid_id_type["results"][0]["quality_summary"],
        ):
            summary["invalid_quality_segment_ids"] = [{"id": 7}]

        for invalid_asr in (wrong_length, duplicate_ids, invalid_id_type):
            with self.subTest(invalid_asr=invalid_asr):
                report = evaluate_evidence(
                    self.production_timeline(),
                    synthetic_audio_inventory(
                        "present", path=str(self.production_raw_file)
                    ),
                    asr_results=invalid_asr,
                    expected_capture_id=CAPTURE_ID,
                )
                self.assertEqual("blocked", report["decision"])
                self.assertIn(
                    "asr_quality_missing_or_invalid", report["evidence_gaps"]
                )

    def test_coverage_aliases_must_agree_and_be_unit_interval_when_both_present(self):
        mismatch = self.production_semantic_result("asr")
        mismatch["quality_summary"]["nonempty_emitted_segment_ratio"] = 0.9
        mismatch["quality_summary"]["text_coverage_ratio"] = 1.0

        out_of_range = self.production_semantic_result("asr")
        out_of_range["results"][0]["quality_summary"][
            "nonempty_emitted_segment_ratio"
        ] = 1.1

        for invalid_asr in (mismatch, out_of_range):
            with self.subTest(invalid_asr=invalid_asr):
                report = evaluate_evidence(
                    self.production_timeline(),
                    synthetic_audio_inventory(
                        "present", path=str(self.production_raw_file)
                    ),
                    asr_results=invalid_asr,
                    expected_capture_id=CAPTURE_ID,
                )
                self.assertEqual("blocked", report["decision"])
                self.assertIn(
                    "asr_quality_missing_or_invalid", report["evidence_gaps"]
                )

    def test_claimed_and_recomputed_quality_reasons_are_separate_and_stable(self):
        fake_pass = self.production_semantic_result("asr")
        for summary in (
            fake_pass["quality_summary"],
            fake_pass["results"][0]["quality_summary"],
        ):
            summary["mean_avg_logprob"] = -0.7
            summary["quality_status"] = "pass"
            summary["quality_reasons"] = []

        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=fake_pass,
            expected_capture_id=CAPTURE_ID,
        )

        audit = report["asr_quality_audit"]["report"]
        self.assertEqual([], audit["claimed_quality_reasons"])
        self.assertEqual(
            ["mean_avg_logprob_below_threshold"],
            audit["recomputed_quality_reasons"],
        )
        self.assertEqual(
            ["mean_avg_logprob_below_threshold"], report["asr_quality_reasons"]
        )

    def test_quality_threshold_relationships_and_count_hierarchy_are_recomputed(self):
        low_coverage = self.production_semantic_result("asr")
        low_coverage["quality_summary"]["text_coverage_ratio"] = 0.2

        high_no_speech = self.production_semantic_result("asr")
        high_no_speech["results"][0]["quality_summary"][
            "max_no_speech_prob"
        ] = 0.8

        fractional_count = self.production_semantic_result("asr")
        fractional_count["quality_summary"]["segment_count"] = 1.5

        impossible_hierarchy = self.production_semantic_result("asr")
        impossible_hierarchy["quality_summary"]["transcribed_segment_count"] = 2

        cases = [
            (low_coverage, "asr_quality_failed"),
            (high_no_speech, "asr_quality_failed"),
            (fractional_count, "asr_quality_missing_or_invalid"),
            (impossible_hierarchy, "asr_quality_missing_or_invalid"),
        ]
        for invalid_asr, expected_gap in cases:
            with self.subTest(expected_gap=expected_gap, invalid_asr=invalid_asr):
                report = evaluate_evidence(
                    self.production_timeline(),
                    synthetic_audio_inventory(
                        "present", path=str(self.production_raw_file)
                    ),
                    asr_results=invalid_asr,
                    expected_capture_id=CAPTURE_ID,
                )
                self.assertFalse(report["production_allowed"])
                self.assertIn(expected_gap, report["evidence_gaps"])

    def test_nonempty_emitted_segment_ratio_is_the_preferred_coverage_metric(self):
        asr_report = self.production_semantic_result("asr")
        for quality_summary in (
            asr_report["quality_summary"],
            asr_report["results"][0]["quality_summary"],
        ):
            quality_summary.pop("text_coverage_ratio")
            quality_summary["nonempty_emitted_segment_ratio"] = 1.0

        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=asr_report,
            expected_capture_id=CAPTURE_ID,
        )

        self.assertTrue(report["production_allowed"])

    def test_asr_results_collection_rejects_non_dict_duplicate_and_extra_items(self):
        base = self.production_semantic_result("asr")
        duplicate = copy.deepcopy(base)
        duplicate["results"].append(copy.deepcopy(duplicate["results"][0]))
        mixed_non_dict = copy.deepcopy(base)
        mixed_non_dict["results"].append(None)
        missing_index = copy.deepcopy(base)
        missing_index["results"].append(
            {**copy.deepcopy(missing_index["results"][0]), "segment_index": None}
        )
        out_of_timeline = copy.deepcopy(base)
        out_of_timeline["results"].append(
            {**copy.deepcopy(out_of_timeline["results"][0]), "segment_index": 2}
        )

        for invalid_asr in [duplicate, mixed_non_dict, missing_index, out_of_timeline]:
            with self.subTest(invalid_asr=invalid_asr):
                report = evaluate_evidence(
                    self.production_timeline(),
                    synthetic_audio_inventory(
                        "present", path=str(self.production_raw_file)
                    ),
                    asr_results=invalid_asr,
                    expected_capture_id=CAPTURE_ID,
                )
                self.assertFalse(report["production_allowed"])
                self.assertIn(
                    "asr_results_collection_invalid", report["evidence_gaps"]
                )

    def test_vlm_results_collection_rejects_non_dict_and_missing_segments(self):
        mixed_non_dict = self.production_semantic_result("vlm")
        mixed_non_dict["results"].append(None)
        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("absent", path=str(self.production_raw_file)),
            vlm_results=mixed_non_dict,
            expected_capture_id=CAPTURE_ID,
        )
        self.assertFalse(report["production_allowed"])
        self.assertIn("vlm_results_collection_invalid", report["evidence_gaps"])

        two_segments = [
            {
                "segment_index": 1,
                "start_s": 0.0,
                "end_s": 1.0,
                "evidence_files": ["frame-1.jpg"],
            },
            {
                "segment_index": 2,
                "start_s": 1.0,
                "end_s": 2.0,
                "evidence_files": ["frame-2.jpg"],
            },
        ]
        report = evaluate_evidence(
            self.production_timeline(
                segments=two_segments,
                timeline_duration_s=2.0,
                capture_wall_s=2.5,
            ),
            synthetic_audio_inventory("absent", path=str(self.production_raw_file)),
            vlm_results=self.production_semantic_result("vlm"),
            expected_capture_id=CAPTURE_ID,
        )
        self.assertFalse(report["production_allowed"])
        self.assertIn("vlm_results_collection_invalid", report["evidence_gaps"])

    def test_production_requires_report_level_capture_id_for_asr_and_vlm(self):
        invalid_reports = [
            (
                "asr",
                self.production_semantic_result("asr", report_capture_id=None),
                "asr_report_capture_id_missing",
            ),
            (
                "asr",
                self.production_semantic_result(
                    "asr", report_capture_id="other-capture"
                ),
                "asr_report_capture_id_mismatch",
            ),
            (
                "vlm",
                self.production_semantic_result("vlm", report_capture_id=None),
                "vlm_report_capture_id_missing",
            ),
            (
                "vlm",
                self.production_semantic_result(
                    "vlm", report_capture_id="other-capture"
                ),
                "vlm_report_capture_id_mismatch",
            ),
        ]

        for kind, invalid_report, expected_gap in invalid_reports:
            with self.subTest(kind=kind, expected_gap=expected_gap):
                kwargs = {f"{kind}_results": invalid_report}
                report = evaluate_evidence(
                    self.production_timeline(),
                    synthetic_audio_inventory(
                        "present" if kind == "asr" else "absent",
                        path=str(self.production_raw_file),
                    ),
                    expected_capture_id=CAPTURE_ID,
                    **kwargs,
                )

                self.assertFalse(report["production_allowed"])
                self.assertIn(expected_gap, report["evidence_gaps"])

    def test_invalid_supplied_asr_report_cannot_be_bypassed_by_valid_vlm(self):
        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=self.production_semantic_result(
                "asr", report_capture_id="other-capture"
            ),
            vlm_results=self.production_semantic_result("vlm"),
            expected_capture_id=CAPTURE_ID,
        )

        self.assertFalse(report["production_allowed"])
        self.assertIn("asr_report_capture_id_mismatch", report["evidence_gaps"])

    def test_production_binds_report_and_segment_media_hashes(self):
        invalid_reports = [
            (
                "asr",
                self.production_semantic_result(
                    "asr",
                    report_media_sha256=None,
                    source_media_sha256=self.production_media_sha256,
                ),
                "asr_report_source_media_sha256_missing",
            ),
            (
                "vlm",
                self.production_semantic_result(
                    "vlm",
                    report_media_sha256="0" * 64,
                    source_media_sha256=self.production_media_sha256,
                ),
                "vlm_report_source_media_sha256_mismatch",
            ),
            (
                "asr",
                self.production_semantic_result(
                    "asr", source_media_sha256="0" * 64
                ),
                "asr_result_source_media_sha256_mismatch",
            ),
            (
                "vlm",
                self.production_semantic_result(
                    "vlm", source_media_sha256="0" * 64
                ),
                "vlm_result_source_media_sha256_mismatch",
            ),
        ]

        for kind, invalid_report, expected_gap in invalid_reports:
            with self.subTest(kind=kind, expected_gap=expected_gap):
                report = evaluate_evidence(
                    self.production_timeline(),
                    synthetic_audio_inventory(
                        "present" if kind == "asr" else "absent",
                        path=str(self.production_raw_file),
                    ),
                    expected_capture_id=CAPTURE_ID,
                    **{f"{kind}_results": invalid_report},
                )

                self.assertFalse(report["production_allowed"])
                self.assertEqual("insufficient", report["trust_level"])
                self.assertIn(expected_gap, report["evidence_gaps"])

    def test_production_reads_raw_file_and_verifies_declared_sha256(self):
        missing_path = Path(self._production_temp.name) / "missing.mkv"
        cases = [
            (
                self.production_timeline(raw_overrides={"sha256": None}),
                "raw_recording_sha256_required_for_production",
            ),
            (
                self.production_timeline(raw_overrides={"sha256": "0" * 64}),
                "raw_recording_sha256_mismatch",
            ),
            (
                production_timeline_report(missing_path),
                "raw_recording_file_missing_for_production",
            ),
        ]

        for timeline, expected_gap in cases:
            with self.subTest(expected_gap=expected_gap):
                report = evaluate_evidence(
                    timeline,
                    synthetic_audio_inventory("absent", capture_id=CAPTURE_ID),
                    vlm_results=self.production_semantic_result("vlm"),
                    expected_capture_id=CAPTURE_ID,
                )

                self.assertFalse(report["production_allowed"])
                self.assertEqual("insufficient", report["trust_level"])
                self.assertIn(expected_gap, report["evidence_gaps"])

    def test_production_requires_matching_external_expected_capture_id(self):
        for expected_capture_id, expected_gap in [
            (None, "expected_capture_id_required_for_production"),
            ("other-capture", "expected_capture_id_mismatch"),
        ]:
            with self.subTest(expected_capture_id=expected_capture_id):
                report = evaluate_evidence(
                    self.production_timeline(),
                    synthetic_audio_inventory(
                        "absent", path=str(self.production_raw_file)
                    ),
                    vlm_results=self.production_semantic_result("vlm"),
                    expected_capture_id=expected_capture_id,
                )

                self.assertEqual("blocked", report["decision"])
                self.assertFalse(report["production_allowed"])
                self.assertIn(expected_gap, report["evidence_gaps"])

    def test_production_requires_raw_recording_capture_binding_and_file(self):
        base = self.production_timeline()
        invalid_raw_recordings = [
            None,
            {"file": str(self.production_raw_file)},
            {
                "file": str(self.production_raw_file),
                "capture_id": "other-capture",
            },
            {"file": None, "capture_id": CAPTURE_ID},
            {"file": "  ", "capture_id": CAPTURE_ID},
        ]

        for raw_recording in invalid_raw_recordings:
            with self.subTest(raw_recording=raw_recording):
                timeline = {**base, "raw_recording": raw_recording}
                report = evaluate_evidence(
                    timeline,
                    synthetic_audio_inventory("absent"),
                    vlm_results=self.production_semantic_result("vlm"),
                    expected_capture_id=CAPTURE_ID,
                )

                self.assertFalse(report["production_allowed"])
                self.assertIn(
                    "raw_recording_capture_binding_required_for_production",
                    report["evidence_gaps"],
                )

    def test_source_kind_claim_does_not_replace_live_transport_proof(self):
        base = self.production_timeline()
        invalid_sources = [
            {**base, "source": "C:/recording.mkv"},
            {**base, "rtsp_url": "C:/recording.mkv"},
            {**base, "rtsp_url": "rtsp://127.0.0.1:8555/other"},
            {**base, "mode": "local_replay_visual_timeline"},
            {**base, "source": None},
        ]

        for timeline in invalid_sources:
            with self.subTest(timeline=timeline):
                report = evaluate_evidence(
                    timeline,
                    synthetic_audio_inventory("absent"),
                    vlm_results=self.production_semantic_result("vlm"),
                    expected_capture_id=CAPTURE_ID,
                )
                self.assertFalse(report["production_allowed"])
                self.assertIn(
                    "live_rtsp_source_required_for_production", report["evidence_gaps"]
                )

    def test_producer_canonical_live_mode_is_accepted_only_with_complete_trust_contract(self):
        timeline = self.canonical_live_timeline()
        valid = evaluate_evidence(
            timeline,
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=self.production_semantic_result("asr"),
            expected_capture_id=CAPTURE_ID,
        )
        self.assertEqual("production_pass", valid["decision"])
        self.assertTrue(valid["production_allowed"])

        invalid_timelines = []
        for field in (
            "acquisition_source_kind",
            "analysis_source_kind",
            "analysis_wall_s",
            "capture_wall_s",
            "trust_level",
            "production_usable",
            "manifest_id",
            "manifest_file",
        ):
            missing = copy.deepcopy(timeline)
            missing.pop(field)
            invalid_timelines.append(missing)
        invalid_timelines.extend(
            [
                {**timeline, "mode": "passive_rtsp_live_visual_timeline"},
                {**timeline, "analysis_source_kind": "local_replay"},
                {**timeline, "analysis_wall_s": 0},
                {**timeline, "trust_level": "insufficient"},
                {**timeline, "production_usable": False},
                {**timeline, "manifest_id": "manifest_other"},
            ]
        )
        for invalid_timeline in invalid_timelines:
            with self.subTest(invalid_timeline=invalid_timeline):
                report = evaluate_evidence(
                    invalid_timeline,
                    synthetic_audio_inventory(
                        "present", path=str(self.production_raw_file)
                    ),
                    asr_results=self.production_semantic_result("asr"),
                    expected_capture_id=CAPTURE_ID,
                )
                self.assertEqual("blocked", report["decision"])

    def test_canonical_mode_never_upgrades_local_replay_or_no_raw_fast_path(self):
        local_replay = self.canonical_live_timeline()
        local_replay["source_kind"] = "local_replay"
        no_raw = self.canonical_live_timeline()
        no_raw["raw_recording"] = {
            "capture_id": CAPTURE_ID,
            "error": "raw_recording_disabled",
        }

        for timeline in (local_replay, no_raw):
            with self.subTest(timeline=timeline):
                report = evaluate_evidence(
                    timeline,
                    synthetic_audio_inventory(
                        "present", path=str(self.production_raw_file)
                    ),
                    asr_results=self.production_semantic_result("asr"),
                    expected_capture_id=CAPTURE_ID,
                )
                self.assertEqual("blocked", report["decision"])

    def test_production_requires_nonempty_capture_id(self):
        for capture_id in [None, "", "  "]:
            with self.subTest(capture_id=capture_id):
                report = evaluate_evidence(
                    self.production_timeline(capture_id=capture_id),
                    synthetic_audio_inventory(
                        "absent",
                        path=str(self.production_raw_file),
                        capture_id=capture_id,
                    ),
                    vlm_results=self.production_semantic_result(
                        "vlm",
                        report_capture_id=capture_id,
                        capture_id=capture_id,
                    ),
                    expected_capture_id=CAPTURE_ID,
                )
                self.assertFalse(report["production_allowed"])
                self.assertIn(
                    "capture_id_required_for_production", report["evidence_gaps"]
                )

    def test_timeline_requires_frame_counts_unique_bounded_segments_and_evidence(self):
        base = synthetic_timeline_report()
        duplicate_segments = [base["segments"][0], dict(base["segments"][0])]
        invalid_timelines = [
            {**base, "sampled_frames": 0},
            {**base, "decoded_frames": 0},
            {**base, "timeline_duration_s": 0},
            {**base, "capture_wall_s": 0},
            {**base, "segments": duplicate_segments},
            {
                **base,
                "segments": [
                    {**base["segments"][0], "start_s": -0.1},
                ],
            },
            {
                **base,
                "segments": [
                    {**base["segments"][0], "end_s": 1.01},
                ],
            },
            {
                **base,
                "capture_wall_s": 0.5,
                "segments": [
                    {**base["segments"][0], "end_s": 0.75},
                ],
            },
            {
                **base,
                "segments": [
                    {**base["segments"][0], "evidence_files": []},
                ],
            },
            {
                **base,
                "segments": [
                    {**base["segments"][0], "evidence_files": ["  "]},
                ],
            },
            synthetic_timeline_report(
                timeline_duration_s=2.0,
                capture_wall_s=2.5,
                segments=[
                    {
                        "segment_index": 1,
                        "start_s": 0.0,
                        "end_s": 1.0,
                        "evidence_files": ["frame-1.jpg"],
                    },
                    {
                        "segment_index": 3,
                        "start_s": 1.0,
                        "end_s": 2.0,
                        "evidence_files": ["frame-2.jpg"],
                    },
                ],
            ),
            synthetic_timeline_report(
                timeline_duration_s=2.0,
                capture_wall_s=2.5,
                segments=[
                    {
                        "segment_index": 1,
                        "start_s": 0.01,
                        "end_s": 1.0,
                        "evidence_files": ["frame-1.jpg"],
                    },
                    {
                        "segment_index": 2,
                        "start_s": 1.0,
                        "end_s": 2.0,
                        "evidence_files": ["frame-2.jpg"],
                    },
                ],
            ),
            synthetic_timeline_report(
                timeline_duration_s=2.0,
                capture_wall_s=2.5,
                segments=[
                    {
                        "segment_index": 1,
                        "start_s": 0.0,
                        "end_s": 1.0,
                        "evidence_files": ["frame-1.jpg"],
                    },
                    {
                        "segment_index": 2,
                        "start_s": 0.5,
                        "end_s": 1.5,
                        "evidence_files": ["frame-2.jpg"],
                    },
                ],
            ),
        ]

        for timeline in invalid_timelines:
            with self.subTest(timeline=timeline):
                report = evaluate_fixture(
                    timeline,
                    synthetic_audio_inventory("present"),
                    asr_results=synthetic_semantic_result("asr"),
                    expected_capture_id=CAPTURE_ID,
                )
                self.assertFalse(report["production_allowed"])
                self.assertIn("timeline_report_invalid", report["evidence_gaps"])

    def test_local_replay_never_allows_production(self):
        report = evaluate_evidence(
            self.production_timeline(source_kind="local_replay"),
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=self.production_semantic_result("asr"),
            expected_capture_id=CAPTURE_ID,
        )

        segment = self.segment(report)
        self.assertFalse(segment["production_allowed"])
        self.assertEqual("blocked", segment["decision"])
        self.assertIn("local_replay_not_production_source", segment["reasons"])

    def test_fixture_only_passes_contract_test_with_both_markers(self):
        fixture_timeline = synthetic_timeline_report()

        successful_contract = evaluate_evidence(
            fixture_timeline,
            synthetic_audio_inventory("present"),
            asr_results=synthetic_semantic_result("asr"),
            execution_scope="contract_test",
            contract_test=True,
        )
        segment = self.segment(successful_contract)
        self.assertEqual("contract_test_pass", segment["decision"])
        self.assertFalse(segment["production_allowed"])
        self.assertEqual("contract_test", segment["execution_scope"])

        for scope, marker in [("production", True), ("contract_test", False)]:
            with self.subTest(scope=scope, marker=marker):
                rejected = evaluate_evidence(
                    fixture_timeline,
                    synthetic_audio_inventory("present"),
                    asr_results=synthetic_semantic_result("asr"),
                    execution_scope=scope,
                    contract_test=marker,
                    expected_capture_id=(
                        CAPTURE_ID if scope == "production" else None
                    ),
                )
                rejected_segment = self.segment(rejected)
                self.assertEqual("blocked", rejected_segment["decision"])
                self.assertFalse(rejected_segment["production_allowed"])
                self.assertIn(
                    "fixture_requires_explicit_contract_test",
                    rejected_segment["evidence_gaps"],
                )

        markerless_fixture = dict(fixture_timeline)
        markerless_fixture.pop("fixture")
        rejected = evaluate_evidence(
            markerless_fixture,
            synthetic_audio_inventory("present"),
            asr_results=synthetic_semantic_result("asr"),
            execution_scope="contract_test",
            contract_test=True,
        )
        self.assertEqual("blocked", rejected["decision"])
        self.assertIn(
            "fixture_marker_required_for_contract_test", rejected["evidence_gaps"]
        )

    def test_fixture_marker_cannot_be_reused_by_production(self):
        timeline = {**self.production_timeline(), "fixture": True}
        report = evaluate_evidence(
            timeline,
            synthetic_audio_inventory("absent", path=str(self.production_raw_file)),
            vlm_results=self.production_semantic_result("vlm"),
            expected_capture_id=CAPTURE_ID,
        )

        self.assertFalse(report["production_allowed"])
        self.assertIn("fixture_marker_forbidden_in_production", report["evidence_gaps"])

    def test_contract_test_marker_always_blocks_production(self):
        report = evaluate_evidence(
            synthetic_timeline_report(),
            synthetic_audio_inventory("present"),
            asr_results=synthetic_semantic_result("asr"),
            execution_scope="production",
            contract_test=True,
            expected_capture_id=CAPTURE_ID,
        )

        self.assertEqual("blocked", report["decision"])
        self.assertFalse(report["production_allowed"])
        self.assertIn(
            "contract_test_marker_forbidden_in_production", report["evidence_gaps"]
        )

    def test_synthetic_capture_without_audio_or_vlm_is_blocked_even_with_ocr(self):
        report = evaluate_evidence(
            synthetic_timeline_report(),
            synthetic_audio_inventory("absent"),
            ocr_report=synthetic_ocr_report(),
            execution_scope="contract_test",
            contract_test=True,
        )

        segment = self.segment(report)
        self.assertEqual("absent", segment["audio_state"])
        self.assertEqual("blocked", segment["decision"])
        self.assertIn("audio_absent", segment["evidence_gaps"])
        self.assertIn("primary_semantic_evidence_missing", segment["evidence_gaps"])

    def test_audio_probe_error_maps_to_unknown_not_absent(self):
        report = evaluate_fixture(
            synthetic_timeline_report(),
            synthetic_audio_inventory("unknown"),
            expected_capture_id=CAPTURE_ID,
        )

        segment = self.segment(report)
        self.assertEqual("unknown", segment["audio_state"])
        self.assertNotIn("audio_absent", segment["evidence_gaps"])
        self.assertIn("audio_state_unknown", segment["evidence_gaps"])

    def test_asr_requires_capture_segment_time_and_evidence_binding(self):
        invalid_asr_results = [
            synthetic_semantic_result("asr", capture_id=None),
            synthetic_semantic_result("asr", capture_id="other-capture"),
            synthetic_semantic_result("asr", segment_index=2),
            synthetic_semantic_result("asr", start_s=1.01, end_s=1.1),
            synthetic_semantic_result("asr", evidence_refs=[]),
            synthetic_semantic_result("asr", text="\t"),
        ]

        for invalid_asr in invalid_asr_results:
            with self.subTest(invalid_asr=invalid_asr):
                report = evaluate_fixture(
                    synthetic_timeline_report(),
                    synthetic_audio_inventory("present"),
                    asr_results=invalid_asr,
                    expected_capture_id=CAPTURE_ID,
                )
                segment = self.segment(report)
                self.assertFalse(segment["production_allowed"])
                self.assertIn("asr_result_missing_or_invalid", segment["evidence_gaps"])

    def test_valid_vlm_allows_production_when_audio_is_absent(self):
        report = evaluate_evidence(
            self.production_timeline(),
            synthetic_audio_inventory("absent", path=str(self.production_raw_file)),
            vlm_results=self.production_semantic_result("vlm"),
            expected_capture_id=CAPTURE_ID,
        )

        segment = self.segment(report)
        self.assertTrue(segment["production_allowed"])
        self.assertEqual(["vlm://segment-1/result-1"], segment["primary_evidence_refs"])
        self.assertEqual("absent", segment["audio_state"])

    def test_missing_asr_segment_invalidates_the_entire_report(self):
        timeline = self.production_timeline(
            timeline_duration_s=2.0,
            capture_wall_s=2.5,
            segments=[
                {
                    "segment_index": 1,
                    "start_s": 0.0,
                    "end_s": 1.0,
                    "evidence_files": ["frame-1.jpg"],
                },
                {
                    "segment_index": 2,
                    "start_s": 1.0,
                    "end_s": 2.0,
                    "evidence_files": ["frame-2.jpg"],
                },
            ],
        )

        report = evaluate_evidence(
            timeline,
            synthetic_audio_inventory("present", path=str(self.production_raw_file)),
            asr_results=self.production_semantic_result("asr"),
            expected_capture_id=CAPTURE_ID,
        )

        self.assertFalse(report["segments"][0]["production_allowed"])
        self.assertFalse(report["segments"][1]["production_allowed"])
        self.assertFalse(report["production_allowed"])
        self.assertIn("asr_results_collection_invalid", report["evidence_gaps"])

    def test_recorded_live_report_without_capture_id_is_blocked(self):
        timeline = self.production_timeline(capture_id="")
        timeline["raw_recording"]["capture_id"] = ""
        report = evaluate_evidence(
            timeline,
            {"files": []},
            expected_capture_id=CAPTURE_ID,
        )

        self.assertEqual("live_rtsp", timeline["source_kind"])
        self.assertFalse(report["production_allowed"])
        self.assertEqual("insufficient", report["trust_level"])
        self.assertIn("capture_id_required_for_production", report["evidence_gaps"])
        self.assertIn(
            "raw_recording_capture_binding_required_for_production",
            report["evidence_gaps"],
        )

    def test_recorded_replay_report_is_blocked(self):
        timeline = self.production_timeline(source_kind="local_replay")
        report = evaluate_evidence(
            timeline,
            {"files": []},
            expected_capture_id=CAPTURE_ID,
        )

        self.assertEqual("local_replay", timeline["source_kind"])
        self.assertFalse(report["production_allowed"])
        self.assertIn("live_rtsp_source_required_for_production", report["evidence_gaps"])

    def _write_cli_inputs(self, temp):
        paths = {
            "timeline": temp / "timeline.json",
            "audio": temp / "audio.json",
            "asr": temp / "asr.json",
            "vlm": temp / "vlm.json",
            "ocr": temp / "ocr.json",
            "output": temp / "gate.json",
            "raw": temp / "captured-live-media.mkv",
        }
        paths["raw"].write_bytes(b"cli bound live transport media\x00\x02")
        payloads = {
            "timeline": synthetic_timeline_report(),
            "audio": synthetic_audio_inventory("present"),
            "asr": synthetic_semantic_result("asr"),
            "vlm": synthetic_semantic_result("vlm"),
            "ocr": synthetic_ocr_report(),
        }
        for name, payload in payloads.items():
            paths[name].write_text(json.dumps(payload), encoding="utf-8")
        return paths

    def _run_cli(self, paths, *, output=None, extra_args=None):
        args = [
            sys.executable,
            str(SCRIPTS / "semantic_evidence_gate.py"),
            "--timeline-report",
            str(paths["timeline"]),
            "--audio-inventory",
            str(paths["audio"]),
            "--asr-results",
            str(paths["asr"]),
            "--vlm-results",
            str(paths["vlm"]),
            "--ocr-report",
            str(paths["ocr"]),
            "--output",
            str(output or paths["output"]),
        ]
        args.extend(extra_args or [])
        return subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_uses_distinct_exit_codes_for_pass_block_and_input_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            paths = self._write_cli_inputs(temp)

            passed = self._run_cli(
                paths,
                extra_args=["--execution-scope", "contract_test", "--contract-test"],
            )
            self.assertEqual(0, passed.returncode, passed.stderr)

            blocked = self._run_cli(
                paths, extra_args=["--expected-capture-id", CAPTURE_ID]
            )
            self.assertEqual(3, blocked.returncode, blocked.stderr)
            output = json.loads(paths["output"].read_text(encoding="utf-8"))
            self.assertEqual("blocked", output["decision"])

            paths["timeline"].write_text("{not-json", encoding="utf-8")
            invalid = self._run_cli(
                paths, extra_args=["--expected-capture-id", CAPTURE_ID]
            )
            self.assertEqual(2, invalid.returncode, invalid.stderr)
            input_error = json.loads(paths["output"].read_text(encoding="utf-8"))
            self.assertEqual("input_error", input_error["status"])
            self.assertTrue(input_error["errors"])

    def test_cli_production_requires_matching_expected_capture_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            paths = self._write_cli_inputs(temp)
            production_timeline = production_timeline_report(paths["raw"])
            media_sha256 = production_timeline["raw_recording"]["sha256"]
            paths["timeline"].write_text(
                json.dumps(production_timeline), encoding="utf-8"
            )
            paths["asr"].write_text(
                json.dumps(
                    synthetic_semantic_result(
                        "asr", report_media_sha256=media_sha256
                    )
                ),
                encoding="utf-8",
            )
            paths["vlm"].write_text(
                json.dumps(
                    synthetic_semantic_result(
                        "vlm", report_media_sha256=media_sha256
                    )
                ),
                encoding="utf-8",
            )

            missing = self._run_cli(paths)
            self.assertEqual(2, missing.returncode, missing.stderr)
            input_error = json.loads(paths["output"].read_text(encoding="utf-8"))
            self.assertEqual("input_error", input_error["status"])
            self.assertTrue(input_error["errors"])

            mismatch = self._run_cli(
                paths, extra_args=["--expected-capture-id", "other-capture"]
            )
            self.assertEqual(3, mismatch.returncode, mismatch.stderr)

            matched = self._run_cli(
                paths, extra_args=["--expected-capture-id", CAPTURE_ID]
            )
            self.assertEqual(0, matched.returncode, matched.stderr)

    def test_cli_missing_input_file_writes_structured_input_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            paths = self._write_cli_inputs(temp)
            paths["timeline"] = temp / "missing-timeline.json"

            completed = self._run_cli(
                paths,
                extra_args=["--execution-scope", "contract_test", "--contract-test"],
            )

            self.assertEqual(2, completed.returncode, completed.stderr)
            self.assertTrue(paths["output"].is_file())
            output = json.loads(paths["output"].read_text(encoding="utf-8"))
            self.assertEqual("input_error", output["status"])
            self.assertTrue(output["errors"])

    def test_cli_rejects_nonstandard_json_constants_with_structured_input_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for constant in ("NaN", "Infinity", "-Infinity"):
                paths = self._write_cli_inputs(temp)
                paths["timeline"].write_text(
                    '{"nonstandard": ' + constant + "}", encoding="utf-8"
                )

                completed = self._run_cli(
                    paths,
                    extra_args=[
                        "--execution-scope",
                        "contract_test",
                        "--contract-test",
                    ],
                )

                with self.subTest(constant=constant):
                    self.assertEqual(2, completed.returncode, completed.stderr)
                    output = json.loads(paths["output"].read_text(encoding="utf-8"))
                    self.assertEqual("input_error", output["status"])

    def test_atomic_json_writer_rejects_nonfinite_output_without_replacing_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "gate.json"
            output.write_text('{"status":"existing"}\n', encoding="utf-8")

            with self.assertRaises(ValueError):
                semantic_evidence_gate._atomic_write_json(
                    output, {"decision": "blocked", "nonfinite": float("nan")}
                )

            self.assertEqual(
                '{"status":"existing"}\n', output.read_text(encoding="utf-8")
            )

    def test_cli_input_error_atomically_replaces_existing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            paths = self._write_cli_inputs(temp)
            paths["timeline"].write_text("{invalid-json", encoding="utf-8")
            paths["output"].write_text("stale", encoding="utf-8")
            replacements = []
            original_replace = Path.replace

            def recording_replace(path, target):
                replacements.append((path, Path(target)))
                return original_replace(path, target)

            with (
                mock.patch.object(Path, "replace", recording_replace),
                mock.patch("sys.stdout", new_callable=io.StringIO),
            ):
                exit_code = semantic_evidence_gate.main(
                    [
                        "--timeline-report",
                        str(paths["timeline"]),
                        "--audio-inventory",
                        str(paths["audio"]),
                        "--execution-scope",
                        "contract_test",
                        "--contract-test",
                        "--output",
                        str(paths["output"]),
                    ]
                )

            self.assertEqual(2, exit_code)
            self.assertEqual(1, len(replacements))
            output = json.loads(paths["output"].read_text(encoding="utf-8"))
            self.assertEqual("input_error", output["status"])
            self.assertTrue(output["errors"])

    def test_cli_unwritable_output_reports_input_error_to_stderr(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            paths = self._write_cli_inputs(temp)
            unwritable_output = temp / "existing-directory"
            unwritable_output.mkdir()

            completed = self._run_cli(
                paths,
                output=unwritable_output,
                extra_args=["--execution-scope", "contract_test", "--contract-test"],
            )

            self.assertEqual(2, completed.returncode)
            self.assertTrue(completed.stderr.strip())
            self.assertTrue(unwritable_output.is_dir())

    def test_cli_rejects_output_that_overlaps_any_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for conflicting_name in ["timeline", "audio", "asr", "vlm", "ocr"]:
                paths = self._write_cli_inputs(temp)
                original = paths[conflicting_name].read_text(encoding="utf-8")
                with self.subTest(conflicting_name=conflicting_name):
                    completed = self._run_cli(
                        paths,
                        output=paths[conflicting_name],
                        extra_args=[
                            "--execution-scope",
                            "contract_test",
                            "--contract-test",
                        ],
                    )
                    self.assertEqual(2, completed.returncode, completed.stderr)
                    self.assertEqual(
                        original, paths[conflicting_name].read_text(encoding="utf-8")
                    )

    def test_cli_atomically_replaces_the_output_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            paths = self._write_cli_inputs(temp)
            paths["output"].write_text("stale", encoding="utf-8")

            original_replace = Path.replace
            replacements = []

            def recording_replace(path, target):
                replacements.append((path, Path(target)))
                return original_replace(path, target)

            with (
                mock.patch.object(Path, "replace", recording_replace),
                mock.patch("sys.stdout", new_callable=io.StringIO),
            ):
                exit_code = semantic_evidence_gate.main(
                    [
                        "--timeline-report",
                        str(paths["timeline"]),
                        "--audio-inventory",
                        str(paths["audio"]),
                        "--asr-results",
                        str(paths["asr"]),
                        "--vlm-results",
                        str(paths["vlm"]),
                        "--ocr-report",
                        str(paths["ocr"]),
                        "--execution-scope",
                        "contract_test",
                        "--contract-test",
                        "--output",
                        str(paths["output"]),
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertEqual(1, len(replacements))
            temporary_path, target_path = replacements[0]
            self.assertEqual(paths["output"], target_path)
            self.assertEqual(paths["output"].parent, temporary_path.parent)
            self.assertNotEqual(paths["output"], temporary_path)
            self.assertFalse(temporary_path.exists())
            output = json.loads(paths["output"].read_text(encoding="utf-8"))
            self.assertEqual("contract_test_pass", output["decision"])


if __name__ == "__main__":
    unittest.main()
