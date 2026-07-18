from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
DEMO_APP = ROOT / "demo_app"
sys.path.insert(0, str(DEMO_APP))

import server


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class DemoAppTests(unittest.TestCase):
    def setUp(self):
        captures = ROOT / "captures"
        captures.mkdir(exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=captures)
        self.run_dir = Path(self.temp_dir.name)
        self.video = self.run_dir / "raw_rtsp_copy.mkv"
        self.video.write_bytes(b"demo video bytes")
        self.media_sha = sha256_file(self.video)
        write_json(
            self.run_dir / "full_video_understanding_report.json",
            {
                "capture_id": "cap_demo_app_001",
                "source_media_sha256": self.media_sha,
                "input_media_path": str(self.video),
                "media": {"duration_s": 2.0},
            },
        )
        write_json(
            self.run_dir / "learning_evidence_bundle.json",
            {"demo_usable": True, "truth_label": "已实测"},
        )
        write_json(
            self.run_dir / "evidence_cards.json",
            [
                {
                    "card_id": "card_0001",
                    "start_s": 0.0,
                    "end_s": 1.5,
                    "video_event_summary": "片段证据",
                }
            ],
        )
        write_json(
            self.run_dir / "microtasks.json",
            [
                {
                    "microtask_id": "task_0001",
                    "type": "explain",
                    "lightweight_action": "解释片段概念。",
                    "evidence_card_id": "card_0001",
                }
            ],
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_demo_payload_checks_video_sha_and_returns_cards(self):
        payload = server.load_demo_payload(self.run_dir)

        self.assertTrue(payload["demo_usable"])
        self.assertEqual("已实测", payload["truth_label"])
        self.assertEqual(1, len(payload["cards"]))
        self.assertIn("/api/video", payload["video_url"])

    def test_sha_mismatch_is_rejected(self):
        report_path = self.run_dir / "full_video_understanding_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["source_media_sha256"] = "b" * 64
        write_json(report_path, report)

        with self.assertRaises(HTTPException) as raised:
            server.load_demo_payload(self.run_dir)

        self.assertEqual(422, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
