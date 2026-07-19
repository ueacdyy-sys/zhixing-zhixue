"""Register a completed authorized RTSP capture as conservative local evidence."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from zhixingzhixue_hub.phone.keyframe_ocr_candidate import build_keyframe_ocr_candidate
from zhixingzhixue_hub.quality.modality_gate import assess_modality_quality, create_downgrade_log


class LiveRtspCaptureIngressError(ValueError):
    """Raised when a capture bundle cannot be bound to replayable local evidence."""


def _read_object(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LiveRtspCaptureIngressError(f"{name}_read_failed") from error
    if not isinstance(value, dict):
        raise LiveRtspCaptureIngressError(f"{name}_object_required")
    return value


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveRtspCaptureIngressError(f"{field}_required")
    return value.strip()


def _same_source_audio_present(timeline: dict[str, Any]) -> bool:
    raw = timeline.get("raw_recording")
    ffprobe = raw.get("ffprobe") if isinstance(raw, dict) else None
    streams = ffprobe.get("streams") if isinstance(ffprobe, dict) else None
    return isinstance(streams, list) and any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in streams
    )


def _ocr_items(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    frame_refs: list[str] = []
    capture_id = _required_text(report.get("capture_id"), "capture_id")
    for frame in report.get("frames", []):
        if not isinstance(frame, dict):
            continue
        frame_file = frame.get("file")
        if isinstance(frame_file, str) and frame_file.strip():
            frame_refs.append(f"local://captures/{capture_id}/evidence_frames/{Path(frame_file).name}")
        for region in frame.get("regions", []):
            if not isinstance(region, dict):
                continue
            texts = region.get("text")
            confidences = region.get("confidences")
            if not isinstance(texts, list) or not isinstance(confidences, list):
                continue
            for text, confidence in zip(texts, confidences, strict=False):
                items.append({"text": text, "confidence": confidence})
    return items, list(dict.fromkeys(frame_refs))


def register_live_rtsp_capture(
    *,
    capture_dir: Path,
    session_id: str,
    recorded_at: str,
) -> dict[str, Any]:
    """Bind recorded RTSP video, keyframe OCR and quality state without semantic overclaiming."""
    try:
        parsed_recorded_at = datetime.fromisoformat(recorded_at)
    except ValueError as error:
        raise LiveRtspCaptureIngressError("recorded_at_must_be_iso8601") from error
    if parsed_recorded_at.tzinfo is None:
        raise LiveRtspCaptureIngressError("recorded_at_must_include_timezone")

    root = capture_dir.resolve()
    manifest = _read_object(root / "capture_manifest.json", "manifest")
    timeline = _read_object(root / "live_timeline_report.json", "timeline")
    ocr = _read_object(root / "content_understanding" / "understanding_report.json", "ocr")
    capture_id = _required_text(manifest.get("capture_id"), "capture_id")
    if timeline.get("capture_id") != capture_id or ocr.get("capture_id") not in (None, capture_id):
        raise LiveRtspCaptureIngressError("capture_id_mismatch")
    if manifest.get("source_kind") != "live_rtsp" or timeline.get("source_kind") != "live_rtsp":
        raise LiveRtspCaptureIngressError("live_rtsp_source_required")

    raw = manifest.get("raw_recording")
    if not isinstance(raw, dict):
        raise LiveRtspCaptureIngressError("raw_recording_required")
    raw_file = Path(_required_text(raw.get("canonical_file"), "canonical_file")).resolve()
    try:
        raw_file.relative_to(root)
    except ValueError as error:
        raise LiveRtspCaptureIngressError("canonical_file_must_stay_within_capture_dir") from error
    if not raw_file.is_file() or raw_file.stat().st_size <= 0:
        raise LiveRtspCaptureIngressError("canonical_media_required")
    media_sha256 = _sha256(raw_file)
    if raw.get("sha256") != media_sha256:
        raise LiveRtspCaptureIngressError("canonical_media_sha256_mismatch")

    ocr_items, frame_refs = _ocr_items({**ocr, "capture_id": capture_id})
    candidate = build_keyframe_ocr_candidate(
        session_id=session_id,
        capture_id=capture_id,
        frame_refs=frame_refs,
        ocr_items=ocr_items,
    )
    media_uri = f"local://captures/{capture_id}/{raw_file.name}"
    visual_gate = assess_modality_quality(
        {
            "session_id": session_id,
            "capture_id": capture_id,
            "source": "phone",
            "modality": "screen_video",
            "connection_status": "connected",
            "quality": "usable",
            "quality_flags": [],
            "evidence_uri": media_uri,
            "alignment_residual_ms": 0.0,
        }
    )
    same_source_audio = _same_source_audio_present(timeline)
    semantic_gate = {
        "status": "PENDING" if same_source_audio else "BLOCKED",
        "allowed_result": "CANDIDATE_ONLY",
        "blocked_stages": [] if same_source_audio else ["ASR", "VLM"],
        "reasons": [] if same_source_audio else ["same_source_audio_missing", "asr_not_started"],
    }
    return {
        "schema_version": "1.0",
        "session_id": session_id,
        "capture_id": capture_id,
        "source_kind": "live_rtsp",
        "media": {"uri": media_uri, "sha256": media_sha256, "same_source_audio": same_source_audio},
        "candidate": candidate,
        "visual_quality": create_downgrade_log(visual_gate, recorded_at=recorded_at),
        "semantic_gate": semantic_gate,
    }
