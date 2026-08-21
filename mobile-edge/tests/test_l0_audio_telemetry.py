from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.contracts import ContractError  # noqa: E402
from realtime_runtime.l0_audio_telemetry import load_fragment_audio_telemetry  # noqa: E402


def _record(*, snapshot_id: str, session_id: str, generation: int, start_us: int, end_us: int) -> dict[str, object]:
    payload = {
        "snapshot_id": snapshot_id,
        "capture_generation": generation,
        "capture_path": "PLAYBACK",
        "status": "CAPTURE_ACTIVE_UNVERIFIED",
        "application_package_id": "tv.danmaku.bili",
        "restriction": "NONE",
        "failure_code": None,
        "video_pts_start_us": start_us,
        "video_pts_end_us": end_us,
        "audio_pts_start_us": start_us,
        "audio_pts_end_us": end_us,
        "session_epoch_id": "rtsp-11",
        "clock_domain": "ANDROID_ELAPSED_REALTIME_MONOTONIC",
        "anchor_elapsed_realtime_ns": 100,
        "sync_error_us": None,
        "recovery_attempt": 0,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return {
        "event_type": "CaptureAudioCapabilityObservedL0",
        "capture_session_id": session_id,
        "payload": payload,
        "payload_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def test_loads_only_authenticated_l0_audio_telemetry_for_matching_session_generation_and_pts() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        journal = Path(temp_dir) / "capture.audio-l0.jsonl"
        records = (
            _record(snapshot_id="overlap", session_id="capture-1", generation=7, start_us=1_500_000, end_us=2_500_000),
            _record(snapshot_id="wrong-generation", session_id="capture-1", generation=6, start_us=1_500_000, end_us=2_500_000),
            _record(snapshot_id="wrong-session", session_id="capture-2", generation=7, start_us=1_500_000, end_us=2_500_000),
            _record(snapshot_id="outside-range", session_id="capture-1", generation=7, start_us=3_000_000, end_us=4_000_000),
        )
        journal.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")

        references = load_fragment_audio_telemetry(
            journal,
            capture_session_id="capture-1",
            capture_generation=7,
            start_pts_ns=1_000_000_000,
            end_pts_ns=2_000_000_000,
        )

    assert [item.snapshot_id for item in references] == ["overlap"]
    assert references[0].session_epoch_id == "rtsp-11"
    assert references[0].video_pts_start_ns == 1_500_000_000


def test_rejects_a_tampered_l0_audio_telemetry_journal() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        journal = Path(temp_dir) / "capture.audio-l0.jsonl"
        record = _record(snapshot_id="tampered", session_id="capture-1", generation=7, start_us=1, end_us=2)
        record["payload_sha256"] = "0" * 64
        journal.write_text(json.dumps(record) + "\n", encoding="utf-8")

        with pytest.raises(ContractError, match="l0_audio_telemetry_hash_mismatch"):
            load_fragment_audio_telemetry(
                journal,
                capture_session_id="capture-1",
                capture_generation=7,
                start_pts_ns=0,
                end_pts_ns=3_000,
            )
