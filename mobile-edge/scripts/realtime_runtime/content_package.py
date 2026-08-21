"""The only valid PC/Cloud-to-Android L1 package contract.

This module intentionally has no candidate-card types. A valid package proves
only that it passed the upstream domain gates; Android still must persist it
atomically and re-check current consent/context before any notification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .contracts import (
    AudioResolution,
    InterestAssessment,
    InterestResult,
    LearningOfferAssessment,
    LearningMoment,
    LearningMomentRevision,
    LearningMomentStatus,
    OfferResult,
    SemanticAudioRequirement,
    SemanticScope,
    SemanticScopeStability,
)


class ContentPackageError(ValueError):
    """Package fields cannot prove a safe L1 eligibility chain."""


def _require_hashes(hashes: tuple[str, ...], error: str) -> None:
    if not hashes or any(len(item) != 64 for item in hashes) or len(set(hashes)) != len(hashes):
        raise ContentPackageError(error)


@dataclass(frozen=True)
class L1LearningBrief:
    brief_id: str
    l1_intervention_key: str
    learning_moment_id: str
    scope_id: str
    title: str
    summary: str
    concept_ids: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    relationship_preview_hashes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not all((self.brief_id, self.l1_intervention_key, self.learning_moment_id, self.scope_id, self.title.strip(), self.summary.strip())):
            raise ContentPackageError("l1_brief_identity_invalid")
        if not self.concept_ids or any(not item for item in self.concept_ids) or len(set(self.concept_ids)) != len(self.concept_ids):
            raise ContentPackageError("l1_brief_concepts_invalid")
        _require_hashes(self.evidence_hashes, "l1_brief_evidence_invalid")
        if self.relationship_preview_hashes:
            _require_hashes(self.relationship_preview_hashes, "l1_brief_relationship_preview_invalid")


@dataclass(frozen=True)
class ContentAnalysisPackageV2:
    schema_version: str
    message_id: str
    package_id: str
    package_revision_id: str
    package_revision: int
    replaces_revision_id: str | None
    learner_id: str
    session_id: str
    capture_consent_id: str
    consent_generation: int
    episode_id: str
    policy_bundle_hash: str
    protocol_profile_id: str
    processing_eligibility_grant_id: str
    analysis_route_lease_id: str
    route_epoch: int
    semantic_scope: SemanticScope
    learning_moment: LearningMoment
    learning_moment_revision: LearningMomentRevision
    evidence_sufficiency_profile_id: str
    runtime_semantic_risk: str
    inference_provenance_hash: str
    audio_snapshot_id: str
    audio_resolution: AudioResolution
    semantic_audio_requirement: SemanticAudioRequirement | None
    semantic_audio_decision_id: str | None
    interest_assessment: InterestAssessment
    learning_offer_assessment: LearningOfferAssessment
    l1: L1LearningBrief
    evidence_hashes: tuple[str, ...]
    created_elapsed_ns: int

    def __post_init__(self) -> None:
        if self.schema_version != "CONTENT_ANALYSIS_PACKAGE.v2.l1":
            raise ContentPackageError("content_package_schema_invalid")
        if not all((
            self.message_id,
            self.package_id,
            self.package_revision_id,
            self.learner_id,
            self.session_id,
            self.capture_consent_id,
            self.processing_eligibility_grant_id,
            self.episode_id,
            self.protocol_profile_id,
            self.analysis_route_lease_id,
            self.evidence_sufficiency_profile_id,
            self.audio_snapshot_id,
        )):
            raise ContentPackageError("content_package_identity_invalid")
        if (
            self.package_revision < 1
            or self.consent_generation < 1
            or self.route_epoch < 1
            or self.created_elapsed_ns < 0
            or len(self.policy_bundle_hash) != 64
            or len(self.inference_provenance_hash) != 64
        ):
            raise ContentPackageError("content_package_version_or_hash_invalid")
        if self.package_revision == 1 and self.replaces_revision_id is not None:
            raise ContentPackageError("initial_package_cannot_replace_revision")
        if self.package_revision > 1 and not self.replaces_revision_id:
            raise ContentPackageError("package_revision_requires_predecessor")
        scope = self.semantic_scope
        episode = scope.episode
        if (
            scope.stability is not SemanticScopeStability.STABLE
            or episode.learner_id != self.learner_id
            or episode.session_id != self.session_id
            or episode.capture_consent_id != self.capture_consent_id
            or episode.consent_generation != self.consent_generation
            or episode.episode_id != self.episode_id
        ):
            raise ContentPackageError("content_package_scope_binding_invalid")
        if self.runtime_semantic_risk != "CLEAR":
            raise ContentPackageError("content_package_runtime_risk_not_clear")
        moment = self.learning_moment
        moment_revision = self.learning_moment_revision
        if (
            moment.status not in {LearningMomentStatus.ACTIVE_DISCOVER, LearningMomentStatus.REVISED}
            or moment.episode.episode_id != self.episode_id
            or moment.episode.learner_id != self.learner_id
            or moment.episode.session_id != self.session_id
            or moment.episode.capture_consent_id != self.capture_consent_id
            or moment.episode.consent_generation != self.consent_generation
            or moment.semantic_lineage_id != scope.semantic_lineage_id
            or moment.current_revision_id != moment_revision.revision_id
            or moment_revision.moment.moment_id != moment.moment_id
            or moment_revision.anchor_scope.scope_id != scope.scope_id
            or moment_revision.anchor_scope.scope_hash != scope.scope_hash
            or moment_revision.anchor_scope.semantic_revision != scope.semantic_revision
        ):
            raise ContentPackageError("content_package_learning_moment_binding_invalid")
        interest = self.interest_assessment
        if (
            interest.result is not InterestResult.INTEREST_CONFIRMED
            or interest.learner_id != self.learner_id
            or interest.target_scope.scope_id != scope.scope_id
            or interest.target_scope.scope_hash != scope.scope_hash
            or interest.target_scope.semantic_revision != scope.semantic_revision
        ):
            raise ContentPackageError("content_package_interest_binding_invalid")
        offer = self.learning_offer_assessment
        if (
            offer.result is not OfferResult.OFFERABLE
            or offer.learner_id != self.learner_id
            or offer.episode_id != self.episode_id
            or offer.learning_moment_id != moment.moment_id
            or offer.scope_id != scope.scope_id
        ):
            raise ContentPackageError("content_package_offer_binding_invalid")
        if self.l1.scope_id != scope.scope_id or self.l1.learning_moment_id != moment.moment_id:
            raise ContentPackageError("content_package_brief_scope_invalid")
        if (
            moment_revision.interest_assessment_id != interest.assessment_id
            or moment_revision.learning_offer_assessment_id != offer.assessment_id
        ):
            raise ContentPackageError("content_package_learning_moment_assessment_invalid")
        expected_key = moment.intervention_key
        if self.l1.l1_intervention_key != expected_key:
            raise ContentPackageError("content_package_intervention_key_invalid")
        _require_hashes(self.evidence_hashes, "content_package_evidence_invalid")
        if not set(self.l1.evidence_hashes).issubset(self.evidence_hashes):
            raise ContentPackageError("content_package_brief_evidence_unbound")
        if self.audio_resolution is AudioResolution.AUDIO_REQUIRED_UNRESOLVED:
            raise ContentPackageError("content_package_audio_unresolved")
        if self.audio_resolution is AudioResolution.NO_AUDIO_TRACK_VERIFIED:
            if (
                self.semantic_audio_requirement is not SemanticAudioRequirement.AUDIO_NOT_REQUIRED_VERIFIED
                or not self.semantic_audio_decision_id
            ):
                raise ContentPackageError("content_package_audio_not_required_unproven")
        elif self.semantic_audio_requirement is not None or self.semantic_audio_decision_id is not None:
            raise ContentPackageError("verified_audio_package_cannot_claim_absence_decision")


@dataclass(frozen=True)
class PackagePersistenceReceipt:
    """Android success ACK after its one transaction; notification status is separate."""

    receipt_message_id: str
    receipt_id: str
    idempotency_key: str
    created_at: str
    learner_id: str
    session_id: str
    capture_consent_id: str
    consent_generation: int
    processing_eligibility_grant_id: str
    policy_bundle_hash: str
    protocol_profile_id: str
    package_id: str
    package_revision_id: str
    delivered_message_id: str
    delivery_lease_id: str
    package_payload_hash: str
    transaction_hash: str
    persisted_elapsed_ns: int
    disposition: str

    def __post_init__(self) -> None:
        if not all((
            self.receipt_message_id,
            self.receipt_id,
            self.idempotency_key,
            self.created_at,
            self.learner_id,
            self.session_id,
            self.capture_consent_id,
            self.processing_eligibility_grant_id,
            self.policy_bundle_hash,
            self.protocol_profile_id,
            self.package_id,
            self.package_revision_id,
            self.delivered_message_id,
            self.delivery_lease_id,
        )):
            raise ContentPackageError("package_receipt_identity_invalid")
        if self.consent_generation < 1 or self.persisted_elapsed_ns < 0:
            raise ContentPackageError("package_receipt_scope_invalid")
        if self.disposition != "PERSISTED":
            raise ContentPackageError("package_receipt_disposition_invalid")
        if any(len(value) != 64 for value in (
            self.policy_bundle_hash,
            self.package_payload_hash,
            self.transaction_hash,
        )):
            raise ContentPackageError("package_receipt_hash_or_time_invalid")
        try:
            created_at = datetime.fromisoformat(self.created_at)
        except ValueError as error:
            raise ContentPackageError("package_receipt_created_at_invalid") from error
        if created_at.tzinfo is None:
            raise ContentPackageError("package_receipt_created_at_timezone_required")
