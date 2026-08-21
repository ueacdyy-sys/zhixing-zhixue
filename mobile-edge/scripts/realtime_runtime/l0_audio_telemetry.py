"""Read-only binding of paired-phone L0 audio telemetry to PC media ranges.

This module deliberately does not construct the formal v2
``AudioCapabilitySnapshot`` and never admits L1.  It makes the existing,
authenticated handset transport facts auditable beside the PC fragment that
overlaps their RTSP PTS range.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .contracts import ContractError


_CAPTURE_PATHS = {"NONE", "PLAYBACK", "MICROPHONE", "MIXED"}
_STATUSES = {"NOT_REQUESTED", "CAPTURE_ACTIVE_UNVERIFIED", "UNRESOLVED"}
_RESTRICTIONS = {
    "NONE", "APPLICATION_DISALLOWED", "DRM_PROTECTED", "SYSTEM_POLICY",
    "PERMISSION_DENIED", "CAPTURE_FAILURE", "UNKNOWN",
}


@dataclass(frozen=True)
class L0AudioTelemetryReference:
    """One immutable, range-scoped handset observation retained for audit."""

    snapshot_id: str
    payload_sha256: str
    session_epoch_id: str
    capture_path: str
    status: str
    restriction: str
    video_pts_start_ns: int
    video_pts_end_ns: int

    def __post_init__(self) -> None:
        if not self.snapshot_id or len(self.payload_sha256) != 64 or not self.session_epoch_id:
            raise ContractError("l0_audio_telemetry_identity_invalid")
        if self.capture_path not in _CAPTURE_PATHS or self.status not in _STATUSES or self.restriction not in _RESTRICTIONS:
            raise ContractError("l0_audio_telemetry_state_invalid")
        if self.video_pts_start_ns < 0 or self.video_pts_end_ns < self.video_pts_start_ns:
            raise ContractError("l0_audio_telemetry_pts_invalid")


def _canonical_payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _reference_from_record(
    record: dict[str, Any],
    *,
    capture_session_id: str,
    capture_generation: int,
) -> L0AudioTelemetryReference | None:
    if record.get("event_type") != "CaptureAudioCapabilityObservedL0":
        raise ContractError("l0_audio_telemetry_event_type_invalid")
    record_session_id = record.get("capture_session_id")
    payload = record.get("payload")
    if not isinstance(record_session_id, str) or not isinstance(payload, dict):
        raise ContractError("l0_audio_telemetry_record_invalid")
    if record_session_id != capture_session_id:
        return None
    raw_generation = payload.get("capture_generation")
    if type(raw_generation) is not int or raw_generation < 1:
        raise ContractError("l0_audio_telemetry_generation_invalid")
    if raw_generation != capture_generation:
        return None
    recorded_hash = record.get("payload_sha256")
    if not isinstance(recorded_hash, str) or len(recorded_hash) != 64:
        raise ContractError("l0_audio_telemetry_hash_invalid")
    if _canonical_payload_hash(payload) != recorded_hash:
        raise ContractError("l0_audio_telemetry_hash_mismatch")
    snapshot_id = payload.get("snapshot_id")
    epoch_id = payload.get("session_epoch_id")
    capture_path = payload.get("capture_path")
    status = payload.get("status")
    restriction = payload.get("restriction")
    start_us = payload.get("video_pts_start_us")
    end_us = payload.get("video_pts_end_us")
    if (
        not isinstance(snapshot_id, str)
        or not isinstance(epoch_id, str)
        or not isinstance(capture_path, str)
        or not isinstance(status, str)
        or not isinstance(restriction, str)
        or type(start_us) is not int
        or type(end_us) is not int
    ):
        raise ContractError("l0_audio_telemetry_payload_invalid")
    return L0AudioTelemetryReference(
        snapshot_id=snapshot_id,
        payload_sha256=recorded_hash,
        session_epoch_id=epoch_id,
        capture_path=capture_path,
        status=status,
        restriction=restriction,
        video_pts_start_ns=start_us * 1_000,
        video_pts_end_ns=end_us * 1_000,
    )


def load_fragment_audio_telemetry(
    journal_path: Path | None,
    *,
    capture_session_id: str,
    capture_generation: int,
    start_pts_ns: int,
    end_pts_ns: int,
) -> tuple[L0AudioTelemetryReference, ...]:
    """Return verified L0 records whose video PTS range overlaps one fragment.

    Missing telemetry is explicitly represented by an empty tuple.  It is not
    converted into a no-audio or same-source claim.
    """

    if not capture_session_id or type(capture_generation) is not int or capture_generation < 1:
        raise ContractError("l0_audio_telemetry_scope_invalid")
    if start_pts_ns < 0 or end_pts_ns <= start_pts_ns:
        raise ContractError("l0_audio_telemetry_fragment_pts_invalid")
    if journal_path is None or not journal_path.is_file():
        return ()
    references: dict[str, L0AudioTelemetryReference] = {}
    for line_number, line in enumerate(journal_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise ContractError("l0_audio_telemetry_journal_json_invalid") from error
        if not isinstance(raw, dict):
            raise ContractError("l0_audio_telemetry_journal_record_invalid")
        reference = _reference_from_record(
            raw,
            capture_session_id=capture_session_id,
            capture_generation=capture_generation,
        )
        if reference is None:
            continue
        prior = references.get(reference.snapshot_id)
        if prior is not None and prior != reference:
            raise ContractError("l0_audio_telemetry_snapshot_conflict")
        references[reference.snapshot_id] = reference
    return tuple(
        sorted(
            (
                reference for reference in references.values()
                if reference.video_pts_start_ns <= end_pts_ns and reference.video_pts_end_ns >= start_pts_ns
            ),
            key=lambda item: (item.video_pts_start_ns, item.video_pts_end_ns, item.snapshot_id),
        )
    )
