from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.contracts import (  # noqa: E402
    AudioCapabilitySnapshot,
    AudioCaptureMode,
    AudioRestriction,
    AudioResolution,
    ContractError,
    LateFactAdmission,
    LateFactDisposition,
    PcBufferedFragment,
    PcBufferGapDisposition,
    PcBufferResumeReceipt,
    SemanticAudioRequirement,
    SemanticAudioRequirementDecision,
    SourceKind,
)


HASH_A = "a" * 64


class AudioAndContinuityContractTests(unittest.TestCase):
    def audio_snapshot(self, **overrides: object) -> AudioCapabilitySnapshot:
        fields: dict[str, object] = {
            "snapshot_id": "audio-1",
            "learner_id": "learner-1",
            "session_id": "session-1",
            "capture_consent_id": "consent-1",
            "consent_generation": 1,
            "source_kind": SourceKind.PHONE_SCREEN,
            "start_pts_ns": 100,
            "end_pts_ns": 200,
            "capture_mode": AudioCaptureMode.PLAYBACK,
            "application_package_id": "tv.danmaku.bili",
            "restriction": AudioRestriction.NONE,
            "resolution": AudioResolution.SAME_SOURCE_VERIFIED,
            "audio_track_hashes": (HASH_A,),
            "absence_proof_hash": None,
            "source_fragment_hashes": (HASH_A,),
            "clock_domain_id": "rtsp-pts.v1",
            "sync_error_ns": 20,
            "sync_sample_hash": HASH_A,
            "max_allowed_sync_error_ns": 40,
            "failure_code": None,
            "recovery_attempt_id": "recover-1",
            "policy_version": "audio-policy.v2",
        }
        fields.update(overrides)
        return AudioCapabilitySnapshot(**fields)  # type: ignore[arg-type]

    def test_playback_audio_must_have_track_and_sync_proof(self) -> None:
        with self.assertRaisesRegex(ContractError, "verified_audio_requires_track_proof"):
            self.audio_snapshot(audio_track_hashes=())
        with self.assertRaisesRegex(ContractError, "verified_audio_requires_sync_proof"):
            self.audio_snapshot(sync_error_ns=None)
        with self.assertRaisesRegex(ContractError, "verified_audio_requires_playback_mode"):
            self.audio_snapshot(capture_mode=AudioCaptureMode.MICROPHONE)
        with self.assertRaisesRegex(ContractError, "verified_audio_sync_error_exceeds_policy"):
            self.audio_snapshot(sync_error_ns=41)

    def test_capture_failure_cannot_be_disguised_as_silent_content(self) -> None:
        with self.assertRaisesRegex(ContractError, "no_audio_requires_absence_proof"):
            self.audio_snapshot(
                capture_mode=AudioCaptureMode.NONE,
                resolution=AudioResolution.NO_AUDIO_TRACK_VERIFIED,
                audio_track_hashes=(),
                absence_proof_hash=None,
                sync_error_ns=None,
                sync_sample_hash=None,
                max_allowed_sync_error_ns=None,
                recovery_attempt_id=None,
            )
        with self.assertRaisesRegex(ContractError, "unresolved_audio_requires_failure_code"):
            self.audio_snapshot(
                resolution=AudioResolution.AUDIO_REQUIRED_UNRESOLVED,
                audio_track_hashes=(),
                sync_error_ns=None,
                sync_sample_hash=None,
                max_allowed_sync_error_ns=None,
                failure_code=None,
                restriction=AudioRestriction.CAPTURE_FAILURE,
            )

    def test_drm_application_and_system_restrictions_remain_explicit_unresolved_audio(self) -> None:
        for restriction in (
            AudioRestriction.APPLICATION_DISALLOWED,
            AudioRestriction.DRM_PROTECTED,
            AudioRestriction.SYSTEM_POLICY,
            AudioRestriction.PERMISSION_DENIED,
        ):
            snapshot = self.audio_snapshot(
                resolution=AudioResolution.AUDIO_REQUIRED_UNRESOLVED,
                audio_track_hashes=(),
                sync_error_ns=None,
                sync_sample_hash=None,
                max_allowed_sync_error_ns=None,
                failure_code="audio_capture_restricted",
                restriction=restriction,
            )
            self.assertEqual(restriction, snapshot.restriction)
        with self.assertRaisesRegex(ContractError, "verified_audio_cannot_have_restriction"):
            self.audio_snapshot(restriction=AudioRestriction.DRM_PROTECTED)
        with self.assertRaisesRegex(ContractError, "unresolved_audio_requires_restriction"):
            self.audio_snapshot(
                resolution=AudioResolution.AUDIO_REQUIRED_UNRESOLVED,
                audio_track_hashes=(),
                sync_error_ns=None,
                sync_sample_hash=None,
                max_allowed_sync_error_ns=None,
                failure_code="audio_capture_restricted",
                restriction=AudioRestriction.NONE,
            )

    def test_no_audio_requires_real_absence_proof_not_microphone_substitution(self) -> None:
        with self.assertRaisesRegex(ContractError, "no_audio_requires_none_mode"):
            self.audio_snapshot(
                capture_mode=AudioCaptureMode.MICROPHONE,
                resolution=AudioResolution.NO_AUDIO_TRACK_VERIFIED,
                audio_track_hashes=(),
                absence_proof_hash=HASH_A,
                sync_error_ns=None,
                sync_sample_hash=None,
                max_allowed_sync_error_ns=None,
                recovery_attempt_id=None,
            )
        snapshot = self.audio_snapshot(
            capture_mode=AudioCaptureMode.NONE,
            resolution=AudioResolution.NO_AUDIO_TRACK_VERIFIED,
            audio_track_hashes=(),
            absence_proof_hash=HASH_A,
            sync_error_ns=None,
            sync_sample_hash=None,
            max_allowed_sync_error_ns=None,
            recovery_attempt_id=None,
        )
        self.assertFalse(snapshot.permits_audio_not_required)
        with self.assertRaisesRegex(ContractError, "audio_not_required_requires_verified_absence"):
            SemanticAudioRequirementDecision(
                decision_id="audio-decision-1",
                learner_id="learner-1",
                session_id="session-1",
                capture_consent_id="consent-1",
                consent_generation=1,
                source_kind=SourceKind.PHONE_SCREEN,
                scope_id="scope-1",
                scope_hash=HASH_A,
                start_pts_ns=100,
                end_pts_ns=200,
                snapshot=self.audio_snapshot(),
                requirement=SemanticAudioRequirement.AUDIO_NOT_REQUIRED_VERIFIED,
                semantic_nonessential_evidence_hashes=(HASH_A,),
                visual_text_coverage_hashes=(HASH_A,),
                policy_version="audio-policy.v2",
                decision_trace_hash=HASH_A,
            )
        decision = SemanticAudioRequirementDecision(
            decision_id="audio-decision-2",
            learner_id="learner-1",
            session_id="session-1",
            capture_consent_id="consent-1",
            consent_generation=1,
            source_kind=SourceKind.PHONE_SCREEN,
            scope_id="scope-1",
            scope_hash=HASH_A,
            start_pts_ns=100,
            end_pts_ns=200,
            snapshot=snapshot,
            requirement=SemanticAudioRequirement.AUDIO_NOT_REQUIRED_VERIFIED,
            semantic_nonessential_evidence_hashes=(HASH_A,),
            visual_text_coverage_hashes=(HASH_A,),
            policy_version="audio-policy.v2",
            decision_trace_hash=HASH_A,
        )
        self.assertTrue(decision.permits_audio_not_required)

    def buffered_fragment(self, sequence: int, start_pts_ns: int, end_pts_ns: int) -> PcBufferedFragment:
        return PcBufferedFragment(
            fragment_id=f"fragment-{sequence}",
            sequence=sequence,
            start_pts_ns=start_pts_ns,
            end_pts_ns=end_pts_ns,
            media_hash=HASH_A,
            local_storage_hash=HASH_A,
            outbox_id=f"outbox-{sequence}",
            replay_idempotency_key=f"replay-{sequence}",
        )

    def test_pc_resume_stays_with_same_pc_route_and_generation(self) -> None:
        receipt = PcBufferResumeReceipt(
            receipt_id="resume-1",
            learner_id="learner-1",
            session_id="session-1",
            capture_consent_id="consent-1",
            consent_generation=1,
            route_lease_id="route-1",
            route_epoch=3,
            capture_epoch=1,
            owner_endpoint_id="pc-1",
            buffered_start_pts_ns=100,
            buffered_end_pts_ns=300,
            cache_manifest_hash=HASH_A,
            resumed_owner_endpoint_id="pc-1",
            fragments=(
                self.buffered_fragment(4, 100, 200),
                self.buffered_fragment(5, 200, 300),
            ),
            last_acked_sequence=3,
            resume_attempt_id="attempt-1",
            replay_idempotency_key="resume-key-1",
            gap_disposition=PcBufferGapDisposition.CONTIGUOUS,
        )
        self.assertEqual("pc-1", receipt.resumed_owner_endpoint_id)
        with self.assertRaisesRegex(ContractError, "resume_cannot_change_route_owner"):
            PcBufferResumeReceipt(
                **{**receipt.__dict__, "resumed_owner_endpoint_id": "cloud-1"}
            )
        with self.assertRaisesRegex(ContractError, "resume_pts_invalid"):
            PcBufferResumeReceipt(
                **{**receipt.__dict__, "buffered_end_pts_ns": 100}
            )
        with self.assertRaisesRegex(ContractError, "resume_unacknowledged_pts_gap"):
            PcBufferResumeReceipt(
                **{
                    **receipt.__dict__,
                    "fragments": (
                        self.buffered_fragment(4, 100, 200),
                        self.buffered_fragment(5, 250, 300),
                    ),
                }
            )
        with self.assertRaisesRegex(ContractError, "resume_ack_cursor_invalid"):
            PcBufferResumeReceipt(**{**receipt.__dict__, "last_acked_sequence": 6})

    def test_late_facts_force_reassessment_or_revision_not_immediate_l1(self) -> None:
        pending = LateFactAdmission(
            fact_id="fact-1",
            learner_id="learner-1",
            session_id="session-1",
            episode_id="episode-1",
            capture_consent_id="consent-1",
            consent_generation=1,
            source_kind=SourceKind.PHONE_SCREEN,
            scope_id="scope-1",
            scope_hash=HASH_A,
            base_scope_revision=1,
            fact_start_pts_ns=120,
            fact_end_pts_ns=160,
            event_time_watermark_ns=200,
            arrived_elapsed_ns=500,
            evidence_hashes=(HASH_A,),
            fact_content_hash=HASH_A,
            admission_idempotency_key="late-1",
            allowed_lateness_ns=50,
            late_policy_id="late-policy.v1",
            presentation_revision_ref=None,
            disposition=LateFactDisposition.REASSESS_UNPRESENTED,
        )
        self.assertEqual(LateFactDisposition.REASSESS_UNPRESENTED, pending.disposition)
        with self.assertRaisesRegex(ContractError, "unpresented_late_fact_requires_reassessment"):
            LateFactAdmission(
                **{**pending.__dict__, "disposition": LateFactDisposition.REVISE_PRESENTED}
            )
        with self.assertRaisesRegex(ContractError, "presented_late_fact_requires_revision_or_withdrawal"):
            LateFactAdmission(
                **{**pending.__dict__, "presentation_revision_ref": "presentation-1"}
            )
        revision = LateFactAdmission(
            **{
                **pending.__dict__,
                "presentation_revision_ref": "presentation-1",
                "disposition": LateFactDisposition.REVISE_PRESENTED,
            }
        )
        self.assertEqual(LateFactDisposition.REVISE_PRESENTED, revision.disposition)
        with self.assertRaisesRegex(ContractError, "late_fact_exceeds_allowed_lateness"):
            LateFactAdmission(
                **{**pending.__dict__, "allowed_lateness_ns": 39}
            )
        quarantined = LateFactAdmission(
            **{
                **pending.__dict__,
                "allowed_lateness_ns": 39,
                "disposition": LateFactDisposition.QUARANTINE,
            }
        )
        self.assertEqual(LateFactDisposition.QUARANTINE, quarantined.disposition)


if __name__ == "__main__":
    unittest.main()
