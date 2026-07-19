from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import learning_evidence_builder as builder


CAPTURE_ID = "cap_learning_evidence_001"
MEDIA_SHA = "a" * 64


def passing_understanding() -> dict:
    return {
        "status": "production_ready",
        "production_ready": True,
        "capture_id": CAPTURE_ID,
        "source_media_sha256": MEDIA_SHA,
        "input_media_path": r"C:\captures\raw_rtsp_copy.mkv",
        "input_mode": "canonical_full_video",
        "media": {"duration_s": 3.0},
        "results": [
            {
                "status": "success",
                "segment_index": 1,
                "start_s": 0.0,
                "end_s": 2.0,
                "summary": "视频里围绕月光意象展开了表达。",
                "concepts": ["月光意象"],
                "expressions": ["海浪"],
                "uncertainty": "medium",
                "evidence_refs": ["video:0.00-2.00"],
            }
        ],
    }


def passing_asr() -> dict:
    return {
        "capture_id": CAPTURE_ID,
        "source_media_sha256": MEDIA_SHA,
        "quality_status": "pass",
        "results": [
            {
                "status": "success",
                "segment_index": 1,
                "start_s": 0.0,
                "end_s": 2.0,
                "text": "这段内容提到了月光和海浪。",
                "evidence_refs": ["asr:segment-1"],
            }
        ],
    }


class LearningEvidenceBuilderTests(unittest.TestCase):
    def test_builds_unverified_bundle_without_claiming_demo_usable(self):
        bundle = builder.build_evidence(
            understanding=passing_understanding(),
            asr_report=passing_asr(),
            human_verified=False,
        )

        self.assertTrue(bundle["machine_evidence_ready"])
        self.assertEqual("not_reviewed", bundle["human_review_status"])
        self.assertEqual("needs_offline_sample_review", bundle["competition_acceptance_status"])
        self.assertEqual(1, len(bundle["cards"]))
        self.assertEqual(1, len(bundle["microtasks"]))
        self.assertTrue(bundle["microtasks"][0]["production_allowed"])
        self.assertIn("offline_sample_review_not_recorded", bundle["cards"][0]["evidence_gaps"])

    def test_human_verified_bundle_can_mark_microtask_production_allowed(self):
        bundle = builder.build_evidence(
            understanding=passing_understanding(),
            asr_report=passing_asr(),
            human_verified=True,
        )

        self.assertEqual("accepted", bundle["competition_acceptance_status"])
        self.assertEqual("accepted", bundle["cards"][0]["competition_acceptance_status"])
        self.assertTrue(bundle["microtasks"][0]["production_allowed"])
        self.assertEqual("explain", bundle["microtasks"][0]["type"])

    def test_rejects_vlm_without_high_quality_asr(self):
        asr = passing_asr()
        asr["quality_status"] = "fail"

        with self.assertRaises(builder.EvidenceBuildError) as raised:
            builder.build_evidence(
                understanding=passing_understanding(),
                asr_report=asr,
                human_verified=True,
            )

        self.assertEqual("asr_quality_not_pass", raised.exception.code)

    def test_rejects_event_without_overlapping_asr_text(self):
        asr = passing_asr()
        asr["results"][0]["start_s"] = 2.1
        asr["results"][0]["end_s"] = 2.9

        with self.assertRaises(builder.EvidenceBuildError) as raised:
            builder.build_evidence(
                understanding=passing_understanding(),
                asr_report=asr,
                human_verified=True,
            )

        self.assertEqual("asr_overlap_missing", raised.exception.code)

    def test_rejects_question_or_exercise_microtask_language(self):
        task = {
            "microtask_id": "task_bad",
            "type": "explain",
            "lightweight_action": "给学生出题并推荐练习题。",
            "evidence_card_id": "card_0001",
        }

        with self.assertRaises(builder.EvidenceBuildError) as raised:
            builder.validate_microtask(task)

        self.assertEqual("question_like_microtask_forbidden", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
