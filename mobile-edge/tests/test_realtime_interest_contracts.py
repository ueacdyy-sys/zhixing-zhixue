from __future__ import annotations

from dataclasses import replace
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.contracts import (  # noqa: E402
    BehaviorEvent,
    BehaviorOrigin,
    BehaviorScopeRelation,
    ContractError,
    ContentEpisode,
    EpisodeAttributionState,
    EpisodeStatus,
    InterestAssessment,
    InterestResult,
    InterruptionFeedback,
    InterruptionFeedbackKind,
    LearningOfferAssessment,
    ObservationTier,
    OfferResult,
    ProgressEvidenceKind,
    SemanticCompleteness,
    SemanticScope,
    SemanticScopeStability,
    SourceKind,
)


HASH_A = "a" * 64


def student_event(
    *,
    event_id: str = "event-1",
    episode_id: str | None = "episode-1",
    attribution_state: EpisodeAttributionState = EpisodeAttributionState.RESOLVED,
    progress_kind: ProgressEvidenceKind = ProgressEvidenceKind.WEAK_ATTENTION_SIGNAL,
    observation_tier: ObservationTier | None = None,
    origin: BehaviorOrigin = BehaviorOrigin.STUDENT_EXPLICIT,
    foreground_valid: bool = True,
    consent_generation: int = 1,
    observed_scope_id: str | None = "scope-1",
    scope_relation: BehaviorScopeRelation = BehaviorScopeRelation.SAME_SCOPE,
    evidence_start_pts_ns: int = 140,
    evidence_end_pts_ns: int = 160,
    observed_elapsed_ns: int = 100,
    expires_elapsed_ns: int = 200,
    action_attestation_id: str | None = None,
    semantic_lineage_id: str | None = "lineage-1",
) -> BehaviorEvent:
    return BehaviorEvent(
        event_id=event_id,
        learner_id="learner-1",
        episode_id=episode_id,
        attribution_state=attribution_state,
        session_id="session-1",
        capture_consent_id="consent-1",
        source_kind=SourceKind.PHONE_SCREEN,
        observed_scope_id=observed_scope_id,
        scope_relation=scope_relation,
        origin=origin,
        observation_tier=observation_tier or (
            ObservationTier.VERIFIED_PLAYER
            if progress_kind is ProgressEvidenceKind.DIRECT_PROGRESS_OBSERVED
            else ObservationTier.SCREEN_INFERRED
        ),
        progress_kind=progress_kind,
        attribution_confidence=0.9,
        evidence_start_pts_ns=evidence_start_pts_ns,
        evidence_end_pts_ns=evidence_end_pts_ns,
        observed_elapsed_ns=observed_elapsed_ns,
        expires_elapsed_ns=expires_elapsed_ns,
        observation_adapter_id="screen-observer.v1" if origin in {BehaviorOrigin.STUDENT_EXPLICIT, BehaviorOrigin.ANALYSIS_OBSERVED} else None,
        observation_adapter_version="1.0.0" if origin in {BehaviorOrigin.STUDENT_EXPLICIT, BehaviorOrigin.ANALYSIS_OBSERVED} else None,
        action_attestation_id=action_attestation_id or (f"action-{event_id}" if origin is BehaviorOrigin.STUDENT_EXPLICIT else None),
        progress_evidence_id="player-progress-proof" if progress_kind is ProgressEvidenceKind.DIRECT_PROGRESS_OBSERVED else None,
        semantic_lineage_id=semantic_lineage_id,
        foreground_snapshot_id="foreground-1" if origin in {BehaviorOrigin.STUDENT_EXPLICIT, BehaviorOrigin.ANALYSIS_OBSERVED} else None,
        consent_generation=consent_generation,
        foreground_valid=foreground_valid,
        evidence_hashes=(HASH_A,),
        observation_id=(f"observation-{event_id}" if origin is BehaviorOrigin.ANALYSIS_OBSERVED else None),
    )


class RealtimeInterestContractTests(unittest.TestCase):
    @staticmethod
    def stable_scope() -> SemanticScope:
        return SemanticScope(
            scope_id="scope-1",
            episode=ContentEpisode(
                episode_id="episode-1",
                learner_id="learner-1",
                session_id="session-1",
                capture_consent_id="consent-1",
                consent_generation=1,
                source_kind=SourceKind.PHONE_SCREEN,
                start_pts_ns=100,
                continuity_start_pts_ns=100,
                end_pts_ns=None,
                status=EpisodeStatus.OPEN,
                boundary_confidence=0.9,
                boundary_reason="CONTENT_CONTINUOUS",
                resolver_version="resolver.v2",
                policy_version="policy.v1",
            ),
            start_pts_ns=100,
            end_pts_ns=180,
            scope_hash=HASH_A,
            semantic_lineage_id="lineage-1",
            completeness=SemanticCompleteness.WINDOW_COMPLETE,
            stability=SemanticScopeStability.STABLE,
            semantic_revision=1,
            event_time_watermark_ns=180,
        )

    def assessment(self, *events: BehaviorEvent, **overrides: object) -> InterestAssessment:
        values: dict[str, object] = {
            "assessment_id": "interest-1",
            "learner_id": "learner-1",
            "target_scope": self.stable_scope(),
            "result": InterestResult.INTEREST_CONFIRMED,
            "policy_version": "interest.v3",
            "evidence_profile_id": "profile.video.v2",
            "decision_trace_hash": HASH_A,
            "evaluated_elapsed_ns": 150,
            "minimum_independent_events": 2,
            "continuous_context_max_gap_ns": 60,
            "evidence_events": events,
        }
        values.update(overrides)
        return InterestAssessment(**values)

    def test_system_delivery_and_restore_cannot_confirm_interest(self) -> None:
        for origin in (BehaviorOrigin.ANDROID_OBSERVED, BehaviorOrigin.SYSTEM_DELIVERY, BehaviorOrigin.SYSTEM_RESTORE):
            with self.subTest(origin=origin), self.assertRaisesRegex(ContractError, "interest_event_origin_invalid"):
                self.assessment(student_event(event_id="direct", origin=origin), student_event(event_id="weak"))

    def test_one_weak_or_unknown_signal_cannot_confirm_interest(self) -> None:
        for kind in (ProgressEvidenceKind.WEAK_ATTENTION_SIGNAL, ProgressEvidenceKind.UNKNOWN):
            with self.subTest(kind=kind), self.assertRaisesRegex(ContractError, "interest_evidence_insufficient"):
                self.assessment(student_event(progress_kind=kind))

    def test_two_independent_analysis_observations_can_confirm_without_fabricating_a_student_tap(self) -> None:
        observed = (
            student_event(event_id="observed-1", origin=BehaviorOrigin.ANALYSIS_OBSERVED),
            student_event(event_id="observed-2", origin=BehaviorOrigin.ANALYSIS_OBSERVED),
        )
        assessment = self.assessment(*observed)
        self.assertEqual(InterestResult.INTEREST_CONFIRMED, assessment.result)
        with self.assertRaisesRegex(ContractError, "interest_evidence_not_independent"):
            self.assessment(
                observed[0],
                replace(observed[1], observation_id=observed[0].observation_id),
            )
        with self.assertRaisesRegex(ContractError, "analysis_observed_requires_replayable_observation"):
            replace(observed[0], observation_id=None)
        with self.assertRaisesRegex(ContractError, "interest_single_weak_signal"):
            self.assessment(observed[0], minimum_independent_events=1)

    def test_confirmed_interest_rejects_cross_session_source_consent_or_unknown_attribution(self) -> None:
        invalid_events = (
            replace(student_event(event_id="session"), session_id="session-other"),
            replace(student_event(event_id="source"), source_kind=SourceKind.GLASSES_FIRST_PERSON),
            replace(student_event(event_id="consent"), capture_consent_id="consent-other"),
            student_event(event_id="unknown", episode_id=None, attribution_state=EpisodeAttributionState.UNKNOWN, observed_scope_id=None, scope_relation=BehaviorScopeRelation.UNKNOWN, semantic_lineage_id=None),
        )
        for event in invalid_events:
            with self.subTest(event=event), self.assertRaisesRegex(ContractError, "interest_event_binding_invalid"):
                self.assessment(student_event(event_id="weak-1"), event)

    def test_same_scope_rejects_out_of_scope_pts(self) -> None:
        with self.assertRaisesRegex(ContractError, "interest_event_not_in_target_scope"):
            self.assessment(student_event(event_id="inside"), student_event(event_id="outside", evidence_start_pts_ns=181, evidence_end_pts_ns=190))

    def test_continuous_same_episode_allows_only_bounded_lineage_preserving_successor(self) -> None:
        assessment = self.assessment(
            student_event(event_id="within"),
            student_event(event_id="next", observed_scope_id="scope-2", scope_relation=BehaviorScopeRelation.CONTINUOUS_SAME_EPISODE, evidence_start_pts_ns=190, evidence_end_pts_ns=200),
        )
        self.assertEqual(InterestResult.INTEREST_CONFIRMED, assessment.result)
        with self.assertRaisesRegex(ContractError, "interest_event_continuity_window_invalid"):
            self.assessment(student_event(event_id="within"), student_event(event_id="stale", observed_scope_id="scope-2", scope_relation=BehaviorScopeRelation.CONTINUOUS_SAME_EPISODE, evidence_start_pts_ns=241, evidence_end_pts_ns=250))

    def test_replayed_or_non_attested_events_cannot_count_as_independent_interest_evidence(self) -> None:
        event = student_event()
        with self.assertRaisesRegex(ContractError, "interest_evidence_not_independent"):
            self.assessment(event, event)
        with self.assertRaisesRegex(ContractError, "interest_evidence_not_independent"):
            self.assessment(student_event(event_id="a", action_attestation_id="same-action"), student_event(event_id="b", action_attestation_id="same-action"))
        with self.assertRaisesRegex(ContractError, "student_explicit_requires_attestation"):
            replace(student_event(), action_attestation_id=None)

    def test_direct_progress_requires_verified_timeline_evidence(self) -> None:
        event = student_event(progress_kind=ProgressEvidenceKind.DIRECT_PROGRESS_OBSERVED)
        with self.assertRaisesRegex(ContractError, "direct_progress_requires_timeline_evidence"):
            replace(event, progress_evidence_id=None)

    def test_interest_and_learning_offer_are_independent_assessments(self) -> None:
        interest = self.assessment(student_event(event_id="direct", progress_kind=ProgressEvidenceKind.DIRECT_PROGRESS_OBSERVED), minimum_independent_events=1)
        offer = LearningOfferAssessment(
            assessment_id="offer-1",
            learner_id="learner-1",
            episode_id="episode-1",
            learning_moment_id="moment-1",
            scope_id="scope-1",
            result=OfferResult.NOT_OFFERABLE,
            explanation_object="营销话术",
            policy_version="offer.v2",
        )
        self.assertEqual(InterestResult.INTEREST_CONFIRMED, interest.result)
        self.assertEqual(OfferResult.NOT_OFFERABLE, offer.result)

    def test_system_or_oem_block_is_not_user_negative_feedback(self) -> None:
        feedback = InterruptionFeedback(
            feedback_id="feedback-1",
            learner_id="learner-1",
            kind=InterruptionFeedbackKind.SYSTEM_BLOCKED,
            scope="episode-1",
        )
        self.assertFalse(feedback.suppresses_future_notifications)


if __name__ == "__main__":
    unittest.main()
