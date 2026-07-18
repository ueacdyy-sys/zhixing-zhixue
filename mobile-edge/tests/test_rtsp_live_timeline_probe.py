from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import rtsp_live_timeline_probe as probe


def valid_probe(duration: float = 1.0) -> dict:
    return {
        "streams": [{"codec_type": "video"}],
        "format": {"duration": str(duration)},
    }


class ScriptedClock:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)
        self._last = values[-1]

    def __call__(self) -> float:
        try:
            self._last = next(self._values)
        except StopIteration:
            pass
        return self._last


class FakeFrame:
    def __init__(self, pts: int) -> None:
        self.pts = pts
        self.time_base = Fraction(1, 1000)

    def to_ndarray(self, *, format: str) -> np.ndarray:
        if format != "bgr24":
            raise AssertionError(f"unexpected frame format: {format}")
        return np.zeros((16, 16, 3), dtype=np.uint8)


class FakePacket:
    def __init__(self, pts: int) -> None:
        self._frame = FakeFrame(pts)

    def decode(self):
        yield self._frame


class FakeCodecContext:
    width = 16
    height = 16


class FakeStream:
    codec_context = FakeCodecContext()


class GuardedLiveContainer:
    """Finite guard around an infinite-like packet source used by the probe."""

    def __init__(self, frame_pts: list[int], max_packets: int = 4) -> None:
        self.streams = type("Streams", (), {"video": [FakeStream()]})()
        self._frame_pts = frame_pts
        self._max_packets = max_packets
        self.demux_yields = 0
        self.close_calls = 0

    def demux(self, stream: FakeStream):
        if stream is not self.streams.video[0]:
            raise AssertionError("probe demuxed an unexpected stream")
        for packet_index in range(self._max_packets):
            self.demux_yields += 1
            pts = self._frame_pts[min(packet_index, len(self._frame_pts) - 1)]
            yield FakePacket(pts)
        raise AssertionError("probe kept consuming packets after the timeline deadline")

    def close(self) -> None:
        self.close_calls += 1


class AnalyzeLiveDeadlineTests(unittest.TestCase):
    def run_probe(
        self,
        *,
        container: GuardedLiveContainer,
        source_is_live: bool,
        clock: ScriptedClock,
    ) -> dict:
        source = "rtsp://test.invalid/screen" if source_is_live else "replay.mkv"
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(probe.av, "open", return_value=container),
                patch.object(probe.time, "perf_counter", side_effect=clock),
            ):
                try:
                    return probe.analyze_live(
                        capture_id="cap_11111111-1111-4111-8111-111111111111",
                        source=source,
                        out_dir=Path(temp_dir),
                        seconds=1.0,
                        sample_interval_s=0.5,
                        segment_s=1.0,
                        save_every_sample=False,
                        rtsp_transport="tcp",
                        open_retries=1,
                        retry_delay_s=0.0,
                        source_is_live=source_is_live,
                        prewarm_iterations=0,
                    )
                finally:
                    self.assertEqual(1, container.close_calls)

    def test_live_deadline_stops_the_outer_demux_loop(self):
        container = GuardedLiveContainer(frame_pts=[0, 1000])
        clock = ScriptedClock(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.1, 1.1)

        report = self.run_probe(
            container=container,
            source_is_live=True,
            clock=clock,
        )

        self.assertEqual(2, container.demux_yields)
        self.assertEqual(2, report["decoded_frames"])
        self.assertEqual(1, report["sampled_frames"])
        self.assertEqual("live_rtsp", report["source_kind"])
        self.assertEqual("cap_11111111-1111-4111-8111-111111111111", report["capture_id"])

    def test_local_replay_still_stops_on_relative_video_time(self):
        container = GuardedLiveContainer(frame_pts=[0, 1000])
        clock = ScriptedClock(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.1)

        report = self.run_probe(
            container=container,
            source_is_live=False,
            clock=clock,
        )

        self.assertEqual(2, container.demux_yields)
        self.assertEqual(2, report["decoded_frames"])
        self.assertEqual(1, report["sampled_frames"])
        self.assertEqual("local_replay", report["source_kind"])
        self.assertEqual("cap_11111111-1111-4111-8111-111111111111", report["capture_id"])


class SegmentBoundaryTests(unittest.TestCase):
    @staticmethod
    def sample(index: int, timeline_s: float, evidence_file: str) -> probe.Sample:
        return probe.Sample(
            sample_index=index,
            source_frame_index=index,
            video_time_s=timeline_s,
            timeline_s=timeline_s,
            capture_wall_s=timeline_s,
            process_wall_ms=1.0,
            width=16,
            height=16,
            full_change=1.0,
            top_change=1.0,
            center_change=1.0,
            subtitle_change=1.0,
            bottom_change=1.0,
            full_luma=1.0,
            subtitle_luma=1.0,
            phash="0" * 16,
            phash_hamming=0,
            evidence_file=evidence_file,
        )

    def test_segments_skip_empty_buckets_and_truncate_the_last_boundary(self):
        samples = [
            self.sample(1, 0.2, "evidence_frames/sample_0001.jpg"),
            self.sample(2, 2.4, "evidence_frames/sample_0002.jpg"),
        ]

        segments = probe.build_segments(
            samples,
            segment_s=1.0,
            shift_threshold=0.5,
            timeline_duration_s=2.4,
        )

        self.assertEqual([1, 2], [segment.segment_index for segment in segments])
        self.assertEqual([1, 1], [segment.sample_count for segment in segments])
        self.assertEqual(2.4, segments[-1].end_s)
        self.assertTrue(all(segment.end_s <= 2.4 for segment in segments))
        self.assertTrue(all(segment.evidence_files for segment in segments))


class MainCaptureIdentityTests(unittest.TestCase):
    CAPTURE_ID_PATTERN = re.compile(
        r"^cap_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )

    def test_local_replay_capture_id_is_generated_once_and_propagated(self):
        observed_capture_ids: list[str] = []

        def fake_analyze_live(**kwargs):
            capture_id = kwargs["capture_id"]
            observed_capture_ids.append(capture_id)
            return {
                "capture_id": capture_id,
                "source": kwargs["source"],
                "source_kind": "local_replay",
                "rtsp_url": None,
                "timeline_duration_s": 0.0,
                "samples": [],
                "segments": [],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            replay = root / "replay.mkv"
            replay.write_bytes(b"local replay")
            argv = ["rtsp_live_timeline_probe.py", "--source", str(replay), "--tag", "identity"]
            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "analyze_live", side_effect=fake_analyze_live),
                patch.object(probe, "ffprobe", return_value={}),
                patch.object(probe.os, "replace", wraps=os.replace) as atomic_replace,
                patch.object(sys, "argv", argv),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            report = json.loads((out_dir / "live_timeline_report.json").read_text(encoding="utf-8"))
            manifest_path = out_dir / "capture_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            markdown = (out_dir / "live_timeline_report.md").read_text(encoding="utf-8")

        capture_id = report["capture_id"]
        self.assertRegex(capture_id, self.CAPTURE_ID_PATTERN)
        self.assertEqual([capture_id], observed_capture_ids)
        self.assertEqual(capture_id, report["raw_recording"]["capture_id"])
        self.assertEqual("local_replay", report["source_kind"])
        expected_hash = hashlib.sha256(b"local replay").hexdigest()
        self.assertNotIn("sha256", report["raw_recording"])
        self.assertNotIn("canonical_file", report["raw_recording"])
        self.assertEqual(expected_hash, report["raw_recording"]["observed_sha256"])
        self.assertEqual(len(b"local replay"), report["raw_recording"]["observed_size_bytes"])
        self.assertEqual("insufficient", report["trust_level"])
        self.assertFalse(report["production_usable"])
        self.assertEqual("local_replay_untrusted_external_source", report["processing_mode"])
        self.assertIn("external_local_replay_not_copied_to_canonical_snapshot", report["trust_limitations"])
        self.assertEqual(report["manifest_id"], manifest["manifest_id"])
        self.assertEqual(str(manifest_path), report["manifest_file"])
        self.assertEqual(capture_id, manifest["capture_id"])
        self.assertEqual("local_replay", manifest["source_kind"])
        self.assertEqual(str(replay), manifest["source"])
        self.assertIsNone(manifest["rtsp_url"])
        self.assertEqual("insufficient", manifest["trust_level"])
        self.assertEqual(
            {
                "observed_size_bytes": len(b"local replay"),
                "observed_sha256": expected_hash,
                "error": "local_replay_external_toctou_untrusted",
            },
            manifest["raw_recording"],
        )
        replace_destinations = [Path(call.args[1]) for call in atomic_replace.call_args_list]
        self.assertIn(manifest_path, replace_destinations)
        self.assertIn(out_dir / "live_timeline_report.json", replace_destinations)
        self.assertFalse(list(out_dir.glob("*.tmp")))
        self.assertIn(f"capture_id: `{capture_id}`", markdown)

    def test_failed_capture_report_keeps_the_same_capture_id(self):
        observed_capture_ids: list[str] = []

        def fail_analyze_live(**kwargs):
            observed_capture_ids.append(kwargs["capture_id"])
            raise RuntimeError("synthetic capture failure")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            replay = root / "replay.mkv"
            argv = ["rtsp_live_timeline_probe.py", "--source", str(replay), "--tag", "failure"]
            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "analyze_live", side_effect=fail_analyze_live),
                patch.object(sys, "argv", argv),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            report = json.loads((out_dir / "live_timeline_report.json").read_text(encoding="utf-8"))
            manifest = json.loads((out_dir / "capture_manifest.json").read_text(encoding="utf-8"))
            markdown = (out_dir / "live_timeline_report.md").read_text(encoding="utf-8")

        capture_id = report["capture_id"]
        self.assertRegex(capture_id, self.CAPTURE_ID_PATTERN)
        self.assertEqual([capture_id], observed_capture_ids)
        self.assertEqual(capture_id, report["raw_recording"]["capture_id"])
        self.assertEqual("local_replay", report["source_kind"])
        self.assertEqual("insufficient", report["trust_level"])
        self.assertEqual("insufficient", manifest["trust_level"])
        self.assertNotIn("sha256", report["raw_recording"])
        self.assertNotIn("sha256", manifest["raw_recording"])
        self.assertIn("synthetic capture failure", report["error"])
        self.assertEqual(capture_id, manifest["capture_id"])
        self.assertEqual(report["manifest_id"], manifest["manifest_id"])
        self.assertIn(f"capture_id: `{capture_id}`", markdown)


class ContentHashBindingTests(unittest.TestCase):
    def test_sha256_file_streams_known_content_without_read_bytes(self):
        content = b"streamed raw recording\x00\xff"
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_file = Path(temp_dir) / "raw.mkv"
            raw_file.write_bytes(content)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("must stream")):
                digest = probe.sha256_file(raw_file, chunk_size=5)

        self.assertEqual(hashlib.sha256(content).hexdigest(), digest)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_sha256_file_rejects_non_positive_chunk_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_file = Path(temp_dir) / "raw.mkv"
            raw_file.write_bytes(b"raw")
            with self.assertRaisesRegex(ValueError, "chunk_size"):
                probe.sha256_file(raw_file, chunk_size=0)

    def test_live_raw_hash_is_computed_only_after_recorder_close(self):
        raw_content = b"completed ffmpeg raw bytes"
        recorder_outputs: list[Path] = []
        analysis_calls: list[dict] = []
        recorder_close_timeouts: list[float | None] = []
        ffprobe_targets: list[Path] = []

        def fake_analyze_live(**kwargs):
            analysis_calls.append(kwargs)
            self.assertFalse(kwargs["source_is_live"])
            self.assertFalse(kwargs["source"].lower().startswith("rtsp://"))
            self.assertEqual(raw_content, Path(kwargs["source"]).read_bytes())
            return {
                "capture_id": kwargs["capture_id"],
                "source": kwargs["source"],
                "source_kind": "local_replay",
                "rtsp_url": None,
                "timeline_duration_s": 1.0,
                "capture_wall_s": 0.25,
                "processing_wall_s": 0.20,
                "samples": [],
                "segments": [],
            }

        def fake_ffprobe(ffprobe_bin, file):
            ffprobe_targets.append(Path(file))
            return valid_probe()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            argv = [
                "rtsp_live_timeline_probe.py",
                "--source",
                "rtsp://test.invalid/screen",
                "--tag",
                "post_close_hash",
                "--seconds",
                "1",
            ]

            def fake_start_raw_recorder(ffmpeg, source, seconds, out_file, log_file):
                recorder_outputs.append(out_file)
                self.assertTrue(out_file.name.endswith(".partial"))
                return object()

            def fake_close_raw_recorder(proc, timeout_s=None):
                recorder_close_timeouts.append(timeout_s)
                recorder_outputs[0].write_bytes(raw_content)
                return 0

            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "port_open", return_value=True),
                patch.object(probe, "start_raw_recorder", side_effect=fake_start_raw_recorder),
                patch.object(probe, "close_raw_recorder", side_effect=fake_close_raw_recorder),
                patch.object(probe, "analyze_live", side_effect=fake_analyze_live),
                patch.object(probe, "ffprobe", side_effect=fake_ffprobe),
                patch.object(probe.time, "perf_counter", side_effect=ScriptedClock(10.0, 13.0)),
                patch.object(sys, "argv", argv),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            report = json.loads((out_dir / "live_timeline_report.json").read_text(encoding="utf-8"))
            manifest = json.loads((out_dir / "capture_manifest.json").read_text(encoding="utf-8"))

        expected_hash = hashlib.sha256(raw_content).hexdigest()
        self.assertEqual(expected_hash, report["raw_recording"]["sha256"])
        self.assertEqual(expected_hash, manifest["raw_recording"]["sha256"])
        self.assertEqual("content_hash_bound", report["trust_level"])
        self.assertEqual(report["capture_id"], manifest["capture_id"])
        self.assertEqual(1, len(recorder_outputs))
        self.assertEqual(1, len(recorder_close_timeouts))
        self.assertGreaterEqual(recorder_close_timeouts[0], 9.0)
        self.assertEqual(1, len(analysis_calls))
        self.assertEqual("live_rtsp", report["acquisition_source_kind"])
        self.assertEqual("canonical_raw_replay", report["analysis_source_kind"])
        self.assertEqual("deferred_trusted_evidence", report["processing_mode"])
        self.assertEqual("deferred_canonical_raw_timeline", report["mode"])
        self.assertEqual(3.0, report["capture_wall_s"])
        self.assertEqual(0.25, report["analysis_wall_s"])
        self.assertEqual("live_rtsp", report["source_kind"])
        self.assertTrue(report["production_usable"])
        self.assertFalse(report["raw_recording"]["canonical_file"].endswith(".partial"))
        self.assertEqual(2, len(ffprobe_targets))
        self.assertTrue(ffprobe_targets[0].name.endswith(".partial"))
        self.assertEqual("raw_rtsp_copy.mkv", ffprobe_targets[1].name)

    def test_content_changed_between_partial_validation_and_canonical_rename_is_rejected(self):
        original = b"original raw bytes"
        changed = b"tampered raw bytes"
        self.assertEqual(len(original), len(changed))
        recorder_outputs: list[Path] = []
        real_replace = os.replace

        def fake_start(ffmpeg, source, seconds, out_file, log_file):
            recorder_outputs.append(out_file)
            return object()

        def fake_close(proc, timeout_s=None):
            recorder_outputs[0].write_bytes(original)
            return 0

        def mutate_before_raw_rename(source, destination):
            source_path = Path(source)
            destination_path = Path(destination)
            if source_path.name.endswith(".partial") and destination_path.name == "raw_rtsp_copy.mkv":
                source_path.write_bytes(changed)
            return real_replace(source, destination)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            argv = [
                "rtsp_live_timeline_probe.py",
                "--source",
                "rtsp://test.invalid/screen",
                "--seconds",
                "1",
                "--tag",
                "rename_toctou",
            ]
            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "port_open", return_value=True),
                patch.object(probe, "start_raw_recorder", side_effect=fake_start),
                patch.object(probe, "close_raw_recorder", side_effect=fake_close),
                patch.object(probe, "ffprobe", return_value=valid_probe()),
                patch.object(probe, "analyze_live", side_effect=AssertionError("changed canonical raw must not be analyzed")),
                patch.object(probe.os, "replace", side_effect=mutate_before_raw_rename),
                patch.object(sys, "argv", argv),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            report = json.loads((out_dir / "live_timeline_report.json").read_text(encoding="utf-8"))
            manifest = json.loads((out_dir / "capture_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual("source_changed_before_canonical_analysis", report["primary_error"])
        self.assertEqual("insufficient", report["trust_level"])
        self.assertFalse(report["production_usable"])
        self.assertNotIn("sha256", report["raw_recording"])
        self.assertEqual(hashlib.sha256(original).hexdigest(), report["raw_recording"]["observed_sha256"])
        self.assertEqual("insufficient", manifest["trust_level"])

    def test_failed_live_recorder_does_not_bind_a_partial_raw_file(self):
        def fake_analyze_live(**kwargs):
            return {
                "capture_id": kwargs["capture_id"],
                "source": kwargs["source"],
                "source_kind": "live_rtsp",
                "rtsp_url": kwargs["source"],
                "samples": [],
                "segments": [],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            argv = [
                "rtsp_live_timeline_probe.py",
                "--source",
                "rtsp://test.invalid/screen",
                "--tag",
                "failed_recorder",
            ]

            recorder_outputs: list[Path] = []

            def fake_start_raw_recorder(ffmpeg, source, seconds, out_file, log_file):
                recorder_outputs.append(out_file)
                return object()

            def fail_close_raw_recorder(proc, timeout_s=None):
                recorder_outputs[0].write_bytes(b"partial raw bytes")
                return 1

            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "port_open", return_value=True),
                patch.object(probe, "start_raw_recorder", side_effect=fake_start_raw_recorder),
                patch.object(probe, "close_raw_recorder", side_effect=fail_close_raw_recorder),
                patch.object(probe, "analyze_live", side_effect=AssertionError("partial raw must not be analyzed")),
                patch.object(probe, "ffprobe", return_value=valid_probe()),
                patch.object(sys, "argv", argv),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            report = json.loads((out_dir / "live_timeline_report.json").read_text(encoding="utf-8"))
            manifest = json.loads((out_dir / "capture_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual("insufficient", report["trust_level"])
        self.assertEqual("insufficient", manifest["trust_level"])
        self.assertNotIn("sha256", report["raw_recording"])
        self.assertNotIn("sha256", manifest["raw_recording"])
        self.assertEqual("raw_recorder_failed_exit_code_1", report["raw_recording"]["error"])
        self.assertEqual(hashlib.sha256(b"partial raw bytes").hexdigest(), report["raw_recording"]["observed_sha256"])
        self.assertEqual(len(b"partial raw bytes"), report["raw_recording"]["observed_size_bytes"])


class OutputDirectorySafetyTests(unittest.TestCase):
    def test_output_directory_contains_capture_and_manifest_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            captures = Path(temp_dir) / "captures"
            output = probe.create_capture_output_dir(
                captures,
                tag="safe-tag_1.0",
                stamp="20260711_120000",
                capture_id="cap_11111111-1111-4111-8111-111111111111",
                manifest_id="manifest_22222222-2222-4222-8222-222222222222",
            )

            self.assertTrue(output.is_dir())
            self.assertTrue(output.is_relative_to(captures.resolve()))
            self.assertIn("cap_11111111-1111-4111-8111-111111111111", output.name)
            self.assertIn("manifest_22222222-2222-4222-8222-222222222222", output.name)

    def test_tag_escape_and_ambiguous_parent_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            captures = Path(temp_dir) / "captures"
            for tag in ("..", "../escape", r"..\escape", "safe/escape", r"safe\escape", "two..dots"):
                with self.subTest(tag=tag), self.assertRaises(ValueError):
                    probe.create_capture_output_dir(
                        captures,
                        tag=tag,
                        stamp="20260711_120000",
                        capture_id="cap_id",
                        manifest_id="manifest_id",
                    )

    def test_output_directory_collision_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            captures = Path(temp_dir) / "captures"
            kwargs = {
                "tag": "collision",
                "stamp": "20260711_120000",
                "capture_id": "cap_id",
                "manifest_id": "manifest_id",
            }
            probe.create_capture_output_dir(captures, **kwargs)
            with self.assertRaises(FileExistsError):
                probe.create_capture_output_dir(captures, **kwargs)


class CliValidationTests(unittest.TestCase):
    def test_invalid_numeric_and_transport_arguments_fail_before_output_side_effects(self):
        cases = [
            ["--seconds", "0"],
            ["--seconds", "nan"],
            ["--seconds", "inf"],
            ["--sample-interval-s", "0"],
            ["--sample-interval-s", "nan"],
            ["--segment-s", "0"],
            ["--open-retry-delay-s", "0"],
            ["--open-retries", "-1"],
            ["--prewarm-iterations", "-1"],
            ["--rtsp-port", "0"],
            ["--rtsp-port", "65536"],
            ["--rtsp-transport", "udp"],
        ]
        for extra_args in cases:
            with self.subTest(args=extra_args), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                replay = root / "input.mkv"
                argv = ["rtsp_live_timeline_probe.py", "--source", str(replay), *extra_args]
                with (
                    patch.object(probe, "ROOT", root),
                    patch.object(probe, "port_open", side_effect=AssertionError("validation must precede network")),
                    patch.object(probe, "start_raw_recorder", side_effect=AssertionError("validation must precede ffmpeg")),
                    patch.object(probe, "analyze_live", side_effect=RuntimeError("must not analyze")),
                    patch.object(sys, "argv", argv),
                    self.assertRaises(SystemExit),
                ):
                    probe.main()
                self.assertFalse((root / "captures").exists())


class RtspEndpointTests(unittest.TestCase):
    def test_custom_rtsp_source_controls_connectivity_endpoint_and_is_redacted(self):
        observed_endpoints: list[tuple[str, int]] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            argv = [
                "rtsp_live_timeline_probe.py",
                "--source",
                "rtsp://user:secret@camera.example:9554/screen",
            ]

            def closed_port(host, port, timeout_s=1.0):
                observed_endpoints.append((host, port))
                return False

            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "port_open", side_effect=closed_port),
                patch.object(sys, "argv", argv),
                self.assertRaisesRegex(SystemExit, "2"),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            report_text = (out_dir / "live_timeline_report.json").read_text(encoding="utf-8")

        self.assertEqual([("camera.example", 9554)], observed_endpoints)
        self.assertNotIn("secret", report_text)
        self.assertIn("rtsp://***@camera.example:9554/screen", report_text)

    def test_custom_rtsp_source_without_port_uses_554(self):
        observed_endpoints: list[tuple[str, int]] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            argv = ["rtsp_live_timeline_probe.py", "--source", "rtsp://camera.example/screen"]

            def closed_port(host, port, timeout_s=1.0):
                observed_endpoints.append((host, port))
                return False

            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "port_open", side_effect=closed_port),
                patch.object(sys, "argv", argv),
                self.assertRaisesRegex(SystemExit, "2"),
            ):
                probe.main()

        self.assertEqual([("camera.example", 554)], observed_endpoints)


class RecorderCancellationTests(unittest.TestCase):
    class FakeLog:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class InterruptingProc:
        def __init__(self, exc):
            self.exc = exc
            self.wait_calls = 0
            self.terminate_calls = 0
            self.kill_calls = 0
            self._codex_log_handle = RecorderCancellationTests.FakeLog()

        def wait(self, timeout):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise self.exc
            return 0

        def terminate(self):
            self.terminate_calls += 1

        def kill(self):
            self.kill_calls += 1

    def test_keyboard_interrupt_terminates_recorder_closes_log_and_re_raises(self):
        proc = self.InterruptingProc(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            probe.close_raw_recorder(proc)
        self.assertEqual(1, proc.terminate_calls)
        self.assertGreaterEqual(proc.wait_calls, 2)
        self.assertTrue(proc._codex_log_handle.closed)

    def test_main_does_not_convert_keyboard_interrupt_to_capture_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            argv = ["rtsp_live_timeline_probe.py", "--source", "rtsp://camera.example/screen"]
            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "port_open", return_value=True),
                patch.object(probe, "start_raw_recorder", side_effect=KeyboardInterrupt()),
                patch.object(sys, "argv", argv),
                self.assertRaises(KeyboardInterrupt),
            ):
                probe.main()

    def test_cleanup_failure_does_not_replace_original_keyboard_interrupt(self):
        proc = self.InterruptingProc(KeyboardInterrupt())

        def fail_terminate():
            proc.terminate_calls += 1
            raise OSError("terminate failed")

        proc.terminate = fail_terminate
        with self.assertRaises(KeyboardInterrupt):
            probe.close_raw_recorder(proc)
        self.assertEqual(1, proc.terminate_calls)
        self.assertGreaterEqual(proc.wait_calls, 2)
        self.assertTrue(proc._codex_log_handle.closed)


class TrustedRecordingGateTests(unittest.TestCase):
    def test_non_finite_media_duration_is_invalid_json_safe_metadata(self):
        for duration in ("nan", "inf", "-inf"):
            with self.subTest(duration=duration):
                status = probe.recording_status(
                    0,
                    {"streams": [{"codec_type": "video"}], "format": {"duration": duration}},
                    10.0,
                )
                self.assertIsNone(status["duration_s"])
                self.assertFalse(status["duration_ok"])
                self.assertFalse(status["complete"])
                json.dumps(status, allow_nan=False)

    def test_invalid_media_never_reaches_timeline_analysis(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recorder_outputs: list[Path] = []
            argv = ["rtsp_live_timeline_probe.py", "--source", "rtsp://test.invalid/screen", "--seconds", "10"]

            def fake_start(ffmpeg, source, seconds, out_file, log_file):
                recorder_outputs.append(out_file)
                return object()

            def fake_close(proc, timeout_s=None):
                recorder_outputs[0].write_bytes(b"not a video")
                return 0

            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "port_open", return_value=True),
                patch.object(probe, "start_raw_recorder", side_effect=fake_start),
                patch.object(probe, "close_raw_recorder", side_effect=fake_close),
                patch.object(probe, "ffprobe", return_value={"streams": [], "format": {"duration": "10"}}),
                patch.object(probe, "analyze_live", side_effect=AssertionError("invalid raw must not be analyzed")),
                patch.object(sys, "argv", argv),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            report = json.loads((out_dir / "live_timeline_report.json").read_text(encoding="utf-8"))

        self.assertEqual("insufficient", report["trust_level"])
        self.assertFalse(report["recording_status"]["complete"])
        self.assertFalse(report["recording_status"]["has_video_stream"])
        self.assertEqual("invalid_or_incomplete_raw_recording", report["primary_error"])
        self.assertIn("observed_sha256", report["raw_recording"])

    def test_recorder_start_failure_is_structured_and_published(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            argv = ["rtsp_live_timeline_probe.py", "--source", "rtsp://user:secret@test.invalid/screen"]
            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "port_open", return_value=True),
                patch.object(probe, "start_raw_recorder", side_effect=OSError("ffmpeg missing")),
                patch.object(probe, "analyze_live", side_effect=AssertionError("must not analyze")),
                patch.object(sys, "argv", argv),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            report_text = (out_dir / "live_timeline_report.json").read_text(encoding="utf-8")
            report = json.loads(report_text)

        self.assertEqual("raw_recorder_start_failed", report["primary_error"])
        self.assertIn("ffmpeg missing", report["recorder_error"])
        self.assertNotIn("secret", report_text)
        self.assertEqual("insufficient", report["trust_level"])

    def test_no_raw_live_fast_path_is_explicitly_untrusted_and_redacted(self):
        analysis_calls: list[dict] = []

        def fake_analyze_live(**kwargs):
            analysis_calls.append(kwargs)
            return {
                "capture_id": kwargs["capture_id"],
                "source": kwargs["source"],
                "source_kind": "live_rtsp",
                "rtsp_url": kwargs["source"],
                "samples": [],
                "segments": [],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            argv = [
                "rtsp_live_timeline_probe.py",
                "--source",
                "rtsp://user:secret@test.invalid/screen",
                "--no-raw-record",
            ]
            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "port_open", return_value=True),
                patch.object(probe, "start_raw_recorder", side_effect=AssertionError("recorder must stay disabled")),
                patch.object(probe, "analyze_live", side_effect=fake_analyze_live),
                patch.object(sys, "argv", argv),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            published_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (
                    out_dir / "live_timeline_report.json",
                    out_dir / "capture_manifest.json",
                    out_dir / "live_timeline_report.md",
                )
            )
            report = json.loads((out_dir / "live_timeline_report.json").read_text(encoding="utf-8"))

        self.assertEqual(1, len(analysis_calls))
        self.assertTrue(analysis_calls[0]["source_is_live"])
        self.assertEqual("insufficient", report["trust_level"])
        self.assertFalse(report["production_usable"])
        self.assertEqual("live_untrusted_fast_path", report["processing_mode"])
        self.assertEqual("live_rtsp_untrusted", report["analysis_source_kind"])
        self.assertNotIn("sha256", report["raw_recording"])
        self.assertNotIn("secret", published_text)

    def test_local_replay_changed_during_analysis_is_not_content_hash_bound(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            replay = root / "replay.mkv"
            original = b"local replay"
            replay.write_bytes(original)

            def mutating_analyze_live(**kwargs):
                replay.write_bytes(b"LOCAL REPLAY")
                return {
                    "capture_id": kwargs["capture_id"],
                    "source": kwargs["source"],
                    "source_kind": "local_replay",
                    "rtsp_url": None,
                    "samples": [],
                    "segments": [],
                }

            argv = ["rtsp_live_timeline_probe.py", "--source", str(replay), "--tag", "mutated_replay"]
            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "analyze_live", side_effect=mutating_analyze_live),
                patch.object(sys, "argv", argv),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            report = json.loads((out_dir / "live_timeline_report.json").read_text(encoding="utf-8"))
            manifest = json.loads((out_dir / "capture_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual("insufficient", report["trust_level"])
        self.assertEqual("local_replay_changed_during_analysis", report["primary_error"])
        self.assertNotIn("sha256", report["raw_recording"])
        self.assertEqual(hashlib.sha256(original).hexdigest(), report["raw_recording"]["observed_sha256"])
        self.assertEqual("insufficient", manifest["trust_level"])


class ManifestCommitMarkerTests(unittest.TestCase):
    def test_manifest_is_written_last_and_binds_published_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            replay = root / "replay.mkv"
            replay.write_bytes(b"local replay")
            write_order: list[str] = []
            real_atomic_json = probe.atomic_write_json

            def fake_analyze_live(**kwargs):
                return {
                    "capture_id": kwargs["capture_id"],
                    "source": kwargs["source"],
                    "source_kind": "local_replay",
                    "rtsp_url": None,
                    "samples": [{"sample_index": 1}],
                    "segments": [],
                }

            def tracking_json(path, value):
                write_order.append(Path(path).name)
                return real_atomic_json(path, value)

            argv = ["rtsp_live_timeline_probe.py", "--source", str(replay), "--tag", "commit"]
            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "analyze_live", side_effect=fake_analyze_live),
                patch.object(probe, "ffprobe", return_value=valid_probe()),
                patch.object(probe, "atomic_write_json", side_effect=tracking_json),
                patch.object(sys, "argv", argv),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            manifest = json.loads((out_dir / "capture_manifest.json").read_text(encoding="utf-8"))

            self.assertEqual("capture_manifest.json", write_order[-1])
            for key in ("timeline_report", "samples", "markdown_report"):
                artifact = manifest["artifacts"][key]
                path = out_dir / artifact["file"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact["sha256"])
                self.assertEqual(path.stat().st_size, artifact["size_bytes"])

    def test_manifest_write_failure_leaves_published_artifacts_without_commit_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            replay = root / "replay.mkv"
            replay.write_bytes(b"local replay")
            real_atomic_json = probe.atomic_write_json

            def fake_analyze_live(**kwargs):
                return {
                    "capture_id": kwargs["capture_id"],
                    "source": kwargs["source"],
                    "source_kind": "local_replay",
                    "rtsp_url": None,
                    "samples": [],
                    "segments": [],
                }

            def fail_manifest(path, value):
                if Path(path).name == "capture_manifest.json":
                    raise OSError("manifest publish failed")
                return real_atomic_json(path, value)

            argv = ["rtsp_live_timeline_probe.py", "--source", str(replay), "--tag", "commit_failure"]
            with (
                patch.object(probe, "ROOT", root),
                patch.object(probe, "analyze_live", side_effect=fake_analyze_live),
                patch.object(probe, "ffprobe", return_value=valid_probe()),
                patch.object(probe, "atomic_write_json", side_effect=fail_manifest),
                patch.object(sys, "argv", argv),
                self.assertRaisesRegex(OSError, "manifest publish failed"),
            ):
                probe.main()

            out_dir = next((root / "captures").iterdir())
            self.assertTrue((out_dir / "live_timeline_report.json").is_file())
            self.assertTrue((out_dir / "samples.jsonl").is_file())
            self.assertTrue((out_dir / "live_timeline_report.md").is_file())
            self.assertFalse((out_dir / "capture_manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
