from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from vlm_innovation.cache import EvidenceAwareVisualCache  # noqa: E402
from vlm_innovation.contracts import CacheQuality, EvidenceWindowKey, InnovationContractError  # noqa: E402
from vlm_innovation.dataset import assign_video_level_splits, audit_dataset, build_evidence_index, require_training_eligible  # noqa: E402
from vlm_innovation.features import FEATURE_NAMES, extract_record_features  # noqa: E402
from vlm_innovation.smolvlm_visual_cache import SmolVlmVisualTokenAdapter  # noqa: E402
from vlm_innovation.evaluation import InnovationContractError as EvaluationContractError, Prediction, Variant, evaluate  # noqa: E402
from vlm_innovation.validate_label_export import audit_export  # noqa: E402
from vlm_innovation.import_authorized_bundle import import_bundle  # noqa: E402


HASH = "a" * 64


class VlmInnovationTests(unittest.TestCase):
    def test_video_level_split_never_leaks_one_group(self) -> None:
        records = [
            {"record_id": f"r{index}", "source_video_group": group}
            for index, group in enumerate(("a", "a", "b", "c", "d"), 1)
        ]
        split = assign_video_level_splits(records, seed="test")
        mapping = {record["source_video_group"]: record["split"] for record in split}
        self.assertEqual(mapping["a"], split[1]["split"])
        self.assertEqual({"train", "validation", "test"}, {record["split"] for record in split})

    def test_diagnostic_single_video_is_not_training_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "media").mkdir()
            (root / "evidence").mkdir()
            (root / "media" / "one.mp4").write_bytes(b"media")
            for lane in ("ocr", "asr", "vlm"):
                (root / "evidence" / f"one.{lane}.json").write_text("{}", encoding="utf-8")
            record = {"record_id": "one", "source_video_group": "one-source", "split": "diagnostic_holdout_only", "video": "media/one.mp4", "evidence": {lane: f"evidence/one.{lane}.json" for lane in ("ocr", "asr", "vlm")}}
            (root / "manifest.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
            audit = audit_dataset(root)
            self.assertTrue(audit.ok)
            with self.assertRaises(InnovationContractError):
                require_training_eligible(audit)

    def test_cache_refuses_cross_visit_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            cache = EvidenceAwareVisualCache(Path(temp), max_bytes=4096)
            source = EvidenceWindowKey("session", "visit-1", HASH, 0, 1_000, "model-v1")
            quality = CacheQuality(0.1, 0.9, 0.1)
            block = cache.keep(source, quality, b"visual-token-payload", token_count=3, encoding="visual-embedding.fp16")
            denied = cache.reuse(block.block_id, EvidenceWindowKey("session", "visit-2", HASH, 1_000, 2_000, "model-v1"), target_quality=quality, max_gap_ns=1_000)
            self.assertIsNone(denied)
            allowed = cache.reuse(block.block_id, EvidenceWindowKey("session", "visit-1", HASH, 1_000, 2_000, "model-v1"), target_quality=quality, max_gap_ns=1_000)
            self.assertEqual(b"visual-token-payload", allowed)

    def test_evidence_index_refuses_mismatched_lane_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "media").mkdir()
            (root / "evidence").mkdir()
            media = root / "media" / "one.mp4"
            media.write_bytes(b"real-media")
            media_hash = hashlib.sha256(b"real-media").hexdigest()
            window_id = "s:window:1"
            for lane in ("ocr", "asr"):
                (root / "evidence" / f"one.{lane}.json").write_text(json.dumps({"window_id": window_id, "input_media_sha256": media_hash, "coverage_start_pts_ns": 1, "coverage_end_pts_ns": 2}), encoding="utf-8")
            (root / "evidence" / "one.vlm.json").write_text(json.dumps({"window_id": window_id, "media_sha256": "b" * 64, "coverage": {"start_pts_ns": 1, "end_pts_ns": 2}}), encoding="utf-8")
            record = {"record_id": "one", "source_session": "s", "source_video_group": "g", "split": "diagnostic_holdout_only", "window_id": window_id, "video": "media/one.mp4", "evidence": {lane: f"evidence/one.{lane}.json" for lane in ("ocr", "asr", "vlm")}}
            (root / "manifest.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaises(InnovationContractError):
                build_evidence_index(root)

    def test_feature_export_preserves_unavailable_runtime_masks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "media").mkdir()
            (root / "evidence").mkdir()
            (root / "media" / "one.mp4").write_bytes(b"media")
            for lane, payload in {
                "ocr": {"result": {"samples": [{"raw": [[[], "关注", 0.9], [[], "线性代数", 0.9]]}]}},
                "asr": {"result": {"segments": [{"text": "矩阵的秩", "confidence": 0.8}]}},
                "vlm": {"raw_model_text": "A matrix is shown on screen."},
            }.items():
                (root / "evidence" / f"one.{lane}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            record = {"record_id": "one", "source_video_group": "g", "split": "diagnostic_holdout_only", "window_id": "s:1", "video": "media/one.mp4", "evidence": {lane: f"evidence/one.{lane}.json" for lane in ("ocr", "asr", "vlm")}, "manual_diagnostic": {"ui_interference": "重度"}}
            row = extract_record_features(record, root)
            self.assertEqual(len(FEATURE_NAMES), len(row["features"]))
            self.assertEqual(0.0, row["features"][FEATURE_NAMES.index("content_change_available")])

    def test_cached_visual_generation_removes_pixels_without_changing_prompt(self) -> None:
        inputs = {"input_ids": "prompt", "pixel_values": "pixels", "pixel_attention_mask": "mask"}
        prepared = SmolVlmVisualTokenAdapter.replace_pixels_with_cached_hidden(inputs, "encoded")
        self.assertEqual("prompt", prepared["input_ids"])
        self.assertEqual("encoded", prepared["image_hidden_states"])
        self.assertNotIn("pixel_values", prepared)

    def test_ablation_evaluator_rejects_single_video_group(self) -> None:
        rows = []
        for variant in Variant:
            rows.append(Prediction(variant, "one", "single-video", True, False, False, True, True, 10.0, 100.0, 50.0, False, 1.0, "技术演示"))
        with self.assertRaises(EvaluationContractError):
            evaluate(rows)

    def test_label_export_rejects_old_incomplete_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            export = Path(temp) / "annotations.jsonl"
            export.write_text(json.dumps({"annotation_id": 1, "dataset_record_id": "r1", "ground_truth": False, "result": [{"from_name": "topic"}]}) + "\n", encoding="utf-8")
            report = audit_export(export)
            self.assertFalse(report["eligible_for_training_supervision"])
            self.assertEqual(1, report["missing_required_v2_fields"])

    def test_authorized_import_preserves_source_hash_and_requires_real_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, artifacts, destination = root / "source", root / "source" / "artifacts", root / "destination"
            (artifacts / "windows").mkdir(parents=True)
            video = artifacts / "windows" / "item.mp4"
            video.write_bytes(b"sealed-media")
            media_hash = hashlib.sha256(b"sealed-media").hexdigest()
            window = "session-1:window:000001"
            (artifacts / "item.full-video-vlm.json").write_text(json.dumps({"window_id": window, "media_sha256": media_hash, "coverage": {"start_pts_ns": 1, "end_pts_ns": 9}}), encoding="utf-8")
            for lane in ("ocr", "asr"):
                (artifacts / f"item.{lane}.json").write_text(json.dumps({"window_id": window, "input_media_sha256": media_hash, "coverage_start_pts_ns": 1, "coverage_end_pts_ns": 9}), encoding="utf-8")
            result = import_bundle(source_root=source, destination=destination, source_video_group="open-video-a", verified_source_video_hash="c" * 64, rights_basis="OPEN_LICENSE", rights_reference="CC-BY-4.0", content_type="技术演示")
            self.assertEqual("IMPORTED_PENDING_HUMAN_REVIEW", result["status"])
            record = json.loads((destination / "manifest.jsonl").read_text(encoding="utf-8"))
            self.assertEqual("c" * 64, record["verified_source_video_hash"])
            self.assertEqual("PENDING_LABEL_STUDIO_V2_HUMAN_REVIEW", record["annotation_state"])


if __name__ == "__main__":
    unittest.main()
