from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import realtime_fragment_worker as worker  # noqa: E402


class CommandContractTests(unittest.TestCase):
    def test_single_reader_config_carries_one_authorized_rtsp_source(self) -> None:
        config = worker.LiveIngressConfig(
            source="rtsp://10.0.0.2:8554/screen",
            session_id="session-1",
            output_dir=Path("C:/captures/session-1"),
            fragment_seconds=2.0,
        )

        self.assertEqual("rtsp://10.0.0.2:8554/screen", config.source)
        self.assertEqual({"rtsp_transport": "tcp", "stimeout": "5000000"}, worker.reader_options(config))


class FragmenterTests(unittest.TestCase):
    def test_keyframe_starts_and_closes_pts_aligned_fragment(self) -> None:
        fragmenter = worker.PtsFragmenter("session-1", fragment_seconds=2.0)
        self.assertEqual([], fragmenter.accept(worker.IncomingPacket("video", 0, 1, 1_000_000, True, 1_000)))
        self.assertEqual([], fragmenter.accept(worker.IncomingPacket("audio", 0, 1, 1_100_000, False, 1_000)))
        self.assertEqual([], fragmenter.accept(worker.IncomingPacket("video", 1_900, 1, 2_900_000, False, 1_000)))
        closed = fragmenter.accept(worker.IncomingPacket("video", 2_100, 1, 3_100_000, True, 1_000))

        self.assertEqual(1, len(closed))
        self.assertEqual(0, closed[0].start_pts_ns)
        self.assertEqual(2_100_000_000, closed[0].end_pts_ns)
        self.assertTrue(closed[0].has_same_source_audio)

    def test_non_keyframe_video_does_not_start_a_fragment(self) -> None:
        fragmenter = worker.PtsFragmenter("session-1", fragment_seconds=2.0)
        self.assertEqual([], fragmenter.accept(worker.IncomingPacket("video", 0, 1, 1_000_000, False, 1_000)))
        self.assertEqual([], fragmenter.accept(worker.IncomingPacket("audio", 0, 1, 1_100_000, False, 1_000)))


if __name__ == "__main__":
    unittest.main()
