from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.contracts import (  # noqa: E402
    ContentEpisode,
    EpisodeStatus,
    LateFactAdmission,
    LateFactDisposition,
    L0HeartbeatState,
    L0SemanticHeartbeat,
    RealtimeSemanticFact,
    SemanticCompleteness,
    SemanticScope,
    SemanticScopeStability,
    SourceKind,
)
from realtime_runtime.semantic_ledger import RealtimeSemanticLedger, SemanticLedgerError  # noqa: E402


HASH_A = "a" * 64
HASH_B = "b" * 64


class RealtimeSemanticLedgerTests(unittest.TestCase):
    def episode(self) -> ContentEpisode:
        return ContentEpisode(
            episode_id="episode-1",
            learner_id="learner-1",
            session_id="session-1",
            capture_consent_id="consent-1",
            consent_generation=1,
            source_kind=SourceKind.PHONE_SCREEN,
            start_pts_ns=0,
            continuity_start_pts_ns=0,
            end_pts_ns=None,
            status=EpisodeStatus.OPEN,
            boundary_confidence=1.0,
            boundary_reason="initial",
            resolver_version="boundary.v2",
            policy_version="semantic.v2",
        )

    def fact(self, fact_id: str, start: int, end: int, **overrides: object) -> RealtimeSemanticFact:
        fields: dict[str, object] = {
            "fact_id": fact_id,
            "idempotency_key": f"idem-{fact_id}",
            "learner_id": "learner-1",
            "session_id": "session-1",
            "episode_id": "episode-1",
            "capture_consent_id": "consent-1",
            "consent_generation": 1,
            "source_kind": SourceKind.PHONE_SCREEN,
            "start_pts_ns": start,
            "end_pts_ns": end,
            "fact_kind": "semantic_increment",
            "content_hash": HASH_A,
            "evidence_hashes": (HASH_A,),
            "semantic_policy_version": "semantic.v2",
            "provenance_hash": HASH_B,
        }
        fields.update(overrides)
        return RealtimeSemanticFact(**fields)  # type: ignore[arg-type]

    def scope(self, **overrides: object) -> SemanticScope:
        fields: dict[str, object] = {
            "scope_id": "scope-1",
            "episode": self.episode(),
            "start_pts_ns": 0,
            "end_pts_ns": 100,
            "scope_hash": HASH_A,
            "semantic_lineage_id": "lineage-1",
            "completeness": SemanticCompleteness.WINDOW_COMPLETE,
            "stability": SemanticScopeStability.STABLE,
            "semantic_revision": 1,
            "event_time_watermark_ns": 100,
        }
        fields.update(overrides)
        return SemanticScope(**fields)  # type: ignore[arg-type]

    def late_admission(self, **overrides: object) -> LateFactAdmission:
        fields: dict[str, object] = {
            "fact_id": "late-1",
            "learner_id": "learner-1",
            "session_id": "session-1",
            "episode_id": "episode-1",
            "capture_consent_id": "consent-1",
            "consent_generation": 1,
            "source_kind": SourceKind.PHONE_SCREEN,
            "scope_id": "scope-1",
            "scope_hash": HASH_A,
            "base_scope_revision": 1,
            "fact_start_pts_ns": 20,
            "fact_end_pts_ns": 40,
            "event_time_watermark_ns": 100,
            "arrived_elapsed_ns": 200,
            "evidence_hashes": (HASH_A,),
            "fact_content_hash": HASH_A,
            "admission_idempotency_key": "admission-1",
            "allowed_lateness_ns": 80,
            "late_policy_id": "late.v1",
            "presentation_revision_ref": None,
            "disposition": LateFactDisposition.REASSESS_UNPRESENTED,
        }
        fields.update(overrides)
        return LateFactAdmission(**fields)  # type: ignore[arg-type]

    def test_contiguous_facts_produce_durable_watermark_and_idempotent_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, RealtimeSemanticLedger(Path(temp_dir) / "ledger.sqlite") as ledger:
            self.assertTrue(ledger.append_fact(self.fact("fact-1", 0, 50)))
            self.assertTrue(ledger.append_fact(self.fact("fact-2", 50, 100)))
            self.assertFalse(ledger.append_fact(self.fact("fact-2", 50, 100)))
            self.assertEqual(100, ledger.contiguous_watermark(episode_id="episode-1", continuity_start_pts_ns=0))
            self.assertTrue(ledger.record_scope(self.scope()))
            self.assertFalse(ledger.record_scope(self.scope()))
            with self.assertRaisesRegex(SemanticLedgerError, "semantic_fact_idempotency_conflict"):
                ledger.append_fact(self.fact("fact-2", 50, 101))

    def test_gap_stops_watermark_and_rejects_cross_gap_stable_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, RealtimeSemanticLedger(Path(temp_dir) / "ledger.sqlite") as ledger:
            ledger.append_fact(self.fact("fact-1", 0, 50))
            ledger.append_fact(self.fact("fact-2", 60, 100))
            self.assertEqual(50, ledger.contiguous_watermark(episode_id="episode-1", continuity_start_pts_ns=0))
            with self.assertRaisesRegex(SemanticLedgerError, "stable_scope_exceeds_durable_watermark"):
                ledger.record_scope(self.scope())

    def test_revision_must_reference_same_durable_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, RealtimeSemanticLedger(Path(temp_dir) / "ledger.sqlite") as ledger:
            ledger.append_fact(self.fact("fact-1", 0, 100))
            ledger.record_scope(self.scope())
            revision = self.scope(
                scope_id="scope-2",
                scope_hash=HASH_B,
                stability=SemanticScopeStability.REVISED,
                semantic_revision=2,
                replaces_scope_id="scope-1",
                predecessor_scope_hash=HASH_A,
            )
            self.assertTrue(ledger.record_scope(revision))
            with self.assertRaisesRegex(SemanticLedgerError, "scope_predecessor_scope_mismatch"):
                ledger.record_scope(
                    self.scope(
                        scope_id="scope-3",
                        scope_hash="c" * 64,
                        stability=SemanticScopeStability.REVISED,
                        semantic_revision=2,
                        replaces_scope_id="scope-1",
                        predecessor_scope_hash="d" * 64,
                    )
                )

    def test_late_admission_uses_ledger_presentation_truth_and_never_advances_watermark(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, RealtimeSemanticLedger(Path(temp_dir) / "ledger.sqlite") as ledger:
            ledger.append_fact(self.fact("fact-1", 0, 100))
            ledger.record_scope(self.scope())
            ledger.append_fact(self.fact("late-1", 20, 40), is_late=True)
            before = ledger.contiguous_watermark(episode_id="episode-1", continuity_start_pts_ns=0)
            admission = self.late_admission()
            self.assertTrue(ledger.admit_late_fact(admission))
            self.assertFalse(ledger.admit_late_fact(admission))
            self.assertEqual(before, ledger.contiguous_watermark(episode_id="episode-1", continuity_start_pts_ns=0))
            ledger.mark_scope_presented(scope_id="scope-1", semantic_revision=1, presentation_revision_ref="present-1")
            with self.assertRaisesRegex(SemanticLedgerError, "late_admission_presentation_mismatch"):
                ledger.admit_late_fact(self.late_admission(admission_idempotency_key="admission-2"))
            revised = self.late_admission(
                admission_idempotency_key="admission-3",
                presentation_revision_ref="present-1",
                disposition=LateFactDisposition.REVISE_PRESENTED,
            )
            self.assertTrue(ledger.admit_late_fact(revised))

    def test_dual_clock_heartbeat_requires_new_processed_media_and_expires(self) -> None:
        heartbeat = L0SemanticHeartbeat(
            heartbeat_id="heartbeat-1",
            learner_id="learner-1",
            session_id="session-1",
            capture_consent_id="consent-1",
            consent_generation=1,
            route_lease_id="route-1",
            route_epoch=1,
            processed_media_watermark_pts_ns=100,
            semantic_watermark_pts_ns=100,
            last_ack_fact_id="fact-1",
            observed_elapsed_ns=1_000,
            deadline_ns=100,
            worker_health_lease_id="worker-lease-1",
            slo_policy_version="slo.v1",
        )
        with tempfile.TemporaryDirectory() as temp_dir, RealtimeSemanticLedger(Path(temp_dir) / "ledger.sqlite") as ledger:
            ledger.append_fact(self.fact("fact-1", 0, 100))
            ledger.record_heartbeat(heartbeat)
            self.assertEqual(
                L0HeartbeatState.ACTIVE,
                ledger.heartbeat_state(
                    learner_id="learner-1", session_id="session-1", capture_consent_id="consent-1",
                    consent_generation=1, route_epoch=1, now_elapsed_ns=1_100,
                ),
            )
            with self.assertRaisesRegex(SemanticLedgerError, "l0_heartbeat_not_monotonic_or_route_mismatch"):
                ledger.record_heartbeat(
                    L0SemanticHeartbeat(
                        **{**heartbeat.__dict__, "heartbeat_id": "heartbeat-2", "observed_elapsed_ns": 1_050}
                )
            )
            ledger.append_fact(self.fact("fact-2", 100, 150))
            ledger.record_heartbeat(
                L0SemanticHeartbeat(
                    **{
                        **heartbeat.__dict__,
                        "heartbeat_id": "heartbeat-3",
                        "processed_media_watermark_pts_ns": 200,
                        "semantic_watermark_pts_ns": 150,
                        "last_ack_fact_id": "fact-2",
                        "observed_elapsed_ns": 1_200,
                    }
                )
            )
            self.assertEqual(
                L0HeartbeatState.SEMANTIC_STALLED,
                ledger.heartbeat_state(
                    learner_id="learner-1", session_id="session-1", capture_consent_id="consent-1",
                    consent_generation=1, route_epoch=1, now_elapsed_ns=1_301,
                ),
            )


if __name__ == "__main__":
    unittest.main()
