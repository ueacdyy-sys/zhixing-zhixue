"""手机公开内容会话的应用用例。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from zhixingzhixue_hub.analysis.slow_path import admit_full_segment


def start_interest_session(media: Mapping[str, Any]) -> dict[str, Any]:
    """Submit a phone media session to the conservative semantic-analysis gate."""
    admission = admit_full_segment(media)
    if admission["status"] != "ADMITTED_FOR_SEMANTIC_ANALYSIS":
        return {
            "status": "CANDIDATE_ONLY",
            "entry_type": "PUBLIC_MEDIA",
            "capture_id": admission["capture_id"],
            "reasons": admission["reasons"],
            "interest_conclusion": None,
        }
    return {
        "status": "SEMANTIC_ANALYSIS_PENDING",
        "entry_type": "PUBLIC_MEDIA",
        "capture_id": admission["capture_id"],
        "reasons": [],
        "interest_conclusion": None,
    }
