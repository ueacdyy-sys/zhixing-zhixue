from __future__ import annotations

from dataclasses import replace
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.contracts import (  # noqa: E402
    ContentEpisode,
    EpisodeStatus,
    LearningMoment,
    LearningMomentRevision,
    LearningMomentStatus,
    SemanticCompleteness,
    SemanticScope,
    SemanticScopeStability,
    SourceKind,
)
from realtime_runtime.learning_moment_ledger import (  # noqa: E402
    LearningMomentLedger,
    LearningMomentLedgerError,
    ReservationState,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


class LearningMomentLedgerTests(unittest.TestCase):
    def scope(self, *, episode_id: str = "episode-1", lineage: str = "lineage-1") -> SemanticScope:
        return SemanticScope(
            scope_id=f"scope-{episode_id}-{lineage}",
            episode=ContentEpisode(
                episode_id=episode_id, learner_id="learner-1", session_id="session-1",
                capture_consent_id="consent-1", consent_generation=1, source_kind=SourceKind.PHONE_SCREEN,
                start_pts_ns=0, continuity_start_pts_ns=0, end_pts_ns=None, status=EpisodeStatus.OPEN,
                boundary_confidence=0.9, boundary_reason="continuous", resolver_version="boundary.v2", policy_version="policy.v1",
            ),
            start_pts_ns=0, end_pts_ns=100, scope_hash=HASH_A, semantic_lineage_id=lineage,
            completeness=SemanticCompleteness.WINDOW_COMPLETE, stability=SemanticScopeStability.STABLE,
            semantic_revision=1, event_time_watermark_ns=100,
        )

    def moment(
        self,
        *,
        moment_id: str = "moment-1",
        revision_id: str = "moment-revision-1",
        episode_id: str = "episode-1",
        lineage: str = "lineage-1",
        anchor: str = "anchor-1",
        status: LearningMomentStatus = LearningMomentStatus.ACTIVE_DISCOVER,
    ) -> LearningMoment:
        scope = self.scope(episode_id=episode_id, lineage=lineage)
        return LearningMoment(
            moment_id=moment_id, episode=scope.episode, semantic_lineage_id=lineage,
            learning_anchor_id=anchor, intervention_key=f"l1:learner-1:{moment_id}:NORMAL",
            current_revision_id=revision_id, status=status, created_elapsed_ns=10, policy_version="moment.v1",
        )

    def revision(self, moment: LearningMoment, *, revision: int = 1, replaces: str | None = None) -> LearningMomentRevision:
        return LearningMomentRevision(
            revision_id=moment.current_revision_id, moment=moment, revision=revision,
            replaces_revision_id=replaces, anchor_scope=self.scope(
                episode_id=moment.episode.episode_id, lineage=moment.semantic_lineage_id,
            ),
            interest_assessment_id=f"interest-{revision}", learning_offer_assessment_id=f"offer-{revision}",
            evidence_hashes=(HASH_A, HASH_B), revision_reason="INITIAL" if revision == 1 else "SCOPE_REVISED",
            created_elapsed_ns=20 + revision,
        )

    def test_claim_is_stable_for_same_episode_lineage_and_anchor(self) -> None:
        first = self.moment()
        duplicate = self.moment(moment_id="moment-retry", revision_id="retry-revision")
        with tempfile.TemporaryDirectory() as temp_dir, LearningMomentLedger(Path(temp_dir) / "moments.sqlite") as ledger:
            claimed = ledger.claim(first)
            self.assertTrue(claimed.created)
            self.assertEqual("moment-1", claimed.moment_id)
            self.assertTrue(ledger.record_revision(self.revision(first)))

            retry = ledger.claim(duplicate)
            self.assertFalse(retry.created)
            self.assertEqual("moment-1", retry.moment_id)
            self.assertEqual("l1:learner-1:moment-1:NORMAL", retry.intervention_key)
            self.assertEqual("moment-revision-1", retry.current_revision_id)

    def test_revision_chain_is_immutable_and_updates_current_revision_only_with_predecessor(self) -> None:
        first = self.moment()
        second = replace(first, current_revision_id="moment-revision-2", status=LearningMomentStatus.REVISED)
        with tempfile.TemporaryDirectory() as temp_dir, LearningMomentLedger(Path(temp_dir) / "moments.sqlite") as ledger:
            ledger.claim(first)
            self.assertTrue(ledger.record_revision(self.revision(first)))
            second_revision = self.revision(second, revision=2, replaces="moment-revision-1")
            self.assertTrue(ledger.record_revision(second_revision))
            self.assertFalse(ledger.record_revision(second_revision))
            with self.assertRaisesRegex(LearningMomentLedgerError, "moment_revision_predecessor_mismatch"):
                ledger.record_revision(
                    self.revision(replace(second, current_revision_id="moment-revision-3"), revision=3, replaces="missing")
                )

    def test_normal_slot_is_not_reopened_by_revisions_and_second_slot_requires_policy_facts(self) -> None:
        first = self.moment()
        second = self.moment(moment_id="moment-2", revision_id="moment-revision-2", lineage="lineage-2", anchor="anchor-2")
        with tempfile.TemporaryDirectory() as temp_dir, LearningMomentLedger(Path(temp_dir) / "moments.sqlite") as ledger:
            for moment in (first, second):
                ledger.claim(moment)
                ledger.record_revision(self.revision(moment))
            self.assertEqual(ReservationState.RESERVED, ledger.reserve_normal_slot(first, now_elapsed_ns=30))
            self.assertEqual(ReservationState.ALREADY_RESERVED, ledger.reserve_normal_slot(first, now_elapsed_ns=31))
            self.assertEqual(ReservationState.BUDGET_EXHAUSTED, ledger.reserve_normal_slot(second, now_elapsed_ns=32))
            with self.assertRaisesRegex(LearningMomentLedgerError, "second_slot_policy_evidence_required"):
                ledger.reserve_second_slot(second, now_elapsed_ns=33, substantial_anchor_evidence_hash=None, student_subscription_attestation_id=None)
            self.assertEqual(
                ReservationState.RESERVED,
                ledger.reserve_second_slot(
                    second, now_elapsed_ns=34, substantial_anchor_evidence_hash=HASH_A,
                    student_subscription_attestation_id="subscription-1",
                ),
            )
            revised_first = replace(first, current_revision_id="moment-revision-3", status=LearningMomentStatus.REVISED)
            self.assertTrue(ledger.record_revision(self.revision(revised_first, revision=2, replaces="moment-revision-1")))
            self.assertEqual(ReservationState.ALREADY_RESERVED, ledger.reserve_normal_slot(revised_first, now_elapsed_ns=35))

    def test_correction_has_a_separate_one_time_budget_and_requires_a_seen_brief(self) -> None:
        first = self.moment()
        revised = replace(first, current_revision_id="moment-revision-2", status=LearningMomentStatus.REVISED)
        with tempfile.TemporaryDirectory() as temp_dir, LearningMomentLedger(Path(temp_dir) / "moments.sqlite") as ledger:
            ledger.claim(first)
            ledger.record_revision(self.revision(first))
            ledger.record_revision(self.revision(revised, revision=2, replaces="moment-revision-1"))
            with self.assertRaisesRegex(LearningMomentLedgerError, "correction_policy_evidence_required"):
                ledger.reserve_correction_slot(
                    revised, correction_revision_id="moment-revision-2", now_elapsed_ns=40,
                    presented_brief_id=None, substantive_error_evidence_hash=None,
                )
            self.assertEqual(
                ReservationState.RESERVED,
                ledger.reserve_correction_slot(
                    revised, correction_revision_id="moment-revision-2", now_elapsed_ns=41,
                    presented_brief_id="brief-1", substantive_error_evidence_hash=HASH_B,
                ),
            )
            self.assertEqual(
                ReservationState.ALREADY_RESERVED,
                ledger.reserve_correction_slot(
                    revised, correction_revision_id="moment-revision-2", now_elapsed_ns=42,
                    presented_brief_id="brief-1", substantive_error_evidence_hash=HASH_B,
                ),
            )


if __name__ == "__main__":
    unittest.main()
