from zhixingzhixue_hub.phone.interest_session import start_interest_session


def full_phone_media() -> dict[str, object]:
    return {
        "capture_id": "cap-phone-001",
        "session_id": "ses-phone-001",
        "media_uri": "local://captures/cap-phone-001/video.mkv",
        "audio_uri": "local://captures/cap-phone-001/audio.m4a",
        "start_ts": "2026-07-17T17:00:00+08:00",
        "end_ts": "2026-07-17T17:00:30+08:00",
        "source": "phone",
    }


def test_phone_public_media_session_enqueues_semantic_analysis_without_interest_conclusion() -> None:
    session = start_interest_session(full_phone_media())

    assert session["status"] == "SEMANTIC_ANALYSIS_PENDING"
    assert session["entry_type"] == "PUBLIC_MEDIA"
    assert session["capture_id"] == "cap-phone-001"
    assert session["interest_conclusion"] is None


def test_phone_media_session_with_incomplete_evidence_stays_candidate_only() -> None:
    media = full_phone_media()
    media.pop("audio_uri")

    session = start_interest_session(media)

    assert session["status"] == "CANDIDATE_ONLY"
    assert session["reasons"] == ["same_source_audio_required"]
    assert session["interest_conclusion"] is None
