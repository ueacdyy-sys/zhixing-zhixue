from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import full_video_runtime_check as runtime_check


class FullVideoRuntimeCheckTests(unittest.TestCase):
    def test_runtime_report_has_explicit_ready_or_not_ready_status(self):
        fake_torch = {
            "module": "torch",
            "present": False,
            "cuda_available": False,
            "device_count": 0,
            "devices": [],
        }
        fake_module = {"module": "x", "present": True, "version": "test"}
        fake_binary = {"binary": "ffmpeg", "available": True, "returncode": 0}
        fake_cache = {
            "model_id": "model",
            "cache_complete": False,
            "cache_directory_present": False,
            "snapshot_ids": [],
            "complete_snapshot_ids": [],
        }
        with (
            mock.patch.object(runtime_check, "_torch_report", return_value=fake_torch),
            mock.patch.object(runtime_check, "_module_report", return_value=fake_module),
            mock.patch.object(runtime_check, "_ffmpeg_report", return_value=fake_binary),
            mock.patch.object(runtime_check, "_model_cache_report", return_value=fake_cache),
        ):
            report = runtime_check.build_runtime_report()

        self.assertEqual("not_ready", report["status"])
        self.assertIn("torch_missing", report["blockers"])
        self.assertIn("vlm_model_cache_incomplete", report["blockers"])
        self.assertIn("asr_model_cache_incomplete", report["blockers"])


if __name__ == "__main__":
    unittest.main()
