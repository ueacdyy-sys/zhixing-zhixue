"""Validated adapter from the RTSP worker's JSONL event to inner contracts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .contracts import AudioStatus, ContractError, SealedFragment, SourceContext


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sealed_fragment_from_worker_event(
    event: dict[str, Any],
    *,
    source_context: SourceContext,
    media_root: Path,
) -> SealedFragment:
    """Validate an outer JSON event before it can enter the evidence ledger."""

    if event.get("event_type") != "FragmentCommitted":
        raise ContractError("worker_event_type_invalid")
    session_id = event.get("session_id")
    index = event.get("fragment_index")
    path_value = event.get("immutable_media_file")
    expected_hash = event.get("sha256")
    if not isinstance(session_id, str) or not isinstance(index, int) or not isinstance(path_value, str):
        raise ContractError("worker_event_identity_invalid")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ContractError("worker_event_hash_invalid")
    root = media_root.resolve()
    media_path = Path(path_value).resolve()
    if root not in media_path.parents or not media_path.is_file():
        raise ContractError("worker_media_outside_authorized_root")
    if _sha256(media_path) != expected_hash:
        raise ContractError("worker_media_hash_mismatch")
    try:
        audio_status = AudioStatus(event["audio_status"])
    except (KeyError, TypeError, ValueError) as error:
        raise ContractError("worker_audio_status_invalid") from error
    has_same_source_audio = audio_status is AudioStatus.SAME_SOURCE_AUDIO_VERIFIED
    if event.get("has_same_source_audio") is not has_same_source_audio:
        raise ContractError("worker_audio_claim_mismatch")
    relative_uri = media_path.relative_to(root).as_posix()
    try:
        return SealedFragment(
            fragment_id=f"{session_id}:fragment:{index:06d}",
            session_id=session_id,
            source_context=source_context,
            start_pts_ns=int(event["start_pts_ns"]),
            end_pts_ns=int(event["end_pts_ns"]),
            media_uri=f"local://capture/{relative_uri}",
            media_sha256=expected_hash,
            has_video=True,
            has_same_source_audio=has_same_source_audio,
            audio_status=audio_status,
            pc_arrival_first_ns=int(event["pc_arrival_first_monotonic_ns"]),
            pc_sealed_ns=int(event["pc_sealed_monotonic_ns"]),
            gap_before=bool(
                event.get("skipped_nonmonotonic_packets")
                or event.get("skipped_pre_roll_packets")
                or event.get("skipped_mux_packets")
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ContractError("worker_event_payload_invalid") from error
