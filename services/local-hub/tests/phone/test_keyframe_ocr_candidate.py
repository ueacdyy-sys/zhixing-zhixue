from zhixingzhixue_hub.phone.keyframe_ocr_candidate import build_keyframe_ocr_candidate


def test_keyframe_ocr_emits_candidate_with_traceable_screen_evidence_only() -> None:
    result = build_keyframe_ocr_candidate(
        session_id="mobile-session-001",
        capture_id="mobile-capture-001",
        frame_refs=["capture://mobile-capture-001/keyframes/0001.jpg"],
        ocr_items=[{"text": "BBOX 标注", "confidence": 0.94}],
    )

    assert result["status"] == "CANDIDATE_ONLY"
    assert result["source_mode"] == "MOBILE_SCREEN_KEYFRAME_OCR"
    assert result["evidence_refs"] == ["capture://mobile-capture-001/keyframes/0001.jpg"]
    assert result["ocr_excerpt"] == "BBOX 标注"
    assert result["learning_diagnosis"] is None
    assert result["interest_conclusion"] is None
    assert result["requires_full_segment_and_audio"] is True


def test_keyframe_ocr_without_usable_text_is_not_a_candidate() -> None:
    result = build_keyframe_ocr_candidate(
        session_id="mobile-session-001",
        capture_id="mobile-capture-001",
        frame_refs=["capture://mobile-capture-001/keyframes/0001.jpg"],
        ocr_items=[{"text": "  ", "confidence": 0.99}, {"text": "噪声", "confidence": 0.31}],
    )

    assert result["status"] == "NO_CANDIDATE"
    assert result["evidence_refs"] == []
    assert result["learning_diagnosis"] is None
    assert result["interest_conclusion"] is None


def test_keyframe_ocr_bounds_duplicate_ocr_noise() -> None:
    result = build_keyframe_ocr_candidate(
        session_id="mobile-session-001",
        capture_id="mobile-capture-001",
        frame_refs=["capture://mobile-capture-001/keyframes/0001.jpg"],
        ocr_items=[{"text": "重复文本", "confidence": 0.9}] * 100
        + [{"text": "x" * 500, "confidence": 0.9}],
    )

    assert result["ocr_excerpt"] == "重复文本"
