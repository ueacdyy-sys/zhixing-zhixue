from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "audio_asr_probe.py"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audio_asr_probe as probe


class AudioAsrProbeBootstrapTests(unittest.TestCase):
    def test_probe_module_exists(self):
        self.assertTrue(MODULE.is_file(), f"missing probe module: {MODULE}")


class AudioMediaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = shutil.which("ffmpeg")
        cls.ffprobe = shutil.which("ffprobe")
        if not cls.ffmpeg or not cls.ffprobe:
            raise unittest.SkipTest("ffmpeg and ffprobe are required")
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp = Path(cls.temp_dir.name)
        cls.media = cls.temp / "opus_48k_stereo.mkv"
        completed = subprocess.run(
            [
                cls.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000:duration=1",
                "-ac",
                "2",
                "-c:a",
                "libopus",
                "-y",
                str(cls.media),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_ffprobe_reports_opus_48k_stereo_audio(self):
        result = probe.probe_audio_stream(self.media, ffprobe=self.ffprobe)

        self.assertEqual("opus", result["codec_name"])
        self.assertEqual(48000, result["sample_rate_hz"])
        self.assertEqual(2, result["channels"])
        self.assertEqual("stereo", result["channel_layout"])
        self.assertGreater(result["duration_s"], 0.9)

    def test_extract_wav_is_pcm_16k_mono(self):
        wav_path = self.temp / "extracted_16k_mono.wav"
        result = probe.extract_wav_16k_mono(
            self.media, wav_path, ffmpeg=self.ffmpeg
        )

        self.assertEqual(wav_path, result)
        with wave.open(str(wav_path), "rb") as wav_file:
            self.assertEqual(1, wav_file.getnchannels())
            self.assertEqual(16000, wav_file.getframerate())
            self.assertEqual(2, wav_file.getsampwidth())
            self.assertGreater(wav_file.getnframes(), 15000)


class AudioSignalStatisticsTests(unittest.TestCase):
    def write_pcm(self, path: Path, samples: list[int]) -> None:
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    def test_non_silence_statistics_reject_empty_audio_and_measure_signal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            mixed = temp / "mixed.wav"
            silent = temp / "silent.wav"
            self.write_pcm(mixed, [0] * 16000 + [10000] * 16000)
            self.write_pcm(silent, [0] * 32000)

            mixed_stats = probe.analyze_wav_signal(
                mixed, silence_threshold_dbfs=-40.0, frame_ms=100
            )
            silent_stats = probe.analyze_wav_signal(
                silent, silence_threshold_dbfs=-40.0, frame_ms=100
            )

        self.assertTrue(mixed_stats["has_non_silent_audio"])
        self.assertAlmostEqual(10000 / 32768, mixed_stats["peak_linear"], places=4)
        self.assertGreater(mixed_stats["rms_linear"], 0.2)
        self.assertAlmostEqual(0.5, mixed_stats["silence_ratio"], delta=0.05)
        self.assertFalse(silent_stats["has_non_silent_audio"])
        self.assertEqual(1.0, silent_stats["silence_ratio"])
        self.assertEqual(0.0, silent_stats["peak_linear"])


class AsrQualitySummaryTests(unittest.TestCase):
    def test_real_out_of_duration_segment_is_invalid_and_unassigned(self):
        raw = [
            {
                "segment_id": index,
                "start_s": float((index - 1) * 2),
                "end_s": float((index - 1) * 2 + 1),
                "text": f"第{index}段",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.1,
            }
            for index in range(1, 9)
        ]
        raw.append(
            {
                "segment_id": 9,
                "start_s": 24.54,
                "end_s": 26.72,
                "text": "越界段",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.1,
            }
        )
        timeline = {
            "capture_id": "capture-duration-audit",
            "segments": [
                {"segment_index": 1, "start_s": 0.0, "end_s": 20.0}
            ],
        }

        try:
            summary = probe.summarize_asr_quality(raw, audio_duration_s=20.0)
            max_end_summary = probe.summarize_asr_quality(raw, max_end_s=20.0)
            aligned = probe.align_asr_to_timeline(
                raw,
                timeline,
                model_id="model",
                source_media_sha256="a" * 64,
                audio_duration_s=20.0,
            )
        except TypeError as exc:
            self.fail(f"missing duration audit API: {exc}")

        for quality in (summary, max_end_summary):
            self.assertEqual(9, quality["segment_count"])
            self.assertEqual(8, quality["valid_quality_segment_count"])
            self.assertEqual([9], quality["invalid_quality_segment_ids"])
            self.assertIn("raw_segment_time_out_of_bounds", quality["quality_reasons"])
        self.assertEqual(
            {
                "raw_segment_count": 9,
                "assigned_raw_segment_count": 8,
                "unassigned_raw_segment_ids": [9],
            },
            aligned["alignment_summary"],
        )
        self.assertEqual(8, sum(
            result["quality_summary"]["segment_count"]
            for result in aligned["results"]
        ))
        self.assertEqual("fail", aligned["quality_status"])
        self.assertIn("raw_segments_unaligned_to_timeline", aligned["quality_reasons"])
        self.assertEqual("capture-duration-audit", aligned["capture_id"])
        self.assertEqual("a" * 64, aligned["results"][0]["source_media_sha256"])

    def test_quality_summary_rejects_wrong_types_and_out_of_range_metrics(self):
        raw = [
            None,
            {"segment_id": 1, "text": 123, "avg_logprob": -0.1, "no_speech_prob": 0.1},
            {"segment_id": 2, "text": "x", "avg_logprob": True, "no_speech_prob": 0.1},
            {"segment_id": 3, "text": "x", "avg_logprob": float("nan"), "no_speech_prob": 0.1},
            {"segment_id": 4, "text": "x", "avg_logprob": -0.1, "no_speech_prob": float("inf")},
            {"segment_id": 5, "text": "x", "avg_logprob": -0.1, "no_speech_prob": -0.1},
            {"segment_id": 6, "text": "x", "avg_logprob": -0.1, "no_speech_prob": 1.1},
            {"segment_id": 7, "text": "x", "avg_logprob": 0.1, "no_speech_prob": 0.1},
        ]

        try:
            summary = probe.summarize_asr_quality(raw)
        except Exception as exc:
            self.fail(f"invalid segments must be reported, not crash: {type(exc).__name__}: {exc}")

        self.assertEqual("fail", summary["quality_status"])
        self.assertEqual(0, summary["valid_quality_segment_count"])
        self.assertEqual([0, 1, 2, 3, 4, 5, 6, 7], summary["invalid_quality_segment_ids"])
        self.assertIn("missing_required_quality_fields", summary["quality_reasons"])
        json.dumps(summary, allow_nan=False)

    def test_quality_thresholds_reject_nonfinite_and_semantically_invalid_values(self):
        invalid_kwargs = [
            {"min_text_coverage_ratio": float("nan")},
            {"min_text_coverage_ratio": float("inf")},
            {"min_text_coverage_ratio": -0.1},
            {"min_text_coverage_ratio": 1.1},
            {"min_mean_avg_logprob": float("nan")},
            {"min_mean_avg_logprob": float("inf")},
            {"min_mean_avg_logprob": 0.1},
            {"max_no_speech_prob": float("nan")},
            {"max_no_speech_prob": float("inf")},
            {"max_no_speech_prob": -0.1},
            {"max_no_speech_prob": 1.1},
        ]

        for kwargs in invalid_kwargs:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    probe.summarize_asr_quality([], **kwargs)

    def test_quality_summary_names_emitted_ratio_and_disclaims_confidence(self):
        summary = probe.summarize_asr_quality(
            [
                {"segment_id": 1, "start_s": 0.0, "end_s": 0.5, "text": "有字", "avg_logprob": -0.3, "no_speech_prob": 0.1},
                {"segment_id": 2, "start_s": 0.5, "end_s": 1.0, "text": "", "avg_logprob": -0.3, "no_speech_prob": 0.1},
            ],
            min_text_coverage_ratio=0.0,
        )

        self.assertIn("nonempty_emitted_segment_ratio", summary)
        self.assertIn("metric_semantics", summary)
        self.assertEqual(0.5, summary["nonempty_emitted_segment_ratio"])
        self.assertEqual(
            summary["nonempty_emitted_segment_ratio"], summary["text_coverage_ratio"]
        )
        self.assertIn("unweighted", summary["metric_semantics"]["mean_avg_logprob"])
        self.assertIn("not_calibrated_confidence", summary["metric_semantics"]["mean_avg_logprob"])
        self.assertEqual(
            "deprecated_alias_of_nonempty_emitted_segment_ratio",
            summary["metric_semantics"]["text_coverage_ratio"],
        )

    def test_quality_summary_api_is_available_for_existing_raw_reports(self):
        self.assertTrue(
            callable(getattr(probe, "summarize_asr_quality", None)),
            "missing pure quality recomputation function",
        )

    def test_quality_summary_passes_only_when_all_conservative_gates_pass(self):
        raw = [
            {"segment_id": 1, "start_s": 0.0, "end_s": 0.5, "text": "第一句", "avg_logprob": -0.4, "no_speech_prob": 0.1},
            {"segment_id": 2, "start_s": 0.5, "end_s": 1.0, "text": "第二句", "avg_logprob": -0.6, "no_speech_prob": 0.2},
        ]

        summary = probe.summarize_asr_quality(
            raw,
            min_text_coverage_ratio=0.8,
            min_mean_avg_logprob=-1.0,
            max_no_speech_prob=0.6,
        )

        self.assertEqual("pass", summary["quality_status"])
        self.assertEqual([], summary["quality_reasons"])
        self.assertEqual(2, summary["segment_count"])
        self.assertEqual(2, summary["speech_segment_count"])
        self.assertEqual(2, summary["transcribed_segment_count"])
        self.assertAlmostEqual(-0.5, summary["mean_avg_logprob"])
        self.assertAlmostEqual(0.15, summary["mean_no_speech_prob"])
        self.assertAlmostEqual(0.2, summary["max_no_speech_prob"])
        self.assertAlmostEqual(1.0, summary["text_coverage_ratio"])
        self.assertEqual(
            {
                "min_text_coverage_ratio": 0.8,
                "min_mean_avg_logprob": -1.0,
                "max_no_speech_prob": 0.6,
            },
            summary["quality_thresholds"],
        )
        json.dumps(summary)

    def test_quality_summary_fails_when_a_segment_lacks_required_metrics(self):
        summary = probe.summarize_asr_quality(
            [{"segment_id": 9, "start_s": 0.0, "end_s": 0.5, "text": "有字", "avg_logprob": -0.2}],
        )

        self.assertEqual("fail", summary["quality_status"])
        self.assertIn("missing_required_quality_fields", summary["quality_reasons"])
        self.assertEqual([9], summary["invalid_quality_segment_ids"])

    def test_quality_summary_fails_without_a_valid_speech_segment(self):
        empty = probe.summarize_asr_quality([])
        high_no_speech = probe.summarize_asr_quality(
            [{"segment_id": 3, "start_s": 0.0, "end_s": 0.5, "text": "疑似幻觉", "avg_logprob": -0.2, "no_speech_prob": 0.9}]
        )

        self.assertIn("no_valid_speech_segments", empty["quality_reasons"])
        self.assertIn("no_valid_speech_segments", high_no_speech["quality_reasons"])
        self.assertIn("max_no_speech_prob_above_threshold", high_no_speech["quality_reasons"])

    def test_quality_summary_fails_when_text_coverage_is_too_low(self):
        summary = probe.summarize_asr_quality(
            [
                {"segment_id": 1, "start_s": 0.0, "end_s": 0.5, "text": "有字", "avg_logprob": -0.3, "no_speech_prob": 0.1},
                {"segment_id": 2, "start_s": 0.5, "end_s": 1.0, "text": "", "avg_logprob": -0.3, "no_speech_prob": 0.1},
            ],
            min_text_coverage_ratio=0.8,
        )

        self.assertEqual(0.5, summary["text_coverage_ratio"])
        self.assertIn("text_coverage_below_threshold", summary["quality_reasons"])

    def test_quality_summary_fails_when_mean_logprob_is_too_low(self):
        summary = probe.summarize_asr_quality(
            [{"segment_id": 1, "start_s": 0.0, "end_s": 0.5, "text": "低置信", "avg_logprob": -1.1, "no_speech_prob": 0.1}],
            min_mean_avg_logprob=-1.0,
        )

        self.assertIn("mean_avg_logprob_below_threshold", summary["quality_reasons"])

    def test_real_tiny_like_distribution_fails_provisional_default_logprob_gate(self):
        raw = [
            {
                "segment_id": index,
                "start_s": float(index),
                "end_s": float(index) + 0.5,
                "text": f"错词样本{index}",
                "avg_logprob": -0.83383,
                "no_speech_prob": 0.50377,
            }
            for index in range(26)
        ]

        summary = probe.summarize_asr_quality(raw)

        self.assertAlmostEqual(-0.83383, summary["mean_avg_logprob"], places=5)
        self.assertAlmostEqual(0.50377, summary["max_no_speech_prob"], places=5)
        self.assertEqual(-0.6, summary["quality_thresholds"]["min_mean_avg_logprob"])
        self.assertEqual("fail", summary["quality_status"])
        self.assertIn(
            "mean_avg_logprob_below_threshold", summary["quality_reasons"]
        )


class TimelineAlignmentTests(unittest.TestCase):
    def test_alignment_rejects_invalid_timeline_contract(self):
        invalid_timelines = [
            None,
            {},
            {"segments": []},
            {"segments": "not-a-list"},
            {"segments": [None]},
            {"segments": [{"segment_index": 2, "start_s": 0.0, "end_s": 1.0}]},
            {"segments": [{"segment_index": 1, "start_s": float("nan"), "end_s": 1.0}]},
            {"segments": [{"segment_index": 1, "start_s": -0.1, "end_s": 1.0}]},
            {"segments": [{"segment_index": 1, "start_s": 1.0, "end_s": 1.0}]},
            {
                "segments": [
                    {"segment_index": 1, "start_s": 0.0, "end_s": 2.0},
                    {"segment_index": 2, "start_s": 1.0, "end_s": 3.0},
                ]
            },
        ]

        for timeline in invalid_timelines:
            with self.subTest(timeline=timeline):
                try:
                    probe.align_asr_to_timeline(
                        [], timeline, model_id="model", source_media_sha256="d" * 64
                    )
                except Exception as exc:
                    self.assertIsInstance(exc, ValueError)
                else:
                    self.fail("invalid timeline was accepted")

    def test_cross_boundary_raw_segment_is_assigned_once_by_maximum_overlap(self):
        timeline = {
            "capture_id": "capture-bound",
            "segments": [
                {"segment_index": 1, "start_s": 0.0, "end_s": 2.0},
                {"segment_index": 2, "start_s": 2.0, "end_s": 4.0},
            ],
        }
        raw = [
            {
                "segment_id": 7,
                "start_s": 1.5,
                "end_s": 3.8,
                "text": "跨边界只出现一次",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.1,
                "evidence_refs": ["raw_asr_segment:7"],
            }
        ]

        aligned = probe.align_asr_to_timeline(
            raw, timeline, model_id="model", source_media_sha256="e" * 64
        )

        first, second = aligned["results"]
        self.assertEqual("", first["text"])
        self.assertNotIn("raw_asr_segment:7", first["evidence_refs"])
        self.assertEqual("跨边界只出现一次", second["text"])
        self.assertEqual(1, second["evidence_refs"].count("raw_asr_segment:7"))
        self.assertEqual("capture-bound", second["capture_id"])
        self.assertEqual("e" * 64, second["source_media_sha256"])

    def test_equal_overlap_tie_assigns_raw_segment_to_lower_segment_index(self):
        timeline = {
            "segments": [
                {"segment_index": 1, "start_s": 0.0, "end_s": 2.0},
                {"segment_index": 2, "start_s": 2.0, "end_s": 4.0},
            ]
        }
        raw = [
            {
                "segment_id": 8,
                "start_s": 1.0,
                "end_s": 3.0,
                "text": "平局归小序号",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.1,
            }
        ]

        aligned = probe.align_asr_to_timeline(
            raw, timeline, model_id="model", source_media_sha256="f" * 64
        )

        self.assertEqual("平局归小序号", aligned["results"][0]["text"])
        self.assertEqual("", aligned["results"][1]["text"])

    def test_alignment_top_level_fails_when_any_timeline_segment_fails_quality(self):
        timeline = {
            "segments": [
                {"segment_index": 1, "start_s": 0.0, "end_s": 1.0},
                {"segment_index": 2, "start_s": 1.0, "end_s": 2.0},
            ]
        }
        raw = [
            {
                "segment_id": 1,
                "start_s": 0.1,
                "end_s": 0.9,
                "text": "只有第一段",
                "avg_logprob": -0.3,
                "no_speech_prob": 0.1,
            }
        ]

        aligned = probe.align_asr_to_timeline(
            raw, timeline, model_id="model", source_media_sha256="d" * 64
        )

        self.assertEqual("pass", aligned["results"][0]["quality_status"])
        self.assertEqual("fail", aligned["results"][1]["quality_status"])
        self.assertEqual("fail", aligned["quality_status"])
        self.assertIn(
            "timeline_segment_quality_failed", aligned["quality_reasons"]
        )

    def test_timeline_segments_and_alignment_top_level_expose_quality(self):
        timeline = {
            "segments": [
                {
                    "segment_index": 1,
                    "start_s": 0.0,
                    "end_s": 2.0,
                    "evidence_files": ["frame.jpg"],
                }
            ]
        }
        raw = [
            {
                "segment_id": 7,
                "start_s": 0.1,
                "end_s": 1.9,
                "text": "证据",
                "avg_logprob": -0.4,
                "no_speech_prob": 0.1,
            }
        ]

        aligned = probe.align_asr_to_timeline(
            raw, timeline, model_id="model", source_media_sha256="d" * 64
        )

        self.assertEqual("pass", aligned["quality_status"])
        self.assertEqual([], aligned["quality_reasons"])
        self.assertEqual(1, aligned["quality_summary"]["segment_count"])
        self.assertEqual("pass", aligned["results"][0]["quality_status"])
        self.assertEqual([], aligned["results"][0]["quality_reasons"])
        self.assertEqual(1, aligned["results"][0]["quality_summary"]["segment_count"])

    def test_alignment_reuses_raw_asr_evidence_identity(self):
        timeline = {
            "segments": [
                {
                    "segment_index": 1,
                    "start_s": 0.0,
                    "end_s": 1.0,
                    "evidence_files": ["frame.jpg"],
                }
            ]
        }
        raw = [
            {
                "segment_id": 7,
                "start_s": 0.1,
                "end_s": 0.9,
                "text": "证据",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.1,
                "evidence_refs": ["raw_asr_segment:7"],
            }
        ]

        report = probe.align_asr_to_timeline(
            raw, timeline, model_id="model", source_media_sha256="d" * 64
        )

        refs = report["results"][0]["evidence_refs"]
        self.assertIn("raw_asr_segment:7", refs)
        self.assertNotIn("raw_asr_segment:0", refs)

    def test_asr_segments_align_to_timeline_with_complete_evidence_fields(self):
        timeline = {
            "segments": [
                {
                    "segment_index": 1,
                    "start_s": 0.0,
                    "end_s": 3.0,
                    "evidence_files": ["frame-1.jpg"],
                },
                {
                    "segment_index": 2,
                    "start_s": 3.0,
                    "end_s": 6.0,
                    "evidence_files": ["frame-2.jpg"],
                },
                {
                    "segment_index": 3,
                    "start_s": 6.0,
                    "end_s": 9.0,
                    "evidence_files": ["frame-3.jpg"],
                },
            ]
        }
        raw_asr = [
            {
                "start_s": 0.5,
                "end_s": 3.4,
                "text": "第一句",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.1,
            },
            {
                "start_s": 4.0,
                "end_s": 5.0,
                "text": "第二句",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.1,
            },
        ]

        report = probe.align_asr_to_timeline(
            raw_asr,
            timeline,
            model_id="Systran/faster-whisper-tiny",
            source_media_sha256="a" * 64,
        )

        self.assertEqual(
            "unbound_timeline_capture_id_missing", report["provenance_status"]
        )
        self.assertIsNone(report["capture_id"])
        self.assertEqual([1, 2, 3], [item["segment_index"] for item in report["results"]])

        first, second, third = report["results"]
        self.assertEqual("success", first["status"])
        self.assertEqual("第一句", first["text"])
        self.assertEqual((0.5, 3.0), (first["start_s"], first["end_s"]))
        self.assertEqual("success", second["status"])
        self.assertEqual("第二句", second["text"])
        self.assertEqual((4.0, 5.0), (second["start_s"], second["end_s"]))
        self.assertEqual("no_speech", third["status"])
        self.assertEqual("", third["text"])
        self.assertEqual((6.0, 9.0), (third["start_s"], third["end_s"]))

        required = {
            "status",
            "text",
            "start_s",
            "end_s",
            "model_id",
            "evidence_refs",
            "source_media_sha256",
        }
        for item in report["results"]:
            self.assertTrue(required.issubset(item))
            self.assertEqual("Systran/faster-whisper-tiny", item["model_id"])
            self.assertEqual("a" * 64, item["source_media_sha256"])
            self.assertTrue(item["evidence_refs"])
            self.assertIn(
                f"timeline_evidence:{item['segment_index']}:frame-{item['segment_index']}.jpg",
                item["evidence_refs"],
            )

    def test_capture_id_is_preserved_only_when_timeline_supplies_it(self):
        timeline = {
            "capture_id": "capture-real-001",
            "segments": [
                {
                    "segment_index": 1,
                    "start_s": 0.0,
                    "end_s": 1.0,
                    "evidence_files": ["frame.jpg"],
                }
            ],
        }

        report = probe.align_asr_to_timeline(
            [], timeline, model_id="model", source_media_sha256="b" * 64
        )

        self.assertEqual("bound_to_timeline_capture_id", report["provenance_status"])
        self.assertEqual("capture-real-001", report["capture_id"])
        self.assertEqual("capture-real-001", report["results"][0]["capture_id"])


class FasterWhisperContractTests(unittest.TestCase):
    def test_out_of_duration_raw_segment_keeps_checkpoint_and_returns_quality_block(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg and ffprobe are required")

        class OutOfDurationModel:
            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, wav_path, **kwargs):
                segments = [
                    SimpleNamespace(
                        id=index,
                        start=float((index - 1) * 2),
                        end=float((index - 1) * 2 + 1),
                        text=f"第{index}段",
                        avg_logprob=-0.2,
                        no_speech_prob=0.1,
                        compression_ratio=1.0,
                    )
                    for index in range(1, 9)
                ]
                segments.append(
                    SimpleNamespace(
                        id=9,
                        start=24.54,
                        end=26.72,
                        text="越界段",
                        avg_logprob=-0.2,
                        no_speech_prob=0.1,
                        compression_ratio=1.0,
                    )
                )
                return (
                    iter(segments),
                    SimpleNamespace(
                        language="zh", language_probability=0.9, duration=20.0
                    ),
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            media = temp / "source.mkv"
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=660:sample_rate=48000:duration=1",
                    "-ac",
                    "2",
                    "-c:a",
                    "libopus",
                    "-y",
                    str(media),
                ],
                check=True,
            )
            timeline_path = temp / "timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "capture_id": "capture-real-equivalent",
                        "segments": [
                            {"segment_index": 1, "start_s": 0.0, "end_s": 20.0}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            out_dir = temp / "output"

            report = probe.run_probe(
                media_path=media,
                timeline_path=timeline_path,
                out_dir=out_dir,
                model_id="tiny",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                model_factory=OutOfDurationModel,
            )

            self.assertEqual("success", report["asr"]["status"])
            self.assertEqual(20.0, report["asr"]["audio_duration_s"])
            self.assertEqual("fail", report["quality_status"])
            self.assertIn("raw_segment_time_out_of_bounds", report["quality_reasons"])
            self.assertIn("raw_segments_unaligned_to_timeline", report["quality_reasons"])
            self.assertEqual(9, report["quality_summary"]["segment_count"])
            self.assertEqual(8, report["quality_summary"]["valid_quality_segment_count"])
            self.assertEqual(8, report["alignment_summary"]["assigned_raw_segment_count"])
            self.assertEqual([9], report["alignment_summary"]["unassigned_raw_segment_ids"])
            self.assertTrue((out_dir / "raw_asr_report.json").is_file())
            self.assertFalse((out_dir / "audio_asr_failure.json").exists())
            with mock.patch.object(probe, "run_probe", return_value=report):
                exit_code = probe.main(
                    ["--media", str(media), "--timeline", str(timeline_path)]
                )
            self.assertEqual(3, exit_code)

    def test_checkpoint_serialization_failure_writes_standard_manifest(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg and ffprobe are required")

        class ValidModel:
            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, wav_path, **kwargs):
                return (
                    iter(
                        [
                            SimpleNamespace(
                                id=21,
                                start=0.1,
                                end=0.8,
                                text="有效文本",
                                avg_logprob=-0.2,
                                no_speech_prob=0.1,
                                compression_ratio=1.0,
                            )
                        ]
                    ),
                    SimpleNamespace(
                        language="zh", language_probability=0.9, duration=1.0
                    ),
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            media = temp / "source.mkv"
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=660:sample_rate=48000:duration=1",
                    "-ac",
                    "2",
                    "-c:a",
                    "libopus",
                    "-y",
                    str(media),
                ],
                check=True,
            )
            timeline_path = temp / "timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "capture_id": "capture-serialization",
                        "segments": [
                            {"segment_index": 1, "start_s": 0.0, "end_s": 1.0}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            out_dir = temp / "output"
            real_write_json = probe._write_json

            def fail_checkpoint(path, payload):
                if Path(path).name == "raw_asr_report.json":
                    raise TypeError("forced checkpoint serialization failure")
                return real_write_json(path, payload)

            with mock.patch.object(probe, "_write_json", side_effect=fail_checkpoint):
                with self.assertRaisesRegex(TypeError, "forced checkpoint"):
                    probe.run_probe(
                        media_path=media,
                        timeline_path=timeline_path,
                        out_dir=out_dir,
                        model_id="tiny",
                        ffmpeg=ffmpeg,
                        ffprobe=ffprobe,
                        model_factory=ValidModel,
                    )

            failure = json.loads(
                (out_dir / "audio_asr_failure.json").read_text(encoding="utf-8")
            )
            self.assertEqual("checkpoint_serialization", failure["stage"])
            self.assertEqual("checkpoint_payload", failure["field_name"])
            self.assertIsNone(failure["segment_id"])
            self.assertEqual("capture-serialization", failure["capture_id"])
            self.assertTrue(failure["audio_evidence_paths"])

    def test_nonfinite_asr_payload_writes_strict_checkpoint_validation_manifest(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg and ffprobe are required")

        invalid_cases = [
            ("avg_logprob", float("nan"), "avg_logprob", 11),
            ("no_speech_prob", float("inf"), "no_speech_prob", 11),
            ("compression_ratio", float("nan"), "compression_ratio", 11),
            ("language_probability", float("inf"), "language_probability", None),
            ("duration", float("nan"), "audio_duration_s", None),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            media = temp / "source.mkv"
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=660:sample_rate=48000:duration=1",
                    "-ac",
                    "2",
                    "-c:a",
                    "libopus",
                    "-y",
                    str(media),
                ],
                check=True,
            )
            timeline_path = temp / "timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "capture_id": "capture-nonfinite",
                        "segments": [
                            {"segment_index": 1, "start_s": 0.0, "end_s": 1.0}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            expected_sha256 = probe.sha256_file(media)

            for case_index, (source_field, value, field_name, segment_id) in enumerate(
                invalid_cases
            ):
                with self.subTest(field=source_field):
                    class NonFiniteModel:
                        def __init__(self, *args, **kwargs):
                            pass

                        def transcribe(self, wav_path, **kwargs):
                            segment_data = {
                                "id": 11,
                                "start": 0.1,
                                "end": 0.8,
                                "text": "有限文本",
                                "avg_logprob": -0.2,
                                "no_speech_prob": 0.1,
                                "compression_ratio": 1.0,
                            }
                            info_data = {
                                "language": "zh",
                                "language_probability": 0.9,
                                "duration": 1.0,
                            }
                            target = (
                                info_data
                                if source_field in {"language_probability", "duration"}
                                else segment_data
                            )
                            target[source_field] = value
                            return (
                                iter([SimpleNamespace(**segment_data)]),
                                SimpleNamespace(**info_data),
                            )

                    out_dir = temp / f"output-{case_index}"
                    with self.assertRaises(ValueError):
                        probe.run_probe(
                            media_path=media,
                            timeline_path=timeline_path,
                            out_dir=out_dir,
                            model_id="tiny",
                            ffmpeg=ffmpeg,
                            ffprobe=ffprobe,
                            model_factory=NonFiniteModel,
                        )

                    failure_path = out_dir / "audio_asr_failure.json"
                    self.assertTrue(failure_path.is_file())
                    self.assertFalse((out_dir / "raw_asr_report.json").exists())
                    serialized = failure_path.read_text(encoding="utf-8")
                    self.assertNotIn("NaN", serialized)
                    self.assertNotIn("Infinity", serialized)
                    failure = json.loads(serialized)
                    self.assertEqual("checkpoint_validation", failure["stage"])
                    self.assertEqual(field_name, failure["field_name"])
                    self.assertEqual(segment_id, failure["segment_id"])
                    self.assertEqual("capture-nonfinite", failure["capture_id"])
                    self.assertEqual(expected_sha256, failure["source_media_sha256"])
                    self.assertTrue(failure["audio_evidence_paths"])
                    for evidence_path in failure["audio_evidence_paths"]:
                        self.assertTrue(Path(evidence_path).is_file())

    def test_successful_asr_is_checkpointed_before_alignment_failure(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg and ffprobe are required")

        class InvalidTimingModel:
            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, wav_path, **kwargs):
                segment = SimpleNamespace(
                    id=1,
                    start=0.1,
                    end=0.5,
                    text="已完成ASR但无法对齐",
                    avg_logprob=-0.2,
                    no_speech_prob=0.1,
                    compression_ratio=1.0,
                )
                info = SimpleNamespace(
                    language="zh", language_probability=0.9, duration=1.0
                )
                return iter([segment]), info

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            media = temp / "source.mkv"
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=660:sample_rate=48000:duration=1",
                    "-ac",
                    "2",
                    "-c:a",
                    "libopus",
                    "-y",
                    str(media),
                ],
                check=True,
            )
            timeline_path = temp / "timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "segments": [
                            {"segment_index": 1, "start_s": 0.0, "end_s": 1.0}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            out_dir = temp / "output"

            with mock.patch.object(
                probe,
                "align_asr_to_timeline",
                side_effect=ValueError("forced alignment failure"),
            ):
                with self.assertRaisesRegex(ValueError, "forced alignment failure"):
                    probe.run_probe(
                        media_path=media,
                        timeline_path=timeline_path,
                        out_dir=out_dir,
                        model_id="tiny",
                        ffmpeg=ffmpeg,
                        ffprobe=ffprobe,
                        model_factory=InvalidTimingModel,
                    )

            checkpoint_path = out_dir / "raw_asr_report.json"
            failure_path = out_dir / "audio_asr_failure.json"
            self.assertTrue(checkpoint_path.is_file())
            self.assertTrue(failure_path.is_file())
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            self.assertEqual("success", checkpoint["asr"]["status"])
            self.assertEqual(1, len(checkpoint["raw_asr_segments"]))
            self.assertEqual("alignment", failure["failed_stage"])
            self.assertEqual("raw_asr_report.json", failure["checkpoint_file"])
            self.assertTrue(failure["retry_requires_new_out_dir"])
            self.assertFalse((out_dir / "audio_asr_report.json").exists())

    def test_cli_rejects_nonfinite_quality_threshold_before_running_pipeline(self):
        report = {
            "out_dir": "out",
            "audio_signal": {"has_non_silent_audio": True},
            "asr": {"status": "success", "language": "zh", "text": "文本"},
            "provenance_status": "bound_to_timeline_capture_id",
            "quality_status": "pass",
            "quality_reasons": [],
        }
        with mock.patch.object(probe, "run_probe", return_value=report) as run_probe:
            exit_code = probe.main(
                [
                    "--media",
                    "source.mkv",
                    "--timeline",
                    "timeline.json",
                    "--quality-min-mean-avg-logprob",
                    "nan",
                ]
            )

        self.assertEqual(2, exit_code)
        run_probe.assert_not_called()

    def test_write_json_is_atomic_and_rejects_nonstandard_nan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "report.json"
            target.write_text("old", encoding="utf-8")

            with self.assertRaises(ValueError):
                probe._write_json(target, {"bad": float("nan")})
            self.assertEqual("old", target.read_text(encoding="utf-8"))

            real_replace = probe.os.replace
            with mock.patch.object(probe.os, "replace", side_effect=real_replace) as replace:
                probe._write_json(target, {"status": "ok"})

            replace.assert_called_once()
            self.assertEqual({"status": "ok"}, json.loads(target.read_text(encoding="utf-8")))
            self.assertEqual([target], list(Path(temp_dir).iterdir()))

    def test_main_returns_three_when_pipeline_succeeds_but_quality_fails(self):
        report = {
            "out_dir": "out",
            "audio_signal": {"has_non_silent_audio": True},
            "asr": {"status": "success", "language": "zh", "text": "错词"},
            "provenance_status": "bound_to_timeline_capture_id",
            "quality_status": "fail",
            "quality_reasons": ["mean_avg_logprob_below_threshold"],
        }
        with mock.patch.object(probe, "run_probe", return_value=report):
            exit_code = probe.main(
                ["--media", "source.mkv", "--timeline", "timeline.json"]
            )

        self.assertEqual(3, exit_code)

    def test_cli_help_exposes_explicit_quality_thresholds(self):
        completed = subprocess.run(
            [sys.executable, str(MODULE), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("--quality-min-text-coverage-ratio", completed.stdout)
        self.assertIn("--quality-min-mean-avg-logprob", completed.stdout)
        self.assertIn("--quality-max-no-speech-prob", completed.stdout)
        self.assertIn("default: -0.6", completed.stdout)
        self.assertIn("exit 3", completed.stdout)

    def test_partial_huggingface_snapshot_is_not_reported_as_complete_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir) / "models--Systran--faster-whisper-tiny"
            snapshot = cache / "snapshots" / "partial"
            snapshot.mkdir(parents=True)
            (snapshot / "config.json").write_text("{}", encoding="utf-8")

            fact = probe._model_cache_fact(
                "Systran/faster-whisper-tiny", cache_path=cache
            )

            self.assertTrue(fact["cache_directory_present"])
            self.assertFalse(fact["cache_complete"])
            self.assertEqual([], fact["complete_snapshot_ids"])

    def test_transcription_records_raw_segments_language_runtime_and_model(self):
        calls = {}

        class FakeModel:
            def __init__(self, model_id, *, device, compute_type):
                calls["constructor"] = (model_id, device, compute_type)

            def transcribe(self, wav_path, **kwargs):
                calls["transcribe"] = (Path(wav_path), kwargs)
                segments = [
                    SimpleNamespace(
                        id=7,
                        start=0.25,
                        end=1.75,
                        text=" 真实文本 ",
                        avg_logprob=-0.4,
                        no_speech_prob=0.1,
                        compression_ratio=1.2,
                    )
                ]
                info = SimpleNamespace(
                    language="zh", language_probability=0.96, duration=2.0
                )
                return iter(segments), info

        clock_values = iter([10.0, 12.0])
        report = probe.transcribe_with_faster_whisper(
            Path("audio.wav"),
            model_id="tiny",
            source_media_sha256="c" * 64,
            device="cpu",
            compute_type="int8",
            model_factory=FakeModel,
            clock=lambda: next(clock_values),
        )

        self.assertEqual(("tiny", "cpu", "int8"), calls["constructor"])
        self.assertEqual("zh", report["language"])
        self.assertEqual(0.96, report["language_probability"])
        self.assertEqual(2.0, report["total_wall_s"])
        self.assertEqual(1.0, report["realtime_factor"])
        self.assertEqual("真实文本", report["text"])
        raw = report["raw_asr_segments"][0]
        self.assertEqual((0.25, 1.75), (raw["start_s"], raw["end_s"]))
        self.assertEqual("tiny", raw["model_id"])
        self.assertEqual("c" * 64, raw["source_media_sha256"])
        self.assertEqual(["raw_asr_segment:7"], raw["evidence_refs"])

    def test_pipeline_keeps_audio_evidence_when_model_loading_fails(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg and ffprobe are required")

        def failing_model(*args, **kwargs):
            raise OSError("model download unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            media = temp / "source.mkv"
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=660:sample_rate=48000:duration=1",
                    "-ac",
                    "2",
                    "-c:a",
                    "libopus",
                    "-y",
                    str(media),
                ],
                check=True,
            )
            timeline_path = temp / "timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "segment_index": 1,
                                "start_s": 0.0,
                                "end_s": 1.0,
                                "evidence_files": ["frame.jpg"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            out_dir = temp / "new-output"

            report = probe.run_probe(
                media_path=media,
                timeline_path=timeline_path,
                out_dir=out_dir,
                model_id="tiny",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                model_factory=failing_model,
            )

            self.assertTrue(report["audio_signal"]["has_non_silent_audio"])
            self.assertEqual("error", report["asr"]["status"])
            self.assertIn("model download unavailable", report["asr"]["error"])
            self.assertEqual("asr_error", report["results"][0]["status"])
            self.assertEqual(
                "unbound_timeline_capture_id_missing",
                report["provenance_status"],
            )
            self.assertEqual("fail", report["quality_status"])
            self.assertIn("no_valid_speech_segments", report["quality_reasons"])
            self.assertEqual(
                {
                    "min_text_coverage_ratio": 0.8,
                    "min_mean_avg_logprob": -0.6,
                    "max_no_speech_prob": 0.6,
                },
                report["quality_summary"]["quality_thresholds"],
            )
            self.assertIn(
                "provisional_conservative_threshold_needs_labeled_calibration",
                report["interpretation_note"],
            )
            self.assertTrue((out_dir / "audio_16k_mono.wav").is_file())
            self.assertTrue((out_dir / "audio_asr_report.json").is_file())
            self.assertTrue((out_dir / "asr_error.txt").is_file())

    def test_pipeline_refuses_to_overwrite_existing_output_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            existing = Path(temp_dir) / "existing"
            existing.mkdir()
            with self.assertRaises(FileExistsError):
                probe.run_probe(
                    media_path=Path("media.mkv"),
                    timeline_path=Path("timeline.json"),
                    out_dir=existing,
                    model_id="tiny",
                )


if __name__ == "__main__":
    unittest.main()
