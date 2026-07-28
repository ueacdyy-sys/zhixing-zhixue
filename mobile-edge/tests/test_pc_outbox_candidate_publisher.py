from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pc_outbox_candidate_publisher import _completed_visit_cards, publish  # noqa: E402


def _window_card(window_id: str, visit_id: str) -> dict[str, object]:
    return {
        "card_id": f"candidate_{window_id}",
        "window_id": window_id,
        "visit_id": visit_id,
        "source_context": "PHONE_DAILY",
        "media_range": {"start_pts_ns": 0, "end_pts_ns": 10},
        "display_excerpt": "候选证据",
        "facts": [
            {"lane": "ASR", "evidence_uri": "local://artifact/asr.json", "text": "语音"},
            {"lane": "OCR", "evidence_uri": "local://artifact/ocr.json", "text": "文字"},
            {"lane": "VLM", "evidence_uri": "local://artifact/vlm.json", "text": "画面"},
        ],
    }


class PcOutboxCandidatePublisherTests(unittest.TestCase):
    def test_completed_visit_becomes_one_non_notifying_l0_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger_path = Path(temp_dir) / "ledger.sqlite3"
            with closing(sqlite3.connect(ledger_path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE visits (visit_id TEXT PRIMARY KEY, end_pts_ns INTEGER);
                    CREATE TABLE fused_candidate_events (
                        window_id TEXT PRIMARY KEY, visit_id TEXT, source_context TEXT,
                        start_pts_ns INTEGER, end_pts_ns INTEGER, evidence_uris_json TEXT,
                        fusion_mode TEXT, fused_at_ns INTEGER, classification TEXT
                    );
                    """
                )
                connection.execute("INSERT INTO visits VALUES (?, ?)", ("visit-1", 20))
                for window_id, start, end in (("window-a", 0, 10), ("window-b", 10, 20)):
                    connection.execute(
                        "INSERT INTO fused_candidate_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (window_id, "visit-1", "PHONE_DAILY", start, end, "[]", "TRIMODAL", 30, "CANDIDATE_ONLY"),
                    )
                connection.commit()
            with patch("pc_outbox_candidate_publisher.build_candidate_card", side_effect=lambda candidate, **_: _window_card(candidate.window_id, candidate.visit_id)):
                cards = _completed_visit_cards(ledger_path, Path(temp_dir))

        self.assertEqual(1, len(cards))
        card, reason = cards[0]
        self.assertEqual("COMPLETED_TRIMODAL_VISIT_L0", reason)
        self.assertEqual("visit-1", card["visit_id"])
        self.assertEqual(2, card["evidence_window_count"])
        self.assertFalse(card["can_offer_l1"])

    @patch("pc_outbox_candidate_publisher.requests.Session")
    def test_publish_persists_l0_message_longer_than_phone_sync_interval(self, session_factory: MagicMock) -> None:
        response = MagicMock(status_code=202)
        response.json.return_value = {"state": "QUEUED"}
        session_factory.return_value.post.return_value = response

        ok, state = publish("https://pc.local", "phone-1", "secret", _window_card("window-a", "visit-1"))

        self.assertTrue(ok)
        self.assertEqual("QUEUED", state)
        _, kwargs = session_factory.return_value.post.call_args
        body = kwargs["json"]
        self.assertFalse(body["payload"]["is_current_visit"])
        self.assertNotIn("notice_title", body["payload"])
        expires_at = datetime.fromisoformat(body["expires_at"])
        issued_at = datetime.fromisoformat(body["payload"]["issued_at"])
        self.assertGreaterEqual((expires_at - issued_at).total_seconds(), 300)


if __name__ == "__main__":
    unittest.main()
