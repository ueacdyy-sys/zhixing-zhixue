"""Framework-independent contracts for durable online multimodal evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceContext(StrEnum):
    PHONE_DAILY = "PHONE_DAILY"
    PC_LEARNING = "PC_LEARNING"
    GLASSES_LEARNING = "GLASSES_LEARNING"


class Lane(StrEnum):
    OCR = "OCR"
    ASR = "ASR"
    VLM = "VLM"


class FusionMode(StrEnum):
    """What the candidate actually contains, never an inferred user judgement."""

    TRIMODAL = "TRIMODAL"
    VISUAL_TEXT_NO_AUDIO = "VISUAL_TEXT_NO_AUDIO"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"


class AudioStatus(StrEnum):
    SAME_SOURCE_AUDIO_VERIFIED = "SAME_SOURCE_AUDIO_VERIFIED"
    NO_AUDIO_TRACK_VERIFIED = "NO_AUDIO_TRACK_VERIFIED"
    AUDIO_INTEGRITY_UNRESOLVED = "AUDIO_INTEGRITY_UNRESOLVED"


class VisitClosureReason(StrEnum):
    CONTENT_SWITCH = "CONTENT_SWITCH"
    SESSION_ENDED = "SESSION_ENDED"


class JobState(StrEnum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    RETRY_WAIT = "RETRY_WAIT"
    COMPLETE = "COMPLETE"
    UNRESOLVED = "UNRESOLVED"


class QualityStatus(StrEnum):
    FUSION_ELIGIBLE = "FUSION_ELIGIBLE"
    RECORD_ONLY = "RECORD_ONLY"
    EXCLUDED = "EXCLUDED"


class ContractError(ValueError):
    """Raised when evidence would make a false cross-media or cross-time claim."""


def _require_hashes(hashes: tuple[str, ...]) -> None:
    if not hashes or any(len(item) != 64 for item in hashes) or len(set(hashes)) != len(hashes):
        raise ContractError("source_hashes_invalid")


@dataclass(frozen=True)
class SealedFragment:
    fragment_id: str
    session_id: str
    source_context: SourceContext
    start_pts_ns: int
    end_pts_ns: int
    media_uri: str
    media_sha256: str
    has_video: bool
    has_same_source_audio: bool
    pc_arrival_first_ns: int
    pc_sealed_ns: int
    gap_before: bool = False
    audio_status: AudioStatus | None = None

    def __post_init__(self) -> None:
        if not self.fragment_id or not self.session_id or not self.media_uri.startswith("local://"):
            raise ContractError("fragment_identity_invalid")
        if len(self.media_sha256) != 64 or self.start_pts_ns < 0 or self.end_pts_ns <= self.start_pts_ns:
            raise ContractError("fragment_media_or_pts_invalid")
        if not self.has_video or self.pc_arrival_first_ns < 0 or self.pc_sealed_ns < self.pc_arrival_first_ns:
            raise ContractError("fragment_stream_facts_invalid")
        if self.has_same_source_audio and self.audio_status not in {None, AudioStatus.SAME_SOURCE_AUDIO_VERIFIED}:
            raise ContractError("fragment_audio_status_mismatch")
        if not self.has_same_source_audio and self.audio_status is AudioStatus.SAME_SOURCE_AUDIO_VERIFIED:
            raise ContractError("fragment_audio_status_mismatch")


@dataclass(frozen=True)
class SemanticWindow:
    window_id: str
    session_id: str
    visit_id: str
    source_context: SourceContext
    start_pts_ns: int
    end_pts_ns: int
    fragment_hashes: tuple[str, ...]
    required_lanes: tuple[Lane, ...]

    def __post_init__(self) -> None:
        if not self.window_id or not self.session_id or not self.visit_id:
            raise ContractError("window_identity_invalid")
        if self.start_pts_ns < 0 or self.end_pts_ns <= self.start_pts_ns:
            raise ContractError("window_pts_invalid")
        _require_hashes(self.fragment_hashes)
        if not self.required_lanes or tuple(sorted(set(self.required_lanes), key=str)) != self.required_lanes:
            raise ContractError("window_required_lanes_invalid")


@dataclass(frozen=True)
class JobLease:
    window_id: str
    lane: Lane
    worker_id: str
    attempt_id: int
    lease_deadline_ns: int


@dataclass(frozen=True)
class WindowDescriptor:
    """Public immutable job input; workers never inspect ledger internals."""

    window_id: str
    visit_id: str
    source_context: SourceContext
    start_pts_ns: int
    end_pts_ns: int
    fragment_hashes: tuple[str, ...]
    media_uris: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.window_id or not self.visit_id or self.end_pts_ns <= self.start_pts_ns:
            raise ContractError("window_descriptor_identity_or_pts_invalid")
        _require_hashes(self.fragment_hashes)
        if len(self.fragment_hashes) != len(self.media_uris) or any(not item.startswith("local://") for item in self.media_uris):
            raise ContractError("window_descriptor_media_invalid")


@dataclass(frozen=True)
class LaneEvidence:
    window_id: str
    lane: Lane
    coverage_start_pts_ns: int
    coverage_end_pts_ns: int
    source_fragment_hashes: tuple[str, ...]
    quality_status: QualityStatus
    artifact_uri: str
    artifact_sha256: str
    started_ns: int
    completed_ns: int

    def __post_init__(self) -> None:
        if self.coverage_start_pts_ns < 0 or self.coverage_end_pts_ns <= self.coverage_start_pts_ns:
            raise ContractError("evidence_pts_invalid")
        _require_hashes(self.source_fragment_hashes)
        if not self.artifact_uri.startswith("local://") or len(self.artifact_sha256) != 64:
            raise ContractError("evidence_artifact_invalid")
        if self.started_ns < 0 or self.completed_ns < self.started_ns:
            raise ContractError("evidence_time_invalid")


@dataclass(frozen=True)
class FusedCandidate:
    window_id: str
    visit_id: str
    source_context: SourceContext
    start_pts_ns: int
    end_pts_ns: int
    evidence_uris: tuple[str, ...]
    fused_at_ns: int
    fusion_mode: FusionMode
    classification: str = "CANDIDATE_ONLY"


@dataclass(frozen=True)
class Visit:
    visit_id: str
    session_id: str
    source_context: SourceContext
    start_pts_ns: int
    end_pts_ns: int | None = None
    closure_reason: VisitClosureReason | None = None

    def __post_init__(self) -> None:
        if not self.visit_id or not self.session_id or self.start_pts_ns < 0:
            raise ContractError("visit_identity_or_pts_invalid")
        if self.end_pts_ns is None and self.closure_reason is not None:
            raise ContractError("open_visit_cannot_have_closure_reason")
        if self.end_pts_ns is not None and (
            self.end_pts_ns <= self.start_pts_ns or self.closure_reason is None
        ):
            raise ContractError("closed_visit_boundary_invalid")
