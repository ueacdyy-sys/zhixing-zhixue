from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.candidate_card import CandidateCardBuildError, build_candidate_card  # noqa: E402
from realtime_runtime.contracts import FusedCandidate, FusionMode, SourceContext  # noqa: E402


def fused_candidate(*, evidence_uris: tuple[str, ...]) -> FusedCandidate:
    return FusedCandidate(
        window_id="window-1",
        visit_id="visit-1",
        source_context=SourceContext.PHONE_DAILY,
        start_pts_ns=10,
        end_pts_ns=20,
        evidence_uris=evidence_uris,
        fused_at_ns=30,
        fusion_mode=FusionMode.TRIMODAL,
    )


class CandidateCardTests(unittest.TestCase):
    def write_artifact(self, root: Path, name: str, lane: str, result: dict[str, object]) -> str:
        (root / name).write_text(
            json.dumps(
                {
                    "schema_version": "sealed_window_lane_artifact.v1",
                    "classification": "CANDIDATE_ONLY",
                    "lane": lane,
                    "window_id": "window-1",
                    "coverage_start_pts_ns": 10,
                    "coverage_end_pts_ns": 20,
                    "result": result,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return f"local://artifact/{name}"

    def test_builds_versioned_candidate_card_from_all_three_sealed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = (
                self.write_artifact(root, "asr.json", "ASR", {"segments": [{"text": "两万个角色"}]}),
                self.write_artifact(root, "ocr.json", "OCR", {"samples": [{"raw": [["AI虚拟演员库上线", 0.99]]}]}),
                self.write_artifact(root, "vlm.json", "VLM", {"raw_model_text": "A character library is shown."}),
            )

            card = build_candidate_card(fused_candidate(evidence_uris=evidence), artifact_root=root)

        self.assertEqual("candidate_card.v1", card["schema_version"])
        self.assertEqual("CANDIDATE_ONLY", card["classification"])
        self.assertEqual("window-1", card["window_id"])
        self.assertEqual(["ASR", "OCR", "VLM"], [fact["lane"] for fact in card["facts"]])
        self.assertIn("两万个角色", card["display_excerpt"])
        self.assertEqual("VIEW_EVIDENCE", card["student_action"])
        self.assertIn("不构成兴趣、能力或专注结论", card["uncertainty"])

    def test_rejects_missing_lane_or_cross_window_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            only_asr = self.write_artifact(root, "asr.json", "ASR", {"segments": [{"text": "文本"}]})
            with self.assertRaisesRegex(CandidateCardBuildError, "trimodal_artifact_required"):
                build_candidate_card(fused_candidate(evidence_uris=(only_asr,)), artifact_root=root)

            ocr = self.write_artifact(root, "ocr.json", "OCR", {"samples": []})
            vlm = self.write_artifact(root, "vlm.json", "VLM", {"raw_model_text": "scene"})
            document = json.loads((root / "vlm.json").read_text(encoding="utf-8"))
            document["window_id"] = "other-window"
            (root / "vlm.json").write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(CandidateCardBuildError, "artifact_window_mismatch"):
                build_candidate_card(fused_candidate(evidence_uris=(only_asr, ocr, vlm)), artifact_root=root)


if __name__ == "__main__":
    unittest.main()
