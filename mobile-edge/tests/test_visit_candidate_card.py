from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.visit_candidate_card import aggregate_visit_cards  # noqa: E402


def card(window_id: str, start: int, end: int, visit_id: str = "visit-a") -> dict[str, object]:
    return {
        "card_id": "candidate_" + window_id,
        "window_id": window_id,
        "visit_id": visit_id,
        "source_context": "PHONE_DAILY",
        "media_range": {"start_pts_ns": start, "end_pts_ns": end},
        "display_excerpt": "同一段视频的分析文本",
        "can_offer_l1": True,
        "facts": [
            {"lane": "ASR", "evidence_uri": f"local://artifact/{window_id}-asr.json", "text": "语音证据"},
            {"lane": "OCR", "evidence_uri": f"local://artifact/{window_id}-ocr.json", "text": "文字证据"},
            {"lane": "VLM", "evidence_uri": f"local://artifact/{window_id}-vlm.json", "text": "画面证据"},
        ],
    }


class VisitCandidateCardTests(unittest.TestCase):
    def test_many_windows_become_one_mobile_visit_card(self) -> None:
        merged = aggregate_visit_cards([card("window-1", 0, 10), card("window-2", 10, 20), card("window-3", 20, 30)])

        self.assertEqual(1, len(merged))
        self.assertTrue(str(merged[0]["card_id"]).startswith("visit_"))
        self.assertEqual("visit-a", merged[0]["visit_id"])
        self.assertEqual(3, merged[0]["evidence_window_count"])
        self.assertEqual(["window-1", "window-2", "window-3"], merged[0]["evidence_window_ids"])
        self.assertEqual(0, merged[0]["media_range"]["start_pts_ns"])
        self.assertEqual(30, merged[0]["media_range"]["end_pts_ns"])

    def test_different_visits_stay_separate(self) -> None:
        merged = aggregate_visit_cards([card("window-1", 0, 10, "visit-a"), card("window-2", 10, 20, "visit-b")])

        self.assertEqual(2, len(merged))


if __name__ == "__main__":
    unittest.main()
