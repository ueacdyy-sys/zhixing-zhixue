"""连续媒体语义分析的保守准入门。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any


def _has_local_uri(segment: Mapping[str, Any], field: str) -> bool:
    value = segment.get(field)
    return isinstance(value, str) and value.startswith("local://")


def _has_timezone_timestamp(segment: Mapping[str, Any], field: str) -> bool:
    value = segment.get(field)
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def admit_full_segment(segment: Mapping[str, Any]) -> dict[str, Any]:
    """Admit only complete, replayable and time-bound phone media to slow analysis."""
    reasons: list[str] = []
    capture_id = segment.get("capture_id")
    if not isinstance(capture_id, str) or not capture_id.strip():
        reasons.append("capture_id_required")
    if not _has_local_uri(segment, "media_uri"):
        reasons.append("continuous_media_required")
    if not _has_local_uri(segment, "audio_uri"):
        reasons.append("same_source_audio_required")
    if not _has_timezone_timestamp(segment, "start_ts") or not _has_timezone_timestamp(
        segment, "end_ts"
    ):
        reasons.append("time_range_required")

    if reasons:
        return {
            "status": "BLOCKED_INSUFFICIENT_EVIDENCE",
            "capture_id": capture_id,
            "reasons": reasons,
            "interest_conclusion": None,
        }
    return {
        "status": "ADMITTED_FOR_SEMANTIC_ANALYSIS",
        "capture_id": capture_id,
        "reasons": [],
        "interest_conclusion": None,
    }
