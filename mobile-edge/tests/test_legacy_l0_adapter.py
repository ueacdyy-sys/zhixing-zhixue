from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.analysis_route import AnalysisRouteLedger  # noqa: E402
from realtime_runtime.contracts import (  # noqa: E402
    AnalysisRouteLease,
    AnalysisRouteState,
    FusedCandidate,
    FusionMode,
    Lane,
    LaneEvidence,
    QualityStatus,
    SealedFragment,
    SemanticWindow,
    SourceContext,
    Visit,
)
from realtime_runtime.legacy_l0_adapter import LegacyL0AdapterError, fused_candidate_to_l0_fact  # noqa: E402
from realtime_runtime.lane_worker import _project_fused_candidates_to_v2_l0, _validate_v2_projection_config  # noqa: E402
from realtime_runtime.ledger import SealedWindowLedger  # noqa: E402
from realtime_runtime.semantic_ledger import RealtimeSemanticLedger  # noqa: E402


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


class LegacyL0AdapterTests(unittest.TestCase):
    def candidate(self, **overrides: object) -> FusedCandidate:
        fields: dict[str, object] = {
            "window_id": "session-1:visit:0001:window:000001",
            "visit_id": "session-1:visit:0001",
            "source_context": SourceContext.PHONE_DAILY,
            "start_pts_ns": 0,
            "end_pts_ns": 100,
            "evidence_uris": ("local://artifact/asr.json", "local://artifact/ocr.json", "local://artifact/vlm.json"),
            "fused_at_ns": 123,
            "fusion_mode": FusionMode.TRIMODAL,
            "classification": "CANDIDATE_ONLY",
        }
        fields.update(overrides)
        return FusedCandidate(**fields)  # type: ignore[arg-type]

    def test_legacy_fused_window_becomes_l0_evidence_only(self) -> None:
        fact = fused_candidate_to_l0_fact(
            self.candidate(),
            session_id="session-1",
            learner_id="learner-1",
            capture_consent_id="consent-1",
            consent_generation=1,
            evidence_hashes=(HASH_A, HASH_B, HASH_C),
        )
        self.assertEqual("LEGACY_FUSED_WINDOW_EVIDENCE_ONLY", fact.fact_kind)
        self.assertTrue(fact.episode_id.startswith("legacy-read-only:"))
        with tempfile.TemporaryDirectory() as temp_dir, RealtimeSemanticLedger(Path(temp_dir) / "semantic.sqlite") as ledger:
            self.assertTrue(ledger.append_fact(fact))
            self.assertFalse(ledger.append_fact(fact))

    def test_adapter_refuses_non_read_only_or_unverifiable_legacy_input(self) -> None:
        with self.assertRaisesRegex(LegacyL0AdapterError, "legacy_candidate_classification_not_read_only"):
            fused_candidate_to_l0_fact(
                self.candidate(classification="L1_ELIGIBLE"),
                session_id="session-1",
                learner_id="learner-1",
                capture_consent_id="consent-1",
                consent_generation=1,
                evidence_hashes=(HASH_A, HASH_B, HASH_C),
            )
        with self.assertRaisesRegex(LegacyL0AdapterError, "legacy_l0_evidence_count_invalid"):
            fused_candidate_to_l0_fact(
                self.candidate(),
                session_id="session-1",
                learner_id="learner-1",
                capture_consent_id="consent-1",
                consent_generation=1,
                evidence_hashes=(HASH_A,),
            )

    def test_worker_rejects_partial_v2_l0_activation_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "v2_l0_projection_config_incomplete"):
            _validate_v2_projection_config(Path("semantic.sqlite"), None, "consent-1", 1, None, None, None, None)
        with self.assertRaisesRegex(ValueError, "v2_l0_projection_requires_route_authority"):
            _validate_v2_projection_config(Path("semantic.sqlite"), "learner-1", "consent-1", 1, None, None, None, None)
        with self.assertRaisesRegex(ValueError, "v2_l0_projection_consent_generation_invalid"):
            _validate_v2_projection_config(
                Path("semantic.sqlite"), "learner-1", "consent-1", 0,
                Path("route.sqlite"), "lease-1", 1, "pc-1",
            )

    def test_worker_projection_requires_current_pc_route_and_writes_only_l0_fact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_path = root / "legacy.sqlite"
            semantic_path = root / "semantic.sqlite"
            route_path = root / "route.sqlite"
            artifacts = root / "artifacts"
            with SealedWindowLedger(legacy_path) as legacy:
                legacy.open_visit(Visit("session-1:visit:0001", "session-1", SourceContext.PHONE_DAILY, 0))
                legacy.append_fragment(
                    SealedFragment(
                        fragment_id="fragment-1", session_id="session-1", source_context=SourceContext.PHONE_DAILY,
                        start_pts_ns=0, end_pts_ns=100, media_uri="local://capture/fragment-1.mp4", media_sha256=HASH_A,
                        has_video=True, has_same_source_audio=True, pc_arrival_first_ns=1, pc_sealed_ns=101,
                    )
                )
                legacy.create_window(
                    SemanticWindow("window-1", "session-1", "session-1:visit:0001", SourceContext.PHONE_DAILY, 0, 100, (HASH_A,), (Lane.ASR, Lane.OCR, Lane.VLM)),
                    fusion_mode=FusionMode.TRIMODAL,
                    created_ns=1,
                )
                for index, lane in enumerate((Lane.ASR, Lane.OCR, Lane.VLM), 1):
                    lease = legacy.claim(lane, f"worker-{lane.value}", now_ns=index, lease_ns=100)
                    legacy.complete(
                        lease,
                        LaneEvidence(
                            window_id="window-1", lane=lane, coverage_start_pts_ns=0, coverage_end_pts_ns=100,
                            source_fragment_hashes=(HASH_A,), quality_status=QualityStatus.FUSION_ELIGIBLE,
                            artifact_uri=f"local://artifact/{lane.value}.json", artifact_sha256=(lane.value.lower()[0] * 64),
                            started_ns=index, completed_ns=index + 1,
                        ),
                    )
                fused = tuple(legacy.fuse_ready(now_ns=1000))
                with AnalysisRouteLedger(route_path) as routes:
                    routes.open(
                        AnalysisRouteLease(
                            lease_id="route-1", learner_id="learner-1", session_id="session-1", capture_consent_id="consent-1",
                            consent_generation=1, route_epoch=1, state=AnalysisRouteState.PC_LOCAL_ACTIVE,
                            owner_endpoint_id="pc-1", opened_receipt_hash=HASH_A, student_confirmation_hash=HASH_B,
                            issued_elapsed_ns=0, last_renewed_elapsed_ns=0, expires_elapsed_ns=10_000,
                        )
                        , now_elapsed_ns=0
                    )
                _project_fused_candidates_to_v2_l0(
                    legacy_ledger=legacy, fused=fused, semantic_ledger_path=semantic_path, learner_id="learner-1",
                    capture_consent_id="consent-1", consent_generation=1, route_ledger_path=route_path,
                    route_lease_id="route-1", route_epoch=1, owner_endpoint_id="pc-1", artifact_root=artifacts,
                    now_elapsed_ns=1_000,
                )
            with RealtimeSemanticLedger(semantic_path) as semantic:
                self.assertEqual(100, semantic.contiguous_watermark(episode_id="legacy-read-only:session-1:visit:0001", continuity_start_pts_ns=0))
            self.assertFalse((artifacts / "v2_l0_projection_errors.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
