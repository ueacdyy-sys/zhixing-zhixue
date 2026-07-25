"""Build a mobile-consumable candidate card from sealed trimodal artifacts.

The card is an evidence envelope, not an interest prediction or a learning
diagnosis.  It preserves lane-specific excerpts and local references so a
student or later PC workbench can inspect what actually supported the prompt.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .contracts import FusedCandidate, FusionMode


class CandidateCardBuildError(ValueError):
    """Raised when a card would lose a sealed-media evidence boundary."""


_REQUIRED_LANES = frozenset({"ASR", "OCR", "VLM"})
_ARTIFACT_PREFIX = "local://artifact/"


def _artifact_path(uri: str, artifact_root: Path) -> Path:
    if not uri.startswith(_ARTIFACT_PREFIX):
        raise CandidateCardBuildError("artifact_uri_unsupported")
    relative = Path(uri[len(_ARTIFACT_PREFIX) :])
    if relative.name != str(relative) or relative.suffix.lower() != ".json":
        raise CandidateCardBuildError("artifact_uri_invalid")
    path = (artifact_root / relative).resolve()
    root = artifact_root.resolve()
    if root not in path.parents or not path.is_file():
        raise CandidateCardBuildError("artifact_missing_or_outside_root")
    return path


def _artifact_document(uri: str, artifact_root: Path, candidate: FusedCandidate) -> dict[str, Any]:
    try:
        payload = json.loads(_artifact_path(uri, artifact_root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CandidateCardBuildError("artifact_unreadable") from error
    if not isinstance(payload, dict):
        raise CandidateCardBuildError("artifact_document_invalid")
    if payload.get("classification") != "CANDIDATE_ONLY":
        raise CandidateCardBuildError("artifact_classification_invalid")
    if payload.get("window_id") != candidate.window_id:
        raise CandidateCardBuildError("artifact_window_mismatch")
    if payload.get("coverage_start_pts_ns") != candidate.start_pts_ns or payload.get("coverage_end_pts_ns") != candidate.end_pts_ns:
        raise CandidateCardBuildError("artifact_coverage_mismatch")
    if not isinstance(payload.get("lane"), str) or not isinstance(payload.get("result"), dict):
        raise CandidateCardBuildError("artifact_lane_or_result_invalid")
    return payload


def _text_values(value: object) -> list[str]:
    """Extract displayable raw text without treating it as a semantic conclusion."""

    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return [cleaned] if cleaned else []
    if isinstance(value, dict):
        return [text for item in value.values() for text in _text_values(item)]
    if isinstance(value, list):
        return [text for item in value for text in _text_values(item)]
    return []


def _lane_excerpt(lane: str, result: dict[str, Any]) -> str:
    if lane == "ASR":
        segments = result.get("segments")
        if isinstance(segments, list):
            return " ".join(
                text for item in segments if isinstance(item, dict)
                for text in _text_values(item.get("text"))
            )[:240]
    if lane == "OCR":
        return " ".join(_text_values(result.get("samples")))[:240]
    if lane == "VLM":
        return " ".join(_text_values(result.get("raw_model_text")))[:240]
    return ""


def build_candidate_card(candidate: FusedCandidate, *, artifact_root: Path) -> dict[str, object]:
    """Return a deterministic, versioned card only for complete trimodal evidence."""

    if candidate.fusion_mode is not FusionMode.TRIMODAL:
        raise CandidateCardBuildError("trimodal_candidate_required")
    documents: dict[str, tuple[str, dict[str, Any]]] = {}
    for uri in candidate.evidence_uris:
        document = _artifact_document(uri, artifact_root, candidate)
        lane = str(document["lane"])
        if lane in documents:
            raise CandidateCardBuildError("duplicate_lane_artifact")
        documents[lane] = (uri, document)
    if frozenset(documents) != _REQUIRED_LANES:
        raise CandidateCardBuildError("trimodal_artifact_required")

    facts: list[dict[str, str]] = []
    excerpts: dict[str, str] = {}
    for lane in ("ASR", "OCR", "VLM"):
        uri, document = documents[lane]
        excerpt = _lane_excerpt(lane, document["result"])
        excerpts[lane] = excerpt
        facts.append({"lane": lane, "evidence_uri": uri, "text": excerpt or "未提取到可展示文本"})
    display_excerpt = next((excerpts[lane] for lane in ("ASR", "OCR", "VLM") if excerpts[lane]), "已形成完整多模态候选证据。")
    card_id = "candidate_" + hashlib.sha256(candidate.window_id.encode("utf-8")).hexdigest()[:20]
    return {
        "schema_version": "candidate_card.v1",
        "card_id": card_id,
        "window_id": candidate.window_id,
        "visit_id": candidate.visit_id,
        "source_context": candidate.source_context.value,
        "classification": "CANDIDATE_ONLY",
        "media_range": {"start_pts_ns": candidate.start_pts_ns, "end_pts_ns": candidate.end_pts_ns},
        "facts": facts,
        "display_excerpt": display_excerpt,
        "student_action": "VIEW_EVIDENCE",
        "uncertainty": "该卡仅保留同源多模态候选证据，不构成兴趣、能力或专注结论。",
        "review_status": "auto",
    }
