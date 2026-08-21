from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.analysis_route import AnalysisRouteError, AnalysisRouteLedger  # noqa: E402
from realtime_runtime.contracts import AnalysisRouteLease, AnalysisRouteState  # noqa: E402


HASH_A = "a" * 64
HASH_B = "b" * 64


class AnalysisRouteLedgerTests(unittest.TestCase):
    def lease(
        self,
        *,
        lease_id: str = "pc-lease",
        session_id: str = "session-1",
        state: AnalysisRouteState = AnalysisRouteState.PC_LOCAL_ACTIVE,
        owner: str | None = "pc-1",
        route_epoch: int = 1,
        issued_elapsed_ns: int = 100,
        expires_elapsed_ns: int = 10_000,
    ) -> AnalysisRouteLease:
        return AnalysisRouteLease(
            lease_id=lease_id,
            learner_id="learner-1",
            session_id=session_id,
            capture_consent_id="consent-1",
            consent_generation=1,
            route_epoch=route_epoch,
            state=state,
            owner_endpoint_id=owner,
            opened_receipt_hash=HASH_A,
            student_confirmation_hash=HASH_B,
            issued_elapsed_ns=issued_elapsed_ns,
            last_renewed_elapsed_ns=issued_elapsed_ns,
            expires_elapsed_ns=expires_elapsed_ns,
        )

    def test_only_current_pc_owner_can_buffer_restore_or_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, AnalysisRouteLedger(Path(temp_dir) / "route.sqlite") as ledger:
            lease = self.lease()
            ledger.open(lease, now_elapsed_ns=100)
            ledger.assert_pc_ingress_authorized(
                lease_id=lease.lease_id,
                learner_id="learner-1",
                session_id="session-1",
                capture_consent_id="consent-1",
                consent_generation=1,
                route_epoch=1,
                endpoint_id="pc-1",
                now_elapsed_ns=101,
            )
            with self.assertRaisesRegex(AnalysisRouteError, "route_owner_or_epoch_denied"):
                ledger.transition_pc_buffer(lease_id=lease.lease_id, route_epoch=1, endpoint_id="pc-2", now_elapsed_ns=102)
            ledger.transition_pc_buffer(lease_id=lease.lease_id, route_epoch=1, endpoint_id="pc-1", now_elapsed_ns=102)
            with self.assertRaisesRegex(AnalysisRouteError, "route_owner_or_epoch_denied"):
                ledger.assert_pc_ingress_authorized(
                    lease_id=lease.lease_id,
                    learner_id="learner-1",
                    session_id="session-1",
                    capture_consent_id="consent-1",
                    consent_generation=1,
                    route_epoch=1,
                    endpoint_id="pc-1",
                    now_elapsed_ns=103,
                )
            ledger.assert_pc_resume_authorized(
                lease_id=lease.lease_id,
                learner_id="learner-1",
                session_id="session-1",
                capture_consent_id="consent-1",
                consent_generation=1,
                route_epoch=1,
                endpoint_id="pc-1",
                now_elapsed_ns=103,
            )
            with self.assertRaisesRegex(AnalysisRouteError, "route_owner_or_epoch_denied"):
                ledger.assert_pc_resume_authorized(
                    lease_id=lease.lease_id,
                    learner_id="learner-1",
                    session_id="session-1",
                    capture_consent_id="consent-1",
                    consent_generation=1,
                    route_epoch=1,
                    endpoint_id="cloud-1",
                    now_elapsed_ns=103,
                )
            ledger.restore_pc(lease_id=lease.lease_id, route_epoch=1, endpoint_id="pc-1", now_elapsed_ns=104)

    def test_cloud_cannot_take_over_existing_or_unclean_pc_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, AnalysisRouteLedger(Path(temp_dir) / "route.sqlite") as ledger:
            pc = self.lease()
            ledger.open(pc, now_elapsed_ns=100)
            cloud_same_session = self.lease(
                lease_id="cloud-bad",
                state=AnalysisRouteState.CLOUD_ACTIVE,
                owner="cloud-1",
            )
            with self.assertRaisesRegex(AnalysisRouteError, "cloud_open_requires_closed_prior_pc_session"):
                ledger.open_cloud_after_pc_closed(
                    cloud_same_session,
                    prior_pc_lease_id="pc-lease",
                    prior_close_receipt_hash=HASH_B,
                    now_elapsed_ns=101,
                )
            ledger.close_pc(lease_id="pc-lease", route_epoch=1, endpoint_id="pc-1", close_receipt_hash=HASH_B, now_elapsed_ns=102)
            cloud = self.lease(
                lease_id="cloud-lease",
                session_id="session-2",
                state=AnalysisRouteState.CLOUD_ACTIVE,
                owner="cloud-1",
            )
            ledger.open_cloud_after_pc_closed(
                cloud,
                prior_pc_lease_id="pc-lease",
                prior_close_receipt_hash=HASH_B,
                now_elapsed_ns=103,
            )
            with self.assertRaisesRegex(AnalysisRouteError, "route_lease_not_active"):
                ledger.assert_pc_resume_authorized(
                    lease_id="pc-lease",
                    learner_id="learner-1",
                    session_id="session-1",
                    capture_consent_id="consent-1",
                    consent_generation=1,
                    route_epoch=1,
                    endpoint_id="pc-1",
                    now_elapsed_ns=104,
                )

    def test_cloud_transition_requires_new_session_and_matching_close_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, AnalysisRouteLedger(Path(temp_dir) / "route.sqlite") as ledger:
            pc = self.lease()
            ledger.open(pc, now_elapsed_ns=100)
            ledger.close_pc(lease_id="pc-lease", route_epoch=1, endpoint_id="pc-1", close_receipt_hash=HASH_B, now_elapsed_ns=101)
            same_session = self.lease(
                lease_id="cloud-same-session",
                state=AnalysisRouteState.CLOUD_ACTIVE,
                owner="cloud-1",
            )
            with self.assertRaisesRegex(AnalysisRouteError, "cloud_open_requires_closed_prior_pc_session"):
                ledger.open_cloud_after_pc_closed(
                    same_session,
                    prior_pc_lease_id="pc-lease",
                    prior_close_receipt_hash=HASH_B,
                    now_elapsed_ns=102,
                )
            new_session = self.lease(
                lease_id="cloud-wrong-receipt",
                session_id="session-2",
                state=AnalysisRouteState.CLOUD_ACTIVE,
                owner="cloud-1",
            )
            with self.assertRaisesRegex(AnalysisRouteError, "cloud_open_requires_closed_prior_pc_session"):
                ledger.open_cloud_after_pc_closed(
                    new_session,
                    prior_pc_lease_id="pc-lease",
                    prior_close_receipt_hash=HASH_A,
                    now_elapsed_ns=102,
                )

    def test_expired_route_fences_old_owner_and_requires_a_new_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, AnalysisRouteLedger(Path(temp_dir) / "route.sqlite") as ledger:
            first = self.lease(expires_elapsed_ns=200)
            ledger.open(first, now_elapsed_ns=100)
            ledger.assert_pc_ingress_authorized(
                lease_id=first.lease_id,
                learner_id="learner-1",
                session_id="session-1",
                capture_consent_id="consent-1",
                consent_generation=1,
                route_epoch=1,
                endpoint_id="pc-1",
                now_elapsed_ns=199,
            )
            with self.assertRaisesRegex(AnalysisRouteError, "route_lease_expired"):
                ledger.assert_pc_ingress_authorized(
                    lease_id=first.lease_id,
                    learner_id="learner-1",
                    session_id="session-1",
                    capture_consent_id="consent-1",
                    consent_generation=1,
                    route_epoch=1,
                    endpoint_id="pc-1",
                    now_elapsed_ns=200,
                )
            stale_epoch = self.lease(lease_id="stale", route_epoch=1, issued_elapsed_ns=201, expires_elapsed_ns=400)
            with self.assertRaisesRegex(AnalysisRouteError, "route_epoch_not_monotonic"):
                ledger.open(stale_epoch, now_elapsed_ns=201)
            replacement = self.lease(lease_id="replacement", route_epoch=2, issued_elapsed_ns=201, expires_elapsed_ns=400)
            ledger.open(replacement, now_elapsed_ns=201)

    def test_owner_can_renew_before_expiry_but_not_after_or_from_another_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, AnalysisRouteLedger(Path(temp_dir) / "route.sqlite") as ledger:
            lease = self.lease(expires_elapsed_ns=200)
            ledger.open(lease, now_elapsed_ns=100)
            with self.assertRaisesRegex(AnalysisRouteError, "route_owner_or_epoch_denied"):
                ledger.renew(lease_id=lease.lease_id, route_epoch=1, endpoint_id="pc-2", now_elapsed_ns=150, new_expires_elapsed_ns=300)
            ledger.renew(lease_id=lease.lease_id, route_epoch=1, endpoint_id="pc-1", now_elapsed_ns=150, new_expires_elapsed_ns=300)
            ledger.assert_pc_ingress_authorized(
                lease_id=lease.lease_id,
                learner_id="learner-1",
                session_id="session-1",
                capture_consent_id="consent-1",
                consent_generation=1,
                route_epoch=1,
                endpoint_id="pc-1",
                now_elapsed_ns=299,
            )
            with self.assertRaisesRegex(AnalysisRouteError, "route_lease_expired"):
                ledger.renew(lease_id=lease.lease_id, route_epoch=1, endpoint_id="pc-1", now_elapsed_ns=300, new_expires_elapsed_ns=400)


if __name__ == "__main__":
    unittest.main()
