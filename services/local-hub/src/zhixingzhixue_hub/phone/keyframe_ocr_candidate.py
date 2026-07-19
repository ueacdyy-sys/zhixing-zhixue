"""将授权屏幕流的关键帧 OCR 降级为可追溯兴趣候选。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


MIN_OCR_CONFIDENCE = 0.6
MAX_OCR_EXCERPT_TERMS = 40
MAX_OCR_EXCERPT_CHARS = 480


def _usable_ocr_texts(ocr_items: Iterable[Mapping[str, Any]]) -> list[str]:
    texts: list[str] = []
    for item in ocr_items:
        text = str(item.get("text") or "").strip()
        confidence = item.get("confidence")
        if text and isinstance(confidence, (int, float)) and confidence >= MIN_OCR_CONFIDENCE:
            texts.append(text)
    return texts


def _bounded_excerpt(texts: Iterable[str]) -> str:
    """Keep a compact, readable trace instead of persisting duplicate OCR noise."""
    selected: list[str] = []
    seen: set[str] = set()
    used_chars = 0
    for text in texts:
        normalized = text.strip()
        if not normalized or normalized in seen:
            continue
        separator_chars = 3 if selected else 0
        if (
            len(selected) >= MAX_OCR_EXCERPT_TERMS
            or used_chars + separator_chars + len(normalized) > MAX_OCR_EXCERPT_CHARS
        ):
            break
        selected.append(normalized)
        seen.add(normalized)
        used_chars += separator_chars + len(normalized)
    return " | ".join(selected)


def build_keyframe_ocr_candidate(
    *,
    session_id: str,
    capture_id: str,
    frame_refs: Iterable[str],
    ocr_items: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a non-diagnostic candidate from user-authorized mobile screen frames.

    This function deliberately cannot emit an interest conclusion. Such a conclusion
    requires the slow path's complete continuous segment and synchronized audio.
    """
    evidence_refs = [ref for ref in frame_refs if isinstance(ref, str) and ref.strip()]
    texts = _usable_ocr_texts(ocr_items)
    base = {
        "session_id": session_id,
        "capture_id": capture_id,
        "source_mode": "MOBILE_SCREEN_KEYFRAME_OCR",
        "learning_diagnosis": None,
        "interest_conclusion": None,
        "requires_full_segment_and_audio": True,
    }
    if not evidence_refs or not texts:
        return {
            **base,
            "status": "NO_CANDIDATE",
            "evidence_refs": [],
            "ocr_excerpt": None,
        }
    return {
        **base,
        "status": "CANDIDATE_ONLY",
        "evidence_refs": evidence_refs,
        "ocr_excerpt": _bounded_excerpt(texts),
    }
