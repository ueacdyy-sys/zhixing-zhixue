"""Framework-independent contracts for durable online multimodal evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceContext(StrEnum):
    """Legacy candidate/visit context. New episode contracts use SourceKind."""

    PHONE_DAILY = "PHONE_DAILY"
    PC_LEARNING = "PC_LEARNING"
    GLASSES_LEARNING = "GLASSES_LEARNING"


class SourceKind(StrEnum):
    PHONE_SCREEN = "PHONE_SCREEN"
    GLASSES_FIRST_PERSON = "GLASSES_FIRST_PERSON"
    PC_LEARNING = "PC_LEARNING"
    PAPER_TEXTBOOK = "PAPER_TEXTBOOK"


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


class AudioCaptureMode(StrEnum):
    PLAYBACK = "PLAYBACK"
    MICROPHONE = "MICROPHONE"
    MIXED = "MIXED"
    NONE = "NONE"


class AudioRestriction(StrEnum):
    """Why requested playback audio cannot be trusted as same-source media."""

    NONE = "NONE"
    APPLICATION_DISALLOWED = "APPLICATION_DISALLOWED"
    DRM_PROTECTED = "DRM_PROTECTED"
    SYSTEM_POLICY = "SYSTEM_POLICY"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CAPTURE_FAILURE = "CAPTURE_FAILURE"
    UNKNOWN = "UNKNOWN"


class AudioResolution(StrEnum):
    SAME_SOURCE_VERIFIED = "SAME_SOURCE_VERIFIED"
    NO_AUDIO_TRACK_VERIFIED = "NO_AUDIO_TRACK_VERIFIED"
    AUDIO_REQUIRED_UNRESOLVED = "AUDIO_REQUIRED_UNRESOLVED"


class SemanticAudioRequirement(StrEnum):
    """Whether a stable semantic scope may omit audio, not whether capture saw a track."""

    AUDIO_REQUIRED_UNRESOLVED = "AUDIO_REQUIRED_UNRESOLVED"
    AUDIO_NOT_REQUIRED_VERIFIED = "AUDIO_NOT_REQUIRED_VERIFIED"


class PcBufferGapDisposition(StrEnum):
    CONTIGUOUS = "CONTIGUOUS"
    GAP_DETECTED = "GAP_DETECTED"
    QUARANTINED = "QUARANTINED"


class AnalysisRouteState(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    PC_LOCAL_ACTIVE = "PC_LOCAL_ACTIVE"
    PC_BUFFER_ONLY = "PC_BUFFER_ONLY"
    CLOUD_ACTIVE = "CLOUD_ACTIVE"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class L0HeartbeatState(StrEnum):
    ACTIVE = "ACTIVE"
    SEMANTIC_STALLED = "SEMANTIC_STALLED"


class LateFactDisposition(StrEnum):
    REASSESS_UNPRESENTED = "REASSESS_UNPRESENTED"
    REVISE_PRESENTED = "REVISE_PRESENTED"
    INVALIDATE_WITHDRAW = "INVALIDATE_WITHDRAW"
    QUARANTINE = "QUARANTINE"


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


class EpisodeStatus(StrEnum):
    """Lifecycle of an inferred content unit, never a fabricated platform ID."""

    OPEN = "OPEN"
    GAP_DETECTED = "GAP_DETECTED"
    EPISODE_AMBIGUOUS = "EPISODE_AMBIGUOUS"
    CLOSED = "CLOSED"


class LearningMomentStatus(StrEnum):
    """Discover lifecycle, intentionally independent from notification delivery."""

    ACTIVE_DISCOVER = "ACTIVE_DISCOVER"
    REVISED = "REVISED"
    WITHDRAWN = "WITHDRAWN"
    TOMBSTONED = "TOMBSTONED"


class SemanticCompleteness(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    AUDIO_REQUIRED_UNRESOLVED = "AUDIO_REQUIRED_UNRESOLVED"
    AUDIO_NOT_REQUIRED = "AUDIO_NOT_REQUIRED"
    INCOMPLETE = "INCOMPLETE"
    WINDOW_COMPLETE = "WINDOW_COMPLETE"
    EPISODE_COMPLETE = "EPISODE_COMPLETE"


class SemanticScopeStability(StrEnum):
    TENTATIVE = "TENTATIVE"
    STABLE = "STABLE"
    REVISED = "REVISED"
    INVALIDATED = "INVALIDATED"


class BehaviorOrigin(StrEnum):
    STUDENT_EXPLICIT = "STUDENT_EXPLICIT"
    ANDROID_OBSERVED = "ANDROID_OBSERVED"
    ANALYSIS_OBSERVED = "ANALYSIS_OBSERVED"
    SYSTEM_DELIVERY = "SYSTEM_DELIVERY"
    SYSTEM_RESTORE = "SYSTEM_RESTORE"
    SYSTEM_MIGRATION = "SYSTEM_MIGRATION"


class ObservationTier(StrEnum):
    VERIFIED_PLAYER = "VERIFIED_PLAYER"
    SCREEN_INFERRED = "SCREEN_INFERRED"
    UNKNOWN = "UNKNOWN"


class ProgressEvidenceKind(StrEnum):
    DIRECT_PROGRESS_OBSERVED = "DIRECT_PROGRESS_OBSERVED"
    WEAK_ATTENTION_SIGNAL = "WEAK_ATTENTION_SIGNAL"
    UNKNOWN = "UNKNOWN"


class BehaviorScopeRelation(StrEnum):
    """The verified causal relation from a behavior fact to an L1 target scope."""

    SAME_SCOPE = "SAME_SCOPE"
    CONTINUOUS_SAME_EPISODE = "CONTINUOUS_SAME_EPISODE"
    UNKNOWN = "UNKNOWN"


class EpisodeAttributionState(StrEnum):
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"


class InterestResult(StrEnum):
    NOT_READY = "NOT_READY"
    INTEREST_CONFIRMED = "INTEREST_CONFIRMED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OfferResult(StrEnum):
    NOT_OFFERABLE = "NOT_OFFERABLE"
    OFFERABLE = "OFFERABLE"
    SUPPRESSED = "SUPPRESSED"
    REVOKED = "REVOKED"


class InterruptionFeedbackKind(StrEnum):
    SYSTEM_BLOCKED = "SYSTEM_BLOCKED"
    DISMISSED = "DISMISSED"
    DEFERRED_BY_STUDENT = "DEFERRED_BY_STUDENT"
    NOT_INTERESTED = "NOT_INTERESTED"
    TOPIC_MUTED = "TOPIC_MUTED"
    REVOKED_BY_STUDENT = "REVOKED_BY_STUDENT"


class ContractError(ValueError):
    """Raised when evidence would make a false cross-media or cross-time claim."""


def _require_hashes(hashes: tuple[str, ...]) -> None:
    if not hashes or any(len(item) != 64 for item in hashes) or len(set(hashes)) != len(hashes):
        raise ContractError("source_hashes_invalid")


@dataclass(frozen=True)
class AudioCapabilitySnapshot:
    """Auditable audio state; capture failure never becomes a silent-content claim."""

    snapshot_id: str
    learner_id: str
    session_id: str
    capture_consent_id: str
    consent_generation: int
    source_kind: SourceKind
    start_pts_ns: int
    end_pts_ns: int
    capture_mode: AudioCaptureMode
    application_package_id: str | None
    restriction: AudioRestriction
    resolution: AudioResolution
    audio_track_hashes: tuple[str, ...]
    absence_proof_hash: str | None
    source_fragment_hashes: tuple[str, ...]
    clock_domain_id: str
    sync_error_ns: int | None
    sync_sample_hash: str | None
    max_allowed_sync_error_ns: int | None
    failure_code: str | None
    recovery_attempt_id: str | None
    policy_version: str

    def __post_init__(self) -> None:
        if not all((self.snapshot_id, self.learner_id, self.session_id, self.capture_consent_id, self.policy_version)):
            raise ContractError("audio_snapshot_identity_invalid")
        if self.consent_generation < 1 or self.start_pts_ns < 0 or self.end_pts_ns <= self.start_pts_ns:
            raise ContractError("audio_snapshot_scope_or_pts_invalid")
        if self.application_package_id is not None and not self.application_package_id.strip():
            raise ContractError("audio_application_package_invalid")
        if self.audio_track_hashes:
            _require_hashes(self.audio_track_hashes)
        _require_hashes(self.source_fragment_hashes)
        if self.absence_proof_hash is not None and len(self.absence_proof_hash) != 64:
            raise ContractError("audio_absence_proof_invalid")
        if not self.clock_domain_id:
            raise ContractError("audio_clock_domain_required")
        if self.sync_error_ns is not None and self.sync_error_ns < 0:
            raise ContractError("audio_sync_error_invalid")
        if self.sync_sample_hash is not None and len(self.sync_sample_hash) != 64:
            raise ContractError("audio_sync_sample_hash_invalid")
        if self.max_allowed_sync_error_ns is not None and self.max_allowed_sync_error_ns < 0:
            raise ContractError("audio_sync_threshold_invalid")
        if self.resolution is AudioResolution.SAME_SOURCE_VERIFIED:
            if self.capture_mode is not AudioCaptureMode.PLAYBACK:
                raise ContractError("verified_audio_requires_playback_mode")
            if self.restriction is not AudioRestriction.NONE:
                raise ContractError("verified_audio_cannot_have_restriction")
            if not self.audio_track_hashes:
                raise ContractError("verified_audio_requires_track_proof")
            if self.sync_error_ns is None:
                raise ContractError("verified_audio_requires_sync_proof")
            if self.sync_sample_hash is None or self.max_allowed_sync_error_ns is None:
                raise ContractError("verified_audio_requires_bounded_sync_proof")
            if self.sync_error_ns > self.max_allowed_sync_error_ns:
                raise ContractError("verified_audio_sync_error_exceeds_policy")
            if self.absence_proof_hash is not None or self.failure_code is not None:
                raise ContractError("verified_audio_has_conflicting_claim")
        elif self.resolution is AudioResolution.NO_AUDIO_TRACK_VERIFIED:
            if self.capture_mode is not AudioCaptureMode.NONE:
                raise ContractError("no_audio_requires_none_mode")
            if self.restriction is not AudioRestriction.NONE:
                raise ContractError("no_audio_cannot_have_restriction")
            if self.audio_track_hashes:
                raise ContractError("no_audio_cannot_have_track")
            if self.absence_proof_hash is None:
                raise ContractError("no_audio_requires_absence_proof")
            if (
                self.sync_error_ns is not None
                or self.sync_sample_hash is not None
                or self.max_allowed_sync_error_ns is not None
                or self.failure_code is not None
                or self.recovery_attempt_id is not None
            ):
                raise ContractError("no_audio_has_conflicting_claim")
        else:
            if self.capture_mode is AudioCaptureMode.NONE:
                raise ContractError("unresolved_audio_cannot_claim_none")
            if self.restriction is AudioRestriction.NONE:
                raise ContractError("unresolved_audio_requires_restriction")
            if not self.failure_code:
                raise ContractError("unresolved_audio_requires_failure_code")
            if self.absence_proof_hash is not None:
                raise ContractError("unresolved_audio_cannot_claim_absence")

    @property
    def permits_audio_not_required(self) -> bool:
        """Deliberately fail closed: absence of a track is never semantic sufficiency."""

        return False


@dataclass(frozen=True)
class SemanticAudioRequirementDecision:
    """Scope-level proof that visual/text evidence makes audio semantically unnecessary."""

    decision_id: str
    learner_id: str
    session_id: str
    capture_consent_id: str
    consent_generation: int
    source_kind: SourceKind
    scope_id: str
    scope_hash: str
    start_pts_ns: int
    end_pts_ns: int
    snapshot: AudioCapabilitySnapshot
    requirement: SemanticAudioRequirement
    semantic_nonessential_evidence_hashes: tuple[str, ...]
    visual_text_coverage_hashes: tuple[str, ...]
    policy_version: str
    decision_trace_hash: str

    def __post_init__(self) -> None:
        if not all((
            self.decision_id,
            self.learner_id,
            self.session_id,
            self.capture_consent_id,
            self.scope_id,
            self.policy_version,
        )):
            raise ContractError("audio_requirement_identity_invalid")
        if len(self.scope_hash) != 64 or len(self.decision_trace_hash) != 64:
            raise ContractError("audio_requirement_hash_invalid")
        if self.consent_generation < 1 or self.start_pts_ns < 0 or self.end_pts_ns <= self.start_pts_ns:
            raise ContractError("audio_requirement_range_invalid")
        snapshot = self.snapshot
        if (
            snapshot.learner_id != self.learner_id
            or snapshot.session_id != self.session_id
            or snapshot.capture_consent_id != self.capture_consent_id
            or snapshot.consent_generation != self.consent_generation
            or snapshot.source_kind is not self.source_kind
            or self.start_pts_ns < snapshot.start_pts_ns
            or self.end_pts_ns > snapshot.end_pts_ns
        ):
            raise ContractError("audio_requirement_cross_scope_snapshot")
        if self.requirement is SemanticAudioRequirement.AUDIO_NOT_REQUIRED_VERIFIED:
            if snapshot.resolution is not AudioResolution.NO_AUDIO_TRACK_VERIFIED:
                raise ContractError("audio_not_required_requires_verified_absence")
            _require_hashes(self.semantic_nonessential_evidence_hashes)
            _require_hashes(self.visual_text_coverage_hashes)
        elif self.semantic_nonessential_evidence_hashes or self.visual_text_coverage_hashes:
            raise ContractError("unresolved_audio_requirement_cannot_claim_semantic_coverage")

    @property
    def permits_audio_not_required(self) -> bool:
        return self.requirement is SemanticAudioRequirement.AUDIO_NOT_REQUIRED_VERIFIED


@dataclass(frozen=True)
class PcBufferedFragment:
    """One locally durable, replayable media fragment in a PC-only transport outbox."""

    fragment_id: str
    sequence: int
    start_pts_ns: int
    end_pts_ns: int
    media_hash: str
    local_storage_hash: str
    outbox_id: str
    replay_idempotency_key: str

    def __post_init__(self) -> None:
        if not all((self.fragment_id, self.outbox_id, self.replay_idempotency_key)):
            raise ContractError("buffered_fragment_identity_invalid")
        if self.sequence < 0 or self.start_pts_ns < 0 or self.end_pts_ns <= self.start_pts_ns:
            raise ContractError("buffered_fragment_range_invalid")
        if len(self.media_hash) != 64 or len(self.local_storage_hash) != 64:
            raise ContractError("buffered_fragment_hash_invalid")


@dataclass(frozen=True)
class PcBufferResumeReceipt:
    """A PC-only outbox resume intent; route authority is resolved later by T091."""

    receipt_id: str
    learner_id: str
    session_id: str
    capture_consent_id: str
    consent_generation: int
    route_lease_id: str
    route_epoch: int
    capture_epoch: int
    owner_endpoint_id: str
    buffered_start_pts_ns: int
    buffered_end_pts_ns: int
    cache_manifest_hash: str
    resumed_owner_endpoint_id: str
    fragments: tuple[PcBufferedFragment, ...]
    last_acked_sequence: int
    resume_attempt_id: str
    replay_idempotency_key: str
    gap_disposition: PcBufferGapDisposition

    def __post_init__(self) -> None:
        if not all((
            self.receipt_id,
            self.learner_id,
            self.session_id,
            self.capture_consent_id,
            self.route_lease_id,
            self.owner_endpoint_id,
            self.resumed_owner_endpoint_id,
            self.resume_attempt_id,
            self.replay_idempotency_key,
        )):
            raise ContractError("resume_identity_invalid")
        if self.consent_generation < 1 or self.route_epoch < 1 or self.capture_epoch < 1:
            raise ContractError("resume_generation_invalid")
        if self.buffered_start_pts_ns < 0 or self.buffered_end_pts_ns <= self.buffered_start_pts_ns:
            raise ContractError("resume_pts_invalid")
        if len(self.cache_manifest_hash) != 64:
            raise ContractError("resume_manifest_hash_invalid")
        if self.owner_endpoint_id != self.resumed_owner_endpoint_id:
            raise ContractError("resume_cannot_change_route_owner")
        if not self.fragments:
            raise ContractError("resume_requires_durable_fragments")
        sequences = tuple(item.sequence for item in self.fragments)
        if len(set(sequences)) != len(sequences) or sequences != tuple(range(sequences[0], sequences[0] + len(sequences))):
            raise ContractError("resume_fragment_sequence_gap")
        if self.last_acked_sequence < -1 or self.last_acked_sequence > sequences[-1]:
            raise ContractError("resume_ack_cursor_invalid")
        if self.fragments[0].start_pts_ns != self.buffered_start_pts_ns or self.fragments[-1].end_pts_ns != self.buffered_end_pts_ns:
            raise ContractError("resume_fragment_range_mismatch")
        has_pts_gap = any(
            current.start_pts_ns != previous.end_pts_ns
            for previous, current in zip(self.fragments, self.fragments[1:])
        )
        if self.gap_disposition is PcBufferGapDisposition.CONTIGUOUS and has_pts_gap:
            raise ContractError("resume_unacknowledged_pts_gap")
        if self.gap_disposition is PcBufferGapDisposition.GAP_DETECTED and not has_pts_gap:
            raise ContractError("resume_gap_disposition_without_gap")


@dataclass(frozen=True)
class LateFactAdmission:
    """Late L0 evidence must be reassessed or revisioned before it affects learning output."""

    fact_id: str
    learner_id: str
    session_id: str
    episode_id: str
    capture_consent_id: str
    consent_generation: int
    source_kind: SourceKind
    scope_id: str
    scope_hash: str
    base_scope_revision: int
    fact_start_pts_ns: int
    fact_end_pts_ns: int
    event_time_watermark_ns: int
    arrived_elapsed_ns: int
    evidence_hashes: tuple[str, ...]
    fact_content_hash: str
    admission_idempotency_key: str
    allowed_lateness_ns: int
    late_policy_id: str
    presentation_revision_ref: str | None
    disposition: LateFactDisposition

    def __post_init__(self) -> None:
        if not all((
            self.fact_id,
            self.learner_id,
            self.session_id,
            self.episode_id,
            self.capture_consent_id,
            self.scope_id,
            self.admission_idempotency_key,
            self.late_policy_id,
        )):
            raise ContractError("late_fact_identity_invalid")
        if (
            len(self.scope_hash) != 64
            or len(self.fact_content_hash) != 64
            or self.base_scope_revision < 1
            or self.consent_generation < 1
            or self.fact_start_pts_ns < 0
            or self.fact_end_pts_ns <= self.fact_start_pts_ns
            or self.arrived_elapsed_ns < 0
            or self.allowed_lateness_ns < 0
        ):
            raise ContractError("late_fact_range_invalid")
        _require_hashes(self.evidence_hashes)
        if self.fact_end_pts_ns >= self.event_time_watermark_ns:
            raise ContractError("fact_is_not_late")
        beyond_allowed_lateness = self.event_time_watermark_ns - self.fact_end_pts_ns > self.allowed_lateness_ns
        if beyond_allowed_lateness and self.disposition is not LateFactDisposition.QUARANTINE:
            raise ContractError("late_fact_exceeds_allowed_lateness")
        if self.presentation_revision_ref:
            if self.disposition not in {
                LateFactDisposition.REVISE_PRESENTED,
                LateFactDisposition.INVALIDATE_WITHDRAW,
                LateFactDisposition.QUARANTINE,
            }:
                raise ContractError("presented_late_fact_requires_revision_or_withdrawal")
        elif self.disposition not in {
            LateFactDisposition.REASSESS_UNPRESENTED,
            LateFactDisposition.QUARANTINE,
        }:
            raise ContractError("unpresented_late_fact_requires_reassessment")


@dataclass(frozen=True)
class RealtimeSemanticFact:
    """An immutable L0 fact; late admission never rewrites or promotes it directly."""

    fact_id: str
    idempotency_key: str
    learner_id: str
    session_id: str
    episode_id: str
    capture_consent_id: str
    consent_generation: int
    source_kind: SourceKind
    start_pts_ns: int
    end_pts_ns: int
    fact_kind: str
    content_hash: str
    evidence_hashes: tuple[str, ...]
    semantic_policy_version: str
    provenance_hash: str

    def __post_init__(self) -> None:
        if not all((
            self.fact_id,
            self.idempotency_key,
            self.learner_id,
            self.session_id,
            self.episode_id,
            self.capture_consent_id,
            self.fact_kind,
            self.semantic_policy_version,
        )):
            raise ContractError("semantic_fact_identity_invalid")
        if (
            self.consent_generation < 1
            or self.start_pts_ns < 0
            or self.end_pts_ns <= self.start_pts_ns
            or len(self.content_hash) != 64
            or len(self.provenance_hash) != 64
        ):
            raise ContractError("semantic_fact_range_or_hash_invalid")
        _require_hashes(self.evidence_hashes)


@dataclass(frozen=True)
class AnalysisRouteLease:
    """The sole analysis owner for one learner/session/consent generation."""

    lease_id: str
    learner_id: str
    session_id: str
    capture_consent_id: str
    consent_generation: int
    route_epoch: int
    state: AnalysisRouteState
    owner_endpoint_id: str | None
    opened_receipt_hash: str
    student_confirmation_hash: str
    issued_elapsed_ns: int
    last_renewed_elapsed_ns: int
    expires_elapsed_ns: int

    def __post_init__(self) -> None:
        if not all((
            self.lease_id,
            self.learner_id,
            self.session_id,
            self.capture_consent_id,
            self.opened_receipt_hash,
            self.student_confirmation_hash,
        )):
            raise ContractError("analysis_route_identity_invalid")
        if (
            self.consent_generation < 1
            or self.route_epoch < 1
            or self.issued_elapsed_ns < 0
            or self.last_renewed_elapsed_ns < self.issued_elapsed_ns
            or self.expires_elapsed_ns <= self.last_renewed_elapsed_ns
        ):
            raise ContractError("analysis_route_generation_invalid")
        if len(self.opened_receipt_hash) != 64 or len(self.student_confirmation_hash) != 64:
            raise ContractError("analysis_route_receipt_hash_invalid")
        if self.state is AnalysisRouteState.UNAVAILABLE:
            if self.owner_endpoint_id is not None:
                raise ContractError("unavailable_route_cannot_have_owner")
        elif self.state in {AnalysisRouteState.CLOSED, AnalysisRouteState.EXPIRED, AnalysisRouteState.REVOKED}:
            raise ContractError("terminal_route_requires_ledger_transition")
        elif not self.owner_endpoint_id:
            raise ContractError("active_route_requires_owner")


@dataclass(frozen=True)
class L0SemanticHeartbeat:
    """Monotonic proof that current media is being semantically processed on time."""

    heartbeat_id: str
    learner_id: str
    session_id: str
    capture_consent_id: str
    consent_generation: int
    route_lease_id: str
    route_epoch: int
    processed_media_watermark_pts_ns: int
    semantic_watermark_pts_ns: int
    last_ack_fact_id: str
    observed_elapsed_ns: int
    deadline_ns: int
    worker_health_lease_id: str
    slo_policy_version: str

    def __post_init__(self) -> None:
        if not all((
            self.heartbeat_id,
            self.learner_id,
            self.session_id,
            self.capture_consent_id,
            self.route_lease_id,
            self.last_ack_fact_id,
            self.worker_health_lease_id,
            self.slo_policy_version,
        )):
            raise ContractError("l0_heartbeat_identity_invalid")
        if self.consent_generation < 1 or self.route_epoch < 1:
            raise ContractError("l0_heartbeat_generation_invalid")
        if (
            self.processed_media_watermark_pts_ns < 0
            or self.semantic_watermark_pts_ns < 0
            or self.semantic_watermark_pts_ns > self.processed_media_watermark_pts_ns
            or self.observed_elapsed_ns < 0
            or self.deadline_ns <= 0
        ):
            raise ContractError("l0_heartbeat_range_invalid")


@dataclass(frozen=True)
class ContentEpisode:
    """A bounded inference over a continuous source, not a third-party video identity."""

    episode_id: str
    learner_id: str
    session_id: str
    capture_consent_id: str
    consent_generation: int
    source_kind: SourceKind
    start_pts_ns: int
    continuity_start_pts_ns: int
    end_pts_ns: int | None
    status: EpisodeStatus
    boundary_confidence: float
    boundary_reason: str
    resolver_version: str
    policy_version: str

    def __post_init__(self) -> None:
        if not self.episode_id or not self.session_id or not self.boundary_reason or not self.resolver_version:
            raise ContractError("episode_identity_invalid")
        if not self.learner_id or not self.capture_consent_id or not self.policy_version:
            raise ContractError("episode_scope_invalid")
        if self.consent_generation < 1:
            raise ContractError("episode_consent_generation_invalid")
        if (
            self.start_pts_ns < 0
            or self.continuity_start_pts_ns < self.start_pts_ns
            or (self.end_pts_ns is not None and self.end_pts_ns <= self.start_pts_ns)
        ):
            raise ContractError("episode_pts_invalid")
        if not 0.0 <= self.boundary_confidence <= 1.0:
            raise ContractError("episode_boundary_confidence_invalid")
        if self.status is EpisodeStatus.OPEN and self.end_pts_ns is not None:
            raise ContractError("open_episode_cannot_have_end_pts")
        if self.status is EpisodeStatus.CLOSED and self.end_pts_ns is None:
            raise ContractError("closed_episode_requires_end_pts")


@dataclass(frozen=True)
class LearningMoment:
    """A coherent intervention topic, deliberately narrower than a media episode.

    A long video or live stream can contain more than one learning moment.  The
    moment therefore owns notification budgeting and graph grouping; it must
    never be inferred from a third-party video ID or merely from elapsed time.
    """

    moment_id: str
    episode: ContentEpisode
    semantic_lineage_id: str
    learning_anchor_id: str
    intervention_key: str
    current_revision_id: str
    status: LearningMomentStatus
    created_elapsed_ns: int
    policy_version: str

    def __post_init__(self) -> None:
        if not all((
            self.moment_id,
            self.episode.episode_id,
            self.semantic_lineage_id,
            self.learning_anchor_id,
            self.intervention_key,
            self.current_revision_id,
            self.policy_version,
        )):
            raise ContractError("learning_moment_identity_invalid")
        if self.created_elapsed_ns < 0:
            raise ContractError("learning_moment_time_invalid")
        expected_intervention_key = f"l1:{self.episode.learner_id}:{self.moment_id}:NORMAL"
        if self.intervention_key != expected_intervention_key:
            raise ContractError("learning_moment_intervention_key_invalid")


@dataclass(frozen=True)
class LearningMomentRevision:
    """Immutable L1/Discover projection of a learning moment at one scope revision."""

    revision_id: str
    moment: LearningMoment
    revision: int
    replaces_revision_id: str | None
    anchor_scope: "SemanticScope"
    interest_assessment_id: str
    learning_offer_assessment_id: str
    evidence_hashes: tuple[str, ...]
    revision_reason: str
    created_elapsed_ns: int

    def __post_init__(self) -> None:
        if not all((
            self.revision_id,
            self.moment.moment_id,
            self.interest_assessment_id,
            self.learning_offer_assessment_id,
            self.revision_reason,
        )):
            raise ContractError("learning_moment_revision_identity_invalid")
        if self.revision < 1 or self.created_elapsed_ns < self.moment.created_elapsed_ns:
            raise ContractError("learning_moment_revision_order_invalid")
        if self.revision == 1 and self.replaces_revision_id is not None:
            raise ContractError("initial_learning_moment_revision_cannot_replace")
        if self.revision > 1 and not self.replaces_revision_id:
            raise ContractError("learning_moment_revision_requires_predecessor")
        scope = self.anchor_scope
        if (
            scope.episode.episode_id != self.moment.episode.episode_id
            or scope.episode.learner_id != self.moment.episode.learner_id
            or scope.episode.session_id != self.moment.episode.session_id
            or scope.episode.capture_consent_id != self.moment.episode.capture_consent_id
            or scope.episode.consent_generation != self.moment.episode.consent_generation
            or scope.semantic_lineage_id != self.moment.semantic_lineage_id
            or scope.stability is not SemanticScopeStability.STABLE
        ):
            raise ContractError("learning_moment_revision_scope_binding_invalid")
        _require_hashes(self.evidence_hashes)


@dataclass(frozen=True)
class SemanticScope:
    """An immutable semantic range. Revisions point forward and never overwrite evidence."""

    scope_id: str
    episode: ContentEpisode
    start_pts_ns: int
    end_pts_ns: int
    scope_hash: str
    semantic_lineage_id: str
    completeness: SemanticCompleteness
    stability: SemanticScopeStability
    semantic_revision: int
    event_time_watermark_ns: int
    replaces_scope_id: str | None = None
    predecessor_scope_hash: str | None = None

    def __post_init__(self) -> None:
        if not self.scope_id or not self.episode.episode_id:
            raise ContractError("scope_identity_invalid")
        if self.start_pts_ns < self.episode.continuity_start_pts_ns or self.end_pts_ns <= self.start_pts_ns:
            if self.start_pts_ns < self.episode.continuity_start_pts_ns:
                raise ContractError("scope_crosses_episode_gap")
            raise ContractError("scope_pts_invalid")
        if self.episode.end_pts_ns is not None and self.end_pts_ns > self.episode.end_pts_ns:
            raise ContractError("scope_pts_outside_episode")
        if len(self.scope_hash) != 64 or not self.semantic_lineage_id:
            raise ContractError("scope_hash_invalid")
        if self.semantic_revision < 1 or self.event_time_watermark_ns < 0:
            raise ContractError("scope_revision_or_watermark_invalid")
        if self.stability is SemanticScopeStability.STABLE:
            if self.episode.status is EpisodeStatus.EPISODE_AMBIGUOUS:
                raise ContractError("stable_scope_requires_non_ambiguous_episode")
            if self.episode.status is EpisodeStatus.GAP_DETECTED:
                raise ContractError("stable_scope_requires_continuous_episode")
            if self.completeness not in {
                SemanticCompleteness.WINDOW_COMPLETE,
                SemanticCompleteness.EPISODE_COMPLETE,
            } or self.event_time_watermark_ns < self.end_pts_ns:
                raise ContractError("stable_scope_requires_complete_range")
        if self.stability in {SemanticScopeStability.REVISED, SemanticScopeStability.INVALIDATED}:
            if not self.replaces_scope_id:
                raise ContractError("revised_scope_requires_predecessor")
            if self.predecessor_scope_hash is None or len(self.predecessor_scope_hash) != 64:
                raise ContractError("revised_scope_requires_predecessor_hash")
            if self.semantic_revision < 2:
                raise ContractError("revised_scope_requires_incremented_revision")
        elif self.replaces_scope_id is not None or self.predecessor_scope_hash is not None:
            raise ContractError("non_revised_scope_cannot_replace_predecessor")


@dataclass(frozen=True)
class BehaviorEvent:
    """An observable student-side fact, never a guessed player API event."""

    event_id: str
    learner_id: str
    episode_id: str | None
    attribution_state: EpisodeAttributionState
    session_id: str
    capture_consent_id: str
    source_kind: SourceKind
    observed_scope_id: str | None
    scope_relation: BehaviorScopeRelation
    origin: BehaviorOrigin
    observation_tier: ObservationTier
    progress_kind: ProgressEvidenceKind
    attribution_confidence: float
    evidence_start_pts_ns: int
    evidence_end_pts_ns: int
    observed_elapsed_ns: int
    expires_elapsed_ns: int
    observation_adapter_id: str | None
    observation_adapter_version: str | None
    action_attestation_id: str | None
    progress_evidence_id: str | None
    semantic_lineage_id: str | None
    foreground_snapshot_id: str | None
    consent_generation: int
    foreground_valid: bool
    evidence_hashes: tuple[str, ...]
    observation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id or not self.learner_id or not self.session_id or not self.capture_consent_id:
            raise ContractError("behavior_event_identity_invalid")
        if (
            self.evidence_start_pts_ns < 0
            or self.evidence_end_pts_ns < self.evidence_start_pts_ns
            or self.observed_elapsed_ns < 0
            or self.expires_elapsed_ns <= self.observed_elapsed_ns
        ):
            raise ContractError("behavior_event_time_invalid")
        if self.attribution_state is EpisodeAttributionState.RESOLVED:
            if not self.episode_id:
                raise ContractError("resolved_behavior_requires_episode")
        elif self.episode_id is not None:
            raise ContractError("unresolved_behavior_cannot_claim_episode")
        if self.observed_scope_id is not None and not self.observed_scope_id:
            raise ContractError("behavior_event_scope_invalid")
        if self.scope_relation is BehaviorScopeRelation.SAME_SCOPE and self.observed_scope_id is None:
            raise ContractError("same_scope_event_requires_scope")
        if self.scope_relation is BehaviorScopeRelation.CONTINUOUS_SAME_EPISODE and self.observed_scope_id is None:
            raise ContractError("continuous_event_requires_observed_scope")
        if self.scope_relation is BehaviorScopeRelation.UNKNOWN and self.observed_scope_id is not None:
            raise ContractError("unknown_scope_relation_cannot_claim_scope")
        if not 0.0 <= self.attribution_confidence <= 1.0 or self.consent_generation < 1:
            raise ContractError("behavior_event_attribution_or_consent_invalid")
        _require_hashes(self.evidence_hashes)
        if (
            self.progress_kind is ProgressEvidenceKind.DIRECT_PROGRESS_OBSERVED
            and self.observation_tier is not ObservationTier.VERIFIED_PLAYER
        ):
            raise ContractError("direct_progress_requires_verified_player")
        if self.origin is BehaviorOrigin.STUDENT_EXPLICIT and (
            not self.observation_adapter_id
            or not self.observation_adapter_version
            or not self.action_attestation_id
            or not self.foreground_snapshot_id
        ):
            raise ContractError("student_explicit_requires_attestation")
        if self.origin is BehaviorOrigin.ANALYSIS_OBSERVED and (
            not self.observation_adapter_id
            or not self.observation_adapter_version
            or not self.observation_id
            or not self.foreground_snapshot_id
        ):
            raise ContractError("analysis_observed_requires_replayable_observation")
        if self.progress_kind is ProgressEvidenceKind.DIRECT_PROGRESS_OBSERVED and not self.progress_evidence_id:
            raise ContractError("direct_progress_requires_timeline_evidence")
        if self.scope_relation is not BehaviorScopeRelation.UNKNOWN and not self.semantic_lineage_id:
            raise ContractError("scoped_behavior_requires_semantic_lineage")


@dataclass(frozen=True)
class InterestAssessment:
    """Versioned interest result from auditable behavior; it is not an offer decision."""

    assessment_id: str
    learner_id: str
    target_scope: SemanticScope
    result: InterestResult
    policy_version: str
    evidence_profile_id: str
    decision_trace_hash: str
    evaluated_elapsed_ns: int
    minimum_independent_events: int
    continuous_context_max_gap_ns: int
    evidence_events: tuple[BehaviorEvent, ...]

    @property
    def episode_id(self) -> str:
        return self.target_scope.episode.episode_id

    @property
    def scope_id(self) -> str:
        return self.target_scope.scope_id

    @property
    def consent_generation(self) -> int:
        return self.target_scope.episode.consent_generation

    def __post_init__(self) -> None:
        if (
            not self.assessment_id
            or not self.learner_id
            or not self.policy_version
            or not self.evidence_profile_id
            or len(self.decision_trace_hash) != 64
        ):
            raise ContractError("interest_assessment_identity_invalid")
        if (
            self.evaluated_elapsed_ns < 0
            or self.minimum_independent_events < 1
            or self.continuous_context_max_gap_ns < 0
        ):
            raise ContractError("interest_assessment_time_or_policy_invalid")
        episode = self.target_scope.episode
        if (
            episode.learner_id != self.learner_id
            or self.target_scope.stability is not SemanticScopeStability.STABLE
            or self.target_scope.completeness not in {SemanticCompleteness.WINDOW_COMPLETE, SemanticCompleteness.EPISODE_COMPLETE}
        ):
            raise ContractError("interest_assessment_scope_invalid")
        if self.result is not InterestResult.INTEREST_CONFIRMED:
            return
        if len(self.evidence_events) < self.minimum_independent_events:
            raise ContractError("interest_evidence_insufficient")
        for event in self.evidence_events:
            if (
                event.learner_id != self.learner_id
                or event.episode_id != self.episode_id
                or event.attribution_state is not EpisodeAttributionState.RESOLVED
                or event.session_id != episode.session_id
                or event.capture_consent_id != episode.capture_consent_id
                or event.source_kind is not episode.source_kind
                or event.origin not in {BehaviorOrigin.STUDENT_EXPLICIT, BehaviorOrigin.ANALYSIS_OBSERVED}
                or not event.foreground_valid
                or event.consent_generation != self.consent_generation
                or event.scope_relation is BehaviorScopeRelation.UNKNOWN
                or event.evidence_start_pts_ns < episode.continuity_start_pts_ns
                or event.expires_elapsed_ns <= self.evaluated_elapsed_ns
            ):
                if event.origin not in {BehaviorOrigin.STUDENT_EXPLICIT, BehaviorOrigin.ANALYSIS_OBSERVED}:
                    raise ContractError("interest_event_origin_invalid")
                raise ContractError("interest_event_binding_invalid")
            if event.scope_relation is BehaviorScopeRelation.SAME_SCOPE:
                if (
                    event.observed_scope_id != self.scope_id
                    or event.semantic_lineage_id != self.target_scope.semantic_lineage_id
                    or event.evidence_start_pts_ns < self.target_scope.start_pts_ns
                    or event.evidence_end_pts_ns > self.target_scope.end_pts_ns
                ):
                    raise ContractError("interest_event_not_in_target_scope")
            elif (
                event.evidence_start_pts_ns < self.target_scope.end_pts_ns
                or event.evidence_start_pts_ns > self.target_scope.end_pts_ns + self.continuous_context_max_gap_ns
                or event.semantic_lineage_id != self.target_scope.semantic_lineage_id
            ):
                raise ContractError("interest_event_continuity_window_invalid")
        event_ids = {event.event_id for event in self.evidence_events}
        independence_keys = {
            f"action:{event.action_attestation_id}"
            if event.origin is BehaviorOrigin.STUDENT_EXPLICIT
            else f"observation:{event.observation_id}"
            for event in self.evidence_events
        }
        if len(event_ids) != len(self.evidence_events) or len(independence_keys) != len(self.evidence_events):
            raise ContractError("interest_evidence_not_independent")
        if (
            len(self.evidence_events) == 1
            and self.evidence_events[0].origin is BehaviorOrigin.ANALYSIS_OBSERVED
            and self.evidence_events[0].progress_kind is ProgressEvidenceKind.WEAK_ATTENTION_SIGNAL
        ):
            raise ContractError("interest_single_weak_signal")


@dataclass(frozen=True)
class LearningOfferAssessment:
    """Independent judgement that an understood scope is worth a low-interruption offer."""

    assessment_id: str
    learner_id: str
    episode_id: str
    learning_moment_id: str
    scope_id: str
    result: OfferResult
    explanation_object: str
    policy_version: str

    def __post_init__(self) -> None:
        if not all((self.assessment_id, self.learner_id, self.episode_id, self.learning_moment_id, self.scope_id, self.explanation_object, self.policy_version)):
            raise ContractError("learning_offer_identity_invalid")


@dataclass(frozen=True)
class InterruptionFeedback:
    feedback_id: str
    learner_id: str
    kind: InterruptionFeedbackKind
    scope: str

    def __post_init__(self) -> None:
        if not self.feedback_id or not self.learner_id or not self.scope:
            raise ContractError("interruption_feedback_identity_invalid")

    @property
    def suppresses_future_notifications(self) -> bool:
        return self.kind in {
            InterruptionFeedbackKind.DISMISSED,
            InterruptionFeedbackKind.NOT_INTERESTED,
            InterruptionFeedbackKind.TOPIC_MUTED,
        }


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
    audio_sync_error_ns: int | None = None
    audio_sync_sample_hash: str | None = None
    audio_max_allowed_sync_error_ns: int | None = None
    capture_generation: int | None = None

    def __post_init__(self) -> None:
        if not self.fragment_id or not self.session_id or not self.media_uri.startswith("local://"):
            raise ContractError("fragment_identity_invalid")
        if len(self.media_sha256) != 64 or self.start_pts_ns < 0 or self.end_pts_ns <= self.start_pts_ns:
            raise ContractError("fragment_media_or_pts_invalid")
        if not self.has_video or self.pc_arrival_first_ns < 0 or self.pc_sealed_ns < self.pc_arrival_first_ns:
            raise ContractError("fragment_stream_facts_invalid")
        if self.capture_generation is not None and (
            type(self.capture_generation) is not int or self.capture_generation < 1
        ):
            raise ContractError("fragment_capture_generation_invalid")
        if self.has_same_source_audio and self.audio_status not in {None, AudioStatus.SAME_SOURCE_AUDIO_VERIFIED}:
            raise ContractError("fragment_audio_status_mismatch")
        if not self.has_same_source_audio and self.audio_status is AudioStatus.SAME_SOURCE_AUDIO_VERIFIED:
            raise ContractError("fragment_audio_status_mismatch")
        sync_evidence = (
            self.audio_sync_error_ns,
            self.audio_sync_sample_hash,
            self.audio_max_allowed_sync_error_ns,
        )
        if self.audio_status is AudioStatus.SAME_SOURCE_AUDIO_VERIFIED:
            if (
                type(self.audio_sync_error_ns) is not int
                or self.audio_sync_error_ns < 0
                or not isinstance(self.audio_sync_sample_hash, str)
                or len(self.audio_sync_sample_hash) != 64
                or type(self.audio_max_allowed_sync_error_ns) is not int
                or self.audio_max_allowed_sync_error_ns < 0
            ):
                raise ContractError("fragment_audio_sync_evidence_required")
            if self.audio_sync_error_ns > self.audio_max_allowed_sync_error_ns:
                raise ContractError("fragment_audio_sync_exceeds_policy")
        elif any(value is not None for value in sync_evidence):
            raise ContractError("fragment_audio_sync_evidence_without_verified_audio")


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
