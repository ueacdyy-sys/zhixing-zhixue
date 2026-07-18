from zhixingzhixue_hub.analysis.slow_path import admit_full_segment


def complete_segment() -> dict[str, object]:
    return {
        "capture_id": "cap-phone-001",
        "session_id": "ses-phone-001",
        "media_uri": "local://captures/cap-phone-001/video.mkv",
        "audio_uri": "local://captures/cap-phone-001/audio.m4a",
        "start_ts": "2026-07-17T17:00:00+08:00",
        "end_ts": "2026-07-17T17:00:30+08:00",
        "source": "phone",
    }


def test_complete_continuous_media_with_same_source_audio_is_admitted_for_semantic_analysis() -> None:
    admission = admit_full_segment(complete_segment())

    assert admission["status"] == "ADMITTED_FOR_SEMANTIC_ANALYSIS"
    assert admission["capture_id"] == "cap-phone-001"
    assert admission["interest_conclusion"] is None


def test_segment_without_same_source_audio_is_blocked_from_interest_conclusion() -> None:
    segment = complete_segment()
    segment.pop("audio_uri")

    admission = admit_full_segment(segment)

    assert admission["status"] == "BLOCKED_INSUFFICIENT_EVIDENCE"
    assert admission["reasons"] == ["same_source_audio_required"]
    assert admission["interest_conclusion"] is None
