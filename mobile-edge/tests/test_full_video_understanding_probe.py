from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import full_video_understanding_probe as probe


CAPTURE_ID = "cap_full_video_contract_001"


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class FullVideoUnderstandingProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_dir.name)
        self.video = self.temp / "raw_rtsp_copy.mkv"
        self.video.write_bytes(b"canonical full video placeholder")
        self.media_sha = sha256_file(self.video)
        self.timeline_path = self.temp / "live_timeline_report.json"
        self.manifest_path = self.temp / "capture_manifest.json"
        self.asr_path = self.temp / "audio_asr_report.json"
        self.vlm_json_path = self.temp / "vlm_model_output.json"
        self.ffprobe_payload = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "duration": "1.0"},
                {"codec_type": "audio", "codec_name": "opus", "duration": "1.0"},
            ],
            "format": {"duration": "1.0"},
        }
        write_json(
            self.timeline_path,
            {
                "capture_id": CAPTURE_ID,
                "source_kind": "live_rtsp",
                "source": "rtsp://127.0.0.1:8554/screen",
                "rtsp_url": "rtsp://127.0.0.1:8554/screen",
                "raw_recording": {
                    "file": str(self.video),
                    "canonical_file": str(self.video),
                    "sha256": self.media_sha,
                    "size_bytes": self.video.stat().st_size,
                },
                "segments": [
                    {"segment_index": 1, "start_s": 0.0, "end_s": 1.0},
                ],
            },
        )
        write_json(
            self.manifest_path,
            {
                "capture_id": CAPTURE_ID,
                "source_kind": "live_rtsp",
                "raw_recording": {
                    "canonical_file": str(self.video),
                    "sha256": self.media_sha,
                    "size_bytes": self.video.stat().st_size,
                },
            },
        )
        write_json(
            self.asr_path,
            {
                "capture_id": CAPTURE_ID,
                "source_media_sha256": self.media_sha,
                "quality_status": "pass",
                "results": [
                    {
                        "status": "success",
                        "segment_index": 1,
                        "start_s": 0.0,
                        "end_s": 1.0,
                        "text": "这里讲到了海浪和月光的意象。",
                        "evidence_refs": ["asr:segment-1"],
                    }
                ],
            },
        )
        write_json(
            self.vlm_json_path,
            {
                "events": [
                    {
                        "segment_index": 1,
                        "start_s": 0.0,
                        "end_s": 1.0,
                        "summary": "视频片段出现海面与月光相关表达。",
                        "concepts": ["意象", "月光"],
                        "expressions": ["海浪"],
                        "uncertainty": "medium",
                        "evidence_refs": ["video:0.00-1.00"],
                    }
                ],
                "global_concepts": ["意象"],
            },
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rejects_image_or_frame_input_as_semantic_main_input(self):
        image = self.temp / "frame.jpg"
        image.write_bytes(b"fake image")

        with self.assertRaises(probe.FullVideoInputError) as raised:
            probe.validate_full_video_path(image)

        self.assertEqual("sampled_frame_input_forbidden", raised.exception.code)

    def test_builds_bound_full_video_report_from_external_model_json_contract(self):
        report = probe.build_understanding_report(
            video_path=self.video,
            timeline_path=self.timeline_path,
            manifest_path=self.manifest_path,
            asr_report_path=self.asr_path,
            ffprobe_payload=self.ffprobe_payload,
            model_output_json=self.vlm_json_path,
        )

        self.assertTrue(report["production_ready"])
        self.assertEqual("canonical_full_video", report["input_mode"])
        self.assertEqual(self.media_sha, report["source_media_sha256"])
        self.assertEqual(CAPTURE_ID, report["capture_id"])
        self.assertEqual(1, len(report["results"]))
        self.assertIn("model_internal_video_sampling_fps", report["processing_disclosure"])

    def test_rejects_positive_path_when_asr_quality_does_not_pass(self):
        asr = json.loads(self.asr_path.read_text(encoding="utf-8"))
        asr["quality_status"] = "fail"
        write_json(self.asr_path, asr)

        with self.assertRaises(probe.FullVideoInputError) as raised:
            probe.build_understanding_report(
                video_path=self.video,
                timeline_path=self.timeline_path,
                manifest_path=self.manifest_path,
                asr_report_path=self.asr_path,
                ffprobe_payload=self.ffprobe_payload,
                model_output_json=self.vlm_json_path,
            )

        self.assertEqual("asr_quality_not_pass", raised.exception.code)

    def test_rejects_media_without_audio_track(self):
        payload = {
            "streams": [{"codec_type": "video", "codec_name": "h264", "duration": "1.0"}],
            "format": {"duration": "1.0"},
        }

        with self.assertRaises(probe.FullVideoInputError) as raised:
            probe.summarize_media(self.video, ffprobe_payload=payload)

        self.assertEqual("audio_track_missing", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
