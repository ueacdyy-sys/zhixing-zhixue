from __future__ import annotations

import hashlib
import json

from zhixingzhixue_hub.adapters.live_rtsp_capture import register_live_rtsp_capture


def test_live_rtsp_capture_with_ocr_and_no_audio_stays_candidate_only(tmp_path) -> None:
    media = tmp_path / "raw_rtsp_copy.mkv"
    media.write_bytes(b"authorized-live-video")
    digest = hashlib.sha256(media.read_bytes()).hexdigest()
    (tmp_path / "content_understanding").mkdir()
    (tmp_path / "capture_manifest.json").write_text(
        json.dumps(
            {
                "capture_id": "cap-live-001",
                "source_kind": "live_rtsp",
                "raw_recording": {"canonical_file": str(media), "sha256": digest},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "live_timeline_report.json").write_text(
        json.dumps(
            {
                "capture_id": "cap-live-001",
                "source_kind": "live_rtsp",
                "raw_recording": {"ffprobe": {"streams": [{"codec_type": "video"}]}},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "content_understanding" / "understanding_report.json").write_text(
        json.dumps(
            {
                "frames": [
                    {
                        "file": str(tmp_path / "evidence_frames" / "sample_0001.jpg"),
                        "regions": [{"text": ["真实文本"], "confidences": [0.91]}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = register_live_rtsp_capture(
        capture_dir=tmp_path,
        session_id="ses-live-001",
        recorded_at="2026-07-18T14:20:00+08:00",
    )

    assert result["candidate"]["status"] == "CANDIDATE_ONLY"
    assert result["candidate"]["interest_conclusion"] is None
    assert result["media"]["same_source_audio"] is False
    assert result["semantic_gate"]["status"] == "BLOCKED"
    assert result["semantic_gate"]["blocked_stages"] == ["ASR", "VLM"]
