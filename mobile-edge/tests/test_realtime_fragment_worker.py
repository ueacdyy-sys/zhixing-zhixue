from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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
        self.assertEqual({"rtsp_transport": "tcp", "timeout": "15000000"}, worker.reader_options(config))

    def test_stop_signal_is_an_explicit_fact_not_an_inferred_socket_close(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stop_signal = Path(temp_dir) / ".stop-requested"
            config = worker.LiveIngressConfig(
                source="rtsp://10.0.0.2:8554/screen",
                session_id="session-1",
                output_dir=Path(temp_dir),
                stop_signal_file=stop_signal,
            )
            self.assertFalse(worker._stop_requested(config))
            stop_signal.touch()
            self.assertTrue(worker._stop_requested(config))


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

    def test_any_pyav_transport_error_becomes_a_terminal_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = worker.LiveIngressConfig(
                source="rtsp://10.0.0.2:8554/screen",
                session_id="session-1",
                output_dir=Path(temp_dir),
                reconnect_attempts=0,
            )
            with patch.object(worker.av, "open", side_effect=worker.av.error.UndefinedError(138, "rtsp unavailable")):
                with self.assertRaises(worker.IngressTransportInterrupted) as raised:
                    worker.run(config)
                report = raised.exception.report

        self.assertEqual(0, report["fragment_count"])
        self.assertIn("UndefinedError", report["terminal_error"])


class AudioTimelineAlignmentTests(unittest.TestCase):
    def test_packet_pts_alignment_emits_replayable_bounded_sync_evidence(self) -> None:
        alignment = worker._assess_av_timeline_alignment(
            video_pts_ns=(0, 33_000_000, 66_000_000, 99_000_000),
            audio_pts_ns=(0, 20_000_000, 40_000_000, 60_000_000, 80_000_000, 100_000_000),
            max_allowed_sync_error_ns=15_000_000,
        )

        self.assertTrue(alignment.within_tolerance)
        self.assertEqual(7_000_000, alignment.sync_error_ns)
        self.assertEqual(4, alignment.sample_count)
        self.assertEqual(64, len(alignment.sync_sample_hash))

    def test_packet_pts_alignment_fails_closed_when_audio_is_not_near_the_video_timeline(self) -> None:
        alignment = worker._assess_av_timeline_alignment(
            video_pts_ns=(0, 100_000_000, 200_000_000),
            audio_pts_ns=(0, 500_000_000),
            max_allowed_sync_error_ns=120_000_000,
        )

        self.assertFalse(alignment.within_tolerance)
        self.assertEqual(200_000_000, alignment.sync_error_ns)
        self.assertEqual("audio_video_pts_delta_exceeds_policy", alignment.reason)


if __name__ == "__main__":
    unittest.main()
