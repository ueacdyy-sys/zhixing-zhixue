from __future__ import annotations

from dataclasses import replace
import sys
import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.content_package import ContentAnalysisPackageV2, ContentPackageError, L1LearningBrief  # noqa: E402
from realtime_runtime.content_package import PackagePersistenceReceipt  # noqa: E402
from realtime_runtime.package_outbox import PackageOutbox, PackageOutboxError  # noqa: E402
from realtime_runtime.learning_moment_ledger import LearningMomentLedger, LearningMomentLedgerError  # noqa: E402
from realtime_runtime.contracts import (  # noqa: E402
    AudioResolution,
    BehaviorEvent,
    BehaviorOrigin,
    BehaviorScopeRelation,
    ContentEpisode,
    EpisodeAttributionState,
    EpisodeStatus,
    InterestAssessment,
    InterestResult,
    LearningOfferAssessment,
    LearningMoment,
    LearningMomentRevision,
    LearningMomentStatus,
    ObservationTier,
    OfferResult,
    ProgressEvidenceKind,
    SemanticAudioRequirement,
    SemanticCompleteness,
    SemanticScope,
    SemanticScopeStability,
    SourceKind,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


class ContentAnalysisPackageTests(unittest.TestCase):
    @staticmethod
    def scope() -> SemanticScope:
        return SemanticScope(
            scope_id="scope-1",
            episode=ContentEpisode(
                episode_id="episode-1", learner_id="learner-1", session_id="session-1",
                capture_consent_id="consent-1", consent_generation=1, source_kind=SourceKind.PHONE_SCREEN,
                start_pts_ns=0, continuity_start_pts_ns=0, end_pts_ns=None, status=EpisodeStatus.OPEN,
                boundary_confidence=0.9, boundary_reason="continuous", resolver_version="boundary.v2", policy_version="scope.v1",
            ),
            start_pts_ns=0, end_pts_ns=100, scope_hash=HASH_A, semantic_lineage_id="lineage-1",
            completeness=SemanticCompleteness.WINDOW_COMPLETE, stability=SemanticScopeStability.STABLE,
            semantic_revision=1, event_time_watermark_ns=100,
        )

    def interest(self) -> InterestAssessment:
        scope = self.scope()
        events = tuple(
            BehaviorEvent(
                event_id=f"event-{index}", learner_id="learner-1", episode_id="episode-1",
                attribution_state=EpisodeAttributionState.RESOLVED, session_id="session-1", capture_consent_id="consent-1",
                source_kind=SourceKind.PHONE_SCREEN, observed_scope_id="scope-1", scope_relation=BehaviorScopeRelation.SAME_SCOPE,
                origin=BehaviorOrigin.STUDENT_EXPLICIT, observation_tier=ObservationTier.SCREEN_INFERRED,
                progress_kind=ProgressEvidenceKind.WEAK_ATTENTION_SIGNAL, attribution_confidence=0.9,
                evidence_start_pts_ns=10 + index, evidence_end_pts_ns=20 + index, observed_elapsed_ns=100,
                expires_elapsed_ns=300, observation_adapter_id="observer.v1", observation_adapter_version="1",
                action_attestation_id=f"attestation-{index}", progress_evidence_id=None, semantic_lineage_id="lineage-1",
                foreground_snapshot_id="foreground-1", consent_generation=1, foreground_valid=True, evidence_hashes=(HASH_A,),
            )
            for index in (1, 2)
        )
        return InterestAssessment(
            assessment_id="interest-1", learner_id="learner-1", target_scope=scope, result=InterestResult.INTEREST_CONFIRMED,
            policy_version="interest.v1", evidence_profile_id="profile.video.v1", decision_trace_hash=HASH_A,
            evaluated_elapsed_ns=150, minimum_independent_events=2, continuous_context_max_gap_ns=10, evidence_events=events,
        )

    def moment(self) -> LearningMoment:
        scope = self.scope()
        return LearningMoment(
            moment_id="moment-1", episode=scope.episode, semantic_lineage_id="lineage-1",
            learning_anchor_id="concept-1", intervention_key="l1:learner-1:moment-1:NORMAL",
            current_revision_id="moment-revision-1", status=LearningMomentStatus.ACTIVE_DISCOVER,
            created_elapsed_ns=400, policy_version="moment.v1",
        )

    def moment_revision(self) -> LearningMomentRevision:
        return LearningMomentRevision(
            revision_id="moment-revision-1", moment=self.moment(), revision=1,
            replaces_revision_id=None, anchor_scope=self.scope(), interest_assessment_id="interest-1",
            learning_offer_assessment_id="offer-1", evidence_hashes=(HASH_A, HASH_B),
            revision_reason="INITIAL_L1", created_elapsed_ns=500,
        )

    def package(self, **overrides: object) -> ContentAnalysisPackageV2:
        interest = self.interest()
        scope = interest.target_scope
        brief = L1LearningBrief(
            brief_id="brief-1", l1_intervention_key="l1:learner-1:moment-1:NORMAL", learning_moment_id="moment-1", scope_id="scope-1",
            title="概念解释", summary="这是当前稳定窗口的可追溯解释。", concept_ids=("concept-1",),
            evidence_hashes=(HASH_A,), relationship_preview_hashes=(HASH_B,),
        )
        values: dict[str, object] = {
            "schema_version": "CONTENT_ANALYSIS_PACKAGE.v2.l1", "message_id": "message-1", "package_id": "package-1",
            "package_revision_id": "revision-1", "package_revision": 1, "replaces_revision_id": None,
            "learner_id": "learner-1", "session_id": "session-1", "capture_consent_id": "consent-1", "consent_generation": 1,
            "episode_id": "episode-1", "policy_bundle_hash": HASH_A, "protocol_profile_id": "protocol.v2",
            "processing_eligibility_grant_id": "grant-1", "analysis_route_lease_id": "route-1", "route_epoch": 1,
            "semantic_scope": scope, "evidence_sufficiency_profile_id": "profile.video.v1", "runtime_semantic_risk": "CLEAR",
            "learning_moment": self.moment(), "learning_moment_revision": self.moment_revision(),
            "inference_provenance_hash": HASH_B, "audio_snapshot_id": "audio-1", "audio_resolution": AudioResolution.SAME_SOURCE_VERIFIED,
            "semantic_audio_requirement": None, "semantic_audio_decision_id": None, "interest_assessment": interest,
            "learning_offer_assessment": LearningOfferAssessment(
                assessment_id="offer-1", learner_id="learner-1", episode_id="episode-1", scope_id="scope-1",
                learning_moment_id="moment-1",
                result=OfferResult.OFFERABLE, explanation_object="concept", policy_version="offer.v1",
            ),
            "l1": brief, "evidence_hashes": (HASH_A, HASH_B), "created_elapsed_ns": 500,
        }
        values.update(overrides)
        return ContentAnalysisPackageV2(**values)  # type: ignore[arg-type]

    def test_only_complete_bound_domain_chain_can_create_l1_package(self) -> None:
        package = self.package()
        self.assertEqual("brief-1", package.l1.brief_id)
        self.assertEqual("CONTENT_ANALYSIS_PACKAGE.v2.l1", package.schema_version)

    def test_l1_rejects_candidate_style_or_unbound_interest_and_evidence(self) -> None:
        with self.assertRaisesRegex(ContentPackageError, "content_package_schema_invalid"):
            self.package(schema_version="candidate_card.v1")
        with self.assertRaisesRegex(ContentPackageError, "content_package_intervention_key_invalid"):
            self.package(l1=replace(self.package().l1, l1_intervention_key="visit:window"))
        with self.assertRaisesRegex(ContentPackageError, "content_package_learning_moment_binding_invalid"):
            self.package(learning_moment=replace(self.moment(), semantic_lineage_id="other-lineage"))
        with self.assertRaisesRegex(ContentPackageError, "content_package_learning_moment_assessment_invalid"):
            self.package(learning_moment_revision=replace(self.moment_revision(), interest_assessment_id="interest-other"))
        with self.assertRaisesRegex(ContentPackageError, "content_package_brief_evidence_unbound"):
            self.package(evidence_hashes=(HASH_B,))
        with self.assertRaisesRegex(ContentPackageError, "content_package_interest_binding_invalid"):
            self.package(interest_assessment=replace(self.interest(), result=InterestResult.NOT_READY))
        with self.assertRaisesRegex(ContentPackageError, "content_package_identity_invalid"):
            self.package(processing_eligibility_grant_id="")

    def test_audio_failure_or_unproven_silent_scope_cannot_package_l1(self) -> None:
        with self.assertRaisesRegex(ContentPackageError, "content_package_audio_unresolved"):
            self.package(audio_resolution=AudioResolution.AUDIO_REQUIRED_UNRESOLVED)
        with self.assertRaisesRegex(ContentPackageError, "content_package_audio_not_required_unproven"):
            self.package(audio_resolution=AudioResolution.NO_AUDIO_TRACK_VERIFIED)
        self.assertEqual(
            SemanticAudioRequirement.AUDIO_NOT_REQUIRED_VERIFIED,
            self.package(
                audio_resolution=AudioResolution.NO_AUDIO_TRACK_VERIFIED,
                semantic_audio_requirement=SemanticAudioRequirement.AUDIO_NOT_REQUIRED_VERIFIED,
                semantic_audio_decision_id="audio-decision-1",
            ).semantic_audio_requirement,
        )

    def test_pc_outbox_is_revision_idempotent_and_only_receipt_acks(self) -> None:
        package = self.package()
        with tempfile.TemporaryDirectory() as temp_dir, LearningMomentLedger(Path(temp_dir) / "moments.sqlite") as moments:
            with self.assertRaisesRegex(LearningMomentLedgerError, "content_package_moment_unregistered"):
                moments.assert_package_registered(package)
            moments.claim(package.learning_moment)
            moments.record_revision(package.learning_moment_revision)
            with PackageOutbox(Path(temp_dir) / "outbox.sqlite", learning_moment_ledger=moments) as outbox:
                self.assertTrue(outbox.enqueue(package))
                self.assertFalse(outbox.enqueue(package))
                with self.assertRaisesRegex(PackageOutboxError, "package_revision_payload_conflict"):
                    outbox.enqueue(replace(package, l1=replace(package.l1, summary="different but same revision")))
                lease = outbox.claim(lease_id="delivery-1", now_elapsed_ns=100, lease_duration_ns=50)
                self.assertIsNotNone(lease)
                assert lease is not None
                self.assertEqual("message-1", lease.message_id)
                receipt = PackagePersistenceReceipt(
                    receipt_message_id="receipt-message-1", receipt_id="receipt-1", idempotency_key="receipt-idempotency-1",
                    created_at="2026-07-30T12:00:00+08:00", learner_id="learner-1", session_id="session-1",
                    capture_consent_id="consent-1", consent_generation=1, processing_eligibility_grant_id="grant-1",
                    policy_bundle_hash=HASH_A, protocol_profile_id="protocol.v2", package_id="package-1",
                    package_revision_id="revision-1", delivered_message_id="message-1", delivery_lease_id="delivery-1",
                    package_payload_hash=lease.payload_hash, transaction_hash=HASH_A, persisted_elapsed_ns=101,
                    disposition="PERSISTED",
                )
                with self.assertRaisesRegex(PackageOutboxError, "package_ack_lease_or_scope_denied"):
                    outbox.acknowledge(
                        receipt,
                        lease_id="delivery-other", now_elapsed_ns=101,
                    )
                self.assertTrue(outbox.acknowledge(receipt, lease_id="delivery-1", now_elapsed_ns=101))
                self.assertFalse(outbox.acknowledge(receipt, lease_id="delivery-1", now_elapsed_ns=101))
                conflicting_idempotency_key = replace(
                    receipt,
                    receipt_message_id="receipt-message-conflict",
                    receipt_id="receipt-conflict",
                    transaction_hash=HASH_B,
                )
                with self.assertRaisesRegex(PackageOutboxError, "package_receipt_idempotency_conflict"):
                    outbox.acknowledge(conflicting_idempotency_key, lease_id="delivery-1", now_elapsed_ns=101)
                self.assertIsNone(outbox.claim(lease_id="delivery-2", now_elapsed_ns=102, lease_duration_ns=50))

    def test_package_outbox_rejects_an_ack_at_the_exact_lease_deadline(self) -> None:
        package = self.package()
        with tempfile.TemporaryDirectory() as temp_dir, LearningMomentLedger(Path(temp_dir) / "moments.sqlite") as moments:
            moments.claim(package.learning_moment)
            moments.record_revision(package.learning_moment_revision)
            with PackageOutbox(Path(temp_dir) / "outbox.sqlite", learning_moment_ledger=moments) as outbox:
                outbox.enqueue(package)
                lease = outbox.claim(lease_id="delivery-1", now_elapsed_ns=100, lease_duration_ns=50)
                assert lease is not None
                receipt = PackagePersistenceReceipt(
                    receipt_message_id="receipt-message-expired", receipt_id="receipt-expired", idempotency_key="receipt-expired-key",
                    created_at="2026-07-30T12:00:00+08:00", learner_id="learner-1", session_id="session-1",
                    capture_consent_id="consent-1", consent_generation=1, processing_eligibility_grant_id="grant-1",
                    policy_bundle_hash=HASH_A, protocol_profile_id="protocol.v2", package_id="package-1",
                    package_revision_id="revision-1", delivered_message_id="message-1", delivery_lease_id="delivery-1",
                    package_payload_hash=lease.payload_hash, transaction_hash=HASH_A, persisted_elapsed_ns=150,
                    disposition="PERSISTED",
                )
                with self.assertRaisesRegex(PackageOutboxError, "package_ack_lease_or_scope_denied"):
                    outbox.acknowledge(receipt, lease_id="delivery-1", now_elapsed_ns=150)

    def test_pre_release_outbox_database_is_upgraded_before_new_receipt_write(self) -> None:
        package = self.package()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "outbox.sqlite"
            with closing(sqlite3.connect(path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE content_package_outbox (
                        package_id TEXT NOT NULL, package_revision_id TEXT NOT NULL,
                        learner_id TEXT NOT NULL, message_id TEXT NOT NULL UNIQUE,
                        payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                        state TEXT NOT NULL, lease_id TEXT, lease_deadline_elapsed_ns INTEGER,
                        ack_receipt_id TEXT, PRIMARY KEY(package_id, package_revision_id)
                    );
                    CREATE TABLE package_persistence_receipts (
                        receipt_id TEXT PRIMARY KEY, package_id TEXT NOT NULL,
                        package_revision_id TEXT NOT NULL, learner_id TEXT NOT NULL,
                        message_id TEXT NOT NULL, receipt_hash TEXT NOT NULL UNIQUE,
                        transaction_hash TEXT NOT NULL, persisted_elapsed_ns INTEGER NOT NULL
                    );
                    """
                )
            with LearningMomentLedger(Path(temp_dir) / "moments.sqlite") as moments:
                moments.claim(package.learning_moment)
                moments.record_revision(package.learning_moment_revision)
                with PackageOutbox(path, learning_moment_ledger=moments) as outbox:
                    self.assertTrue(outbox.enqueue(package))


if __name__ == "__main__":
    unittest.main()
