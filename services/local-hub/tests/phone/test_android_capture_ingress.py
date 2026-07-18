import pytest

from zhixingzhixue_hub.adapters.android_capture_ingress import (
    AndroidCaptureIngressError,
    register_authorized_capture,
)


def test_authorized_real_media_and_audio_files_become_replayable_phone_capture(tmp_path) -> None:
    media = tmp_path / "segment.mkv"
    audio = tmp_path / "audio.m4a"
    media.write_bytes(b"captured-video-bytes")
    audio.write_bytes(b"captured-audio-bytes")

    capture = register_authorized_capture(
        capture_root=tmp_path,
        session_id="ses-live-phone-001",
        capture_id="cap-live-phone-001",
        media_path=media,
        audio_path=audio,
        start_ts="2026-07-17T22:30:00+08:00",
        end_ts="2026-07-17T22:31:00+08:00",
        consent_granted=True,
    )

    assert capture["media_uri"] == "local://captures/cap-live-phone-001/segment.mkv"
    assert capture["audio_uri"] == "local://captures/cap-live-phone-001/audio.m4a"
    assert len(capture["media_sha256"]) == 64
    assert len(capture["audio_sha256"]) == 64
    assert capture["source"] == "phone"


def test_capture_ingress_rejects_missing_audio_or_missing_explicit_consent(tmp_path) -> None:
    media = tmp_path / "segment.mkv"
    media.write_bytes(b"captured-video-bytes")

    with pytest.raises(AndroidCaptureIngressError, match="explicit_consent_required"):
        register_authorized_capture(
            capture_root=tmp_path,
            session_id="ses-live-phone-001",
            capture_id="cap-live-phone-001",
            media_path=media,
            audio_path=tmp_path / "audio.m4a",
            start_ts="2026-07-17T22:30:00+08:00",
            end_ts="2026-07-17T22:31:00+08:00",
            consent_granted=False,
        )

    with pytest.raises(AndroidCaptureIngressError, match="audio_file_required"):
        register_authorized_capture(
            capture_root=tmp_path,
            session_id="ses-live-phone-001",
            capture_id="cap-live-phone-001",
            media_path=media,
            audio_path=tmp_path / "audio.m4a",
            start_ts="2026-07-17T22:30:00+08:00",
            end_ts="2026-07-17T22:31:00+08:00",
            consent_granted=True,
        )
