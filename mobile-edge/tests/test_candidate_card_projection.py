from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.candidate_card_projection import project_candidate_cards  # noqa: E402
from realtime_runtime.lane_worker import _record_candidate_projection_error  # noqa: E402
from realtime_runtime.contracts import (  # noqa: E402
    Lane,
    LaneEvidence,
    QualityStatus,
    SealedFragment,
    SemanticWindow,
    SourceContext,
    Visit,
)
from realtime_runtime.ledger import SealedWindowLedger  # noqa: E402


HASH = "a" * 64


def artifact(root: Path, lane: Lane) -> str:
    path = root / f"window-1.{lane.value.lower()}.json"
    result = {
        Lane.ASR: {"segments": [{"text": "视频语音内容"}]},
        Lane.OCR: {"samples": [{"raw": [["视频标题", 0.99]]}]},
        Lane.VLM: {"raw_model_text": "A video page is visible."},
    }[lane]
    path.write_text(
        json.dumps(
            {
                "classification": "CANDIDATE_ONLY",
                "lane": lane.value,
                "window_id": "window-1",
                "coverage_start_pts_ns": 0,
                "coverage_end_pts_ns": 2,
                "result": result,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return f"local://artifact/{path.name}"


class CandidateCardProjectionTests(unittest.TestCase):
    def test_projection_failure_is_persisted_without_mutating_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _record_candidate_projection_error(root, ValueError("bad artifact"))
            entries = [json.loads(line) for line in (root / "candidate_card_projection_errors.jsonl").read_text(encoding="utf-8").splitlines()]

        self.assertEqual(["CandidateCardProjectionFailed"], [item["event_type"] for item in entries])
        self.assertEqual("ValueError", entries[0]["error_type"])

    def test_rebuilds_candidate_card_and_visit_snapshot_from_durable_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_root = root / "artifacts"
            artifact_root.mkdir()
            ledger_path = root / "ledger.sqlite"
            with SealedWindowLedger(ledger_path) as ledger:
                ledger.open_visit(Visit("visit-1", "session-1", SourceContext.PHONE_DAILY, 0))
                ledger.append_fragment(
                    SealedFragment("fragment-1", "session-1", SourceContext.PHONE_DAILY, 0, 2, "local://capture/fragment-1.mkv", HASH, True, True, 0, 2)
                )
                ledger.create_window(
                    SemanticWindow("window-1", "session-1", "visit-1", SourceContext.PHONE_DAILY, 0, 2, (HASH,), (Lane.ASR, Lane.OCR, Lane.VLM))
                )
                for index, lane in enumerate((Lane.ASR, Lane.OCR, Lane.VLM), 1):
                    lease = ledger.claim(lane, f"worker-{lane.value}", now_ns=index, lease_ns=100)
                    uri = artifact(artifact_root, lane)
                    ledger.complete(
                        lease,
                        LaneEvidence("window-1", lane, 0, 2, (HASH,), QualityStatus.FUSION_ELIGIBLE, uri, hashlib.sha256(uri.encode()).hexdigest(), index, index + 1),
                    )
                ledger.fuse_ready(now_ns=10)

            output = root / "candidate_cards.v1.json"
            report = project_candidate_cards(ledger_path=ledger_path, artifact_root=artifact_root, output_path=output)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual({"cards": 1, "visits": 1}, report)
        self.assertEqual("candidate_card_projection.v1", payload["schema_version"])
        self.assertTrue(payload["visits"][0]["can_offer_l1"])
        self.assertEqual("window-1", payload["cards"][0]["window_id"])


if __name__ == "__main__":
    unittest.main()
