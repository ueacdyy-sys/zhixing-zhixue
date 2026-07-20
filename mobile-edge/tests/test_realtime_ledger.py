from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.contracts import (  # noqa: E402
    Lane,
    LaneEvidence,
    AudioStatus,
    FusionMode,
    QualityStatus,
    SealedFragment,
    SemanticWindow,
    SourceContext,
    Visit,
)
from realtime_runtime.ledger import SealedWindowLedger  # noqa: E402
from realtime_runtime.visit import VisitWindowPlanner  # noqa: E402


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def fragment(fragment_id: str, start: int, end: int, digest: str) -> SealedFragment:
    return SealedFragment(
        fragment_id=fragment_id,
        session_id="session-1",
        source_context=SourceContext.PHONE_DAILY,
        start_pts_ns=start,
        end_pts_ns=end,
        media_uri=f"local://media/{fragment_id}.mkv",
        media_sha256=digest,
        has_video=True,
        has_same_source_audio=True,
        pc_arrival_first_ns=start + 10,
        pc_sealed_ns=end + 20,
    )


def window(
    window_id: str,
    start: int,
    end: int,
    hashes: tuple[str, ...],
    *,
    visit_id: str = "session-1:visit:0001",
    lanes: tuple[Lane, ...] = (Lane.ASR, Lane.OCR, Lane.VLM),
) -> SemanticWindow:
    return SemanticWindow(
        window_id=window_id,
        session_id="session-1",
        visit_id=visit_id,
        source_context=SourceContext.PHONE_DAILY,
        start_pts_ns=start,
        end_pts_ns=end,
        fragment_hashes=hashes,
        required_lanes=lanes,
    )


def evidence(window_id: str, lane: Lane, start: int, end: int, hashes: tuple[str, ...], now: int) -> LaneEvidence:
    return LaneEvidence(
        window_id=window_id,
        lane=lane,
        coverage_start_pts_ns=start,
        coverage_end_pts_ns=end,
        source_fragment_hashes=hashes,
        quality_status=QualityStatus.FUSION_ELIGIBLE,
        artifact_uri=f"local://evidence/{window_id}/{lane}.json",
        artifact_sha256=(lane.value.lower()[0] * 64),
        started_ns=now,
        completed_ns=now + 1,
    )


class SealedWindowLedgerTests(unittest.TestCase):
    @staticmethod
    def open_visit(ledger: SealedWindowLedger, visit_id: str = "session-1:visit:0001", start: int = 0) -> None:
        ledger.open_visit(
            Visit(
                visit_id=visit_id,
                session_id="session-1",
                source_context=SourceContext.PHONE_DAILY,
                start_pts_ns=start,
            )
        )

    def test_expired_lease_is_recoverable_after_process_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ledger.sqlite"
            with SealedWindowLedger(path) as ledger:
                self.open_visit(ledger)
                ledger.append_fragment(fragment("f1", 0, 2, HASH_A))
                ledger.create_window(window("w1", 0, 2, (HASH_A,)))
                lease = ledger.claim(Lane.VLM, "worker-a", now_ns=100, lease_ns=10)
                self.assertIsNotNone(lease)

            with SealedWindowLedger(path) as restarted:
                self.assertEqual(1, restarted.recover_expired_leases(now_ns=111))
                retried = restarted.claim(Lane.VLM, "worker-b", now_ns=112, lease_ns=10)
                self.assertEqual(2, retried.attempt_id)
                self.assertEqual("worker-b", retried.worker_id)

    def test_evidence_with_wrong_media_coverage_is_rejected_and_job_stays_leased(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with SealedWindowLedger(Path(temp_dir) / "ledger.sqlite") as ledger:
                self.open_visit(ledger)
                ledger.append_fragment(fragment("f1", 0, 2, HASH_A))
                ledger.create_window(window("w1", 0, 2, (HASH_A,)))
                lease = ledger.claim(Lane.OCR, "worker", now_ns=10, lease_ns=100)
                with self.assertRaises(ValueError):
                    ledger.complete(lease, evidence("w1", Lane.OCR, 0, 2, (HASH_B,), 20))
                self.assertEqual("LEASED", ledger.job_state("w1", Lane.OCR))

    def test_candidate_emits_only_after_all_lanes_cover_same_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with SealedWindowLedger(Path(temp_dir) / "ledger.sqlite") as ledger:
                self.open_visit(ledger)
                ledger.append_fragment(fragment("f1", 0, 2, HASH_A))
                ledger.append_fragment(fragment("f2", 2, 4, HASH_B))
                ledger.create_window(window("w1", 0, 4, (HASH_A, HASH_B)))
                for index, lane in enumerate((Lane.ASR, Lane.OCR, Lane.VLM), 1):
                    lease = ledger.claim(lane, f"worker-{lane}", now_ns=10 * index, lease_ns=100)
                    ledger.complete(lease, evidence("w1", lane, 0, 4, (HASH_A, HASH_B), 20 * index))
                    if lane != Lane.VLM:
                        self.assertEqual([], ledger.fuse_ready(now_ns=100))
                candidates = ledger.fuse_ready(now_ns=100)
                self.assertEqual(["w1"], [candidate.window_id for candidate in candidates])
                self.assertEqual("CANDIDATE_ONLY", candidates[0].classification)
                self.assertEqual([], ledger.fuse_ready(now_ns=101))

    def test_fused_candidate_event_is_durable_and_emitted_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ledger.sqlite"
            with SealedWindowLedger(path) as ledger:
                self.open_visit(ledger)
                ledger.append_fragment(fragment("f1", 0, 2, HASH_A))
                ledger.create_window(window("w1", 0, 2, (HASH_A,)))
                for index, lane in enumerate((Lane.ASR, Lane.OCR, Lane.VLM), 1):
                    lease = ledger.claim(lane, f"worker-{lane}", now_ns=index, lease_ns=100)
                    ledger.complete(lease, evidence("w1", lane, 0, 2, (HASH_A,), index + 10))
                ledger.fuse_ready(now_ns=100)
                events = ledger.fused_candidate_events()
                self.assertEqual(["w1"], [item.window_id for item in events])
                self.assertEqual(FusionMode.TRIMODAL, events[0].fusion_mode)

            with SealedWindowLedger(path) as restarted:
                self.assertEqual(["w1"], [item.window_id for item in restarted.fused_candidate_events()])
                self.assertEqual([], restarted.fuse_ready(now_ns=101))

    def test_late_window_cannot_advance_contiguous_lane_watermark_over_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with SealedWindowLedger(Path(temp_dir) / "ledger.sqlite") as ledger:
                self.open_visit(ledger)
                ledger.append_fragment(fragment("f1", 0, 2, HASH_A))
                ledger.append_fragment(fragment("f2", 2, 4, HASH_B))
                ledger.create_window(window("w1", 0, 2, (HASH_A,)))
                ledger.create_window(window("w2", 2, 4, (HASH_B,)))
                for lane in (Lane.ASR, Lane.OCR, Lane.VLM):
                    held = ledger.claim(lane, f"w1-{lane}", now_ns=10, lease_ns=100)
                    self.assertEqual("w1", held.window_id)
                    lease = ledger.claim(lane, f"w2-{lane}", now_ns=11, lease_ns=100)
                    self.assertEqual("w2", lease.window_id)
                    ledger.complete(lease, evidence("w2", lane, 2, 4, (HASH_B,), 20))
                self.assertIsNone(ledger.contiguous_watermark("session-1:visit:0001", Lane.VLM))

    def test_visual_text_window_has_no_asr_and_is_never_described_as_trimodal(self) -> None:
        planner = VisitWindowPlanner(session_id="session-1", source_context=SourceContext.PHONE_DAILY, fragments_per_window=2)
        first = fragment("f1", 0, 2, HASH_A)
        second = SealedFragment(
            fragment_id="f2",
            session_id="session-1",
            source_context=SourceContext.PHONE_DAILY,
            start_pts_ns=2,
            end_pts_ns=4,
            media_uri="local://media/f2.mkv",
            media_sha256=HASH_B,
            has_video=True,
            has_same_source_audio=False,
            pc_arrival_first_ns=3,
            pc_sealed_ns=5,
        )
        planner.ingest(first)
        planned = planner.ingest(second)
        self.assertEqual(FusionMode.VISUAL_TEXT_NO_AUDIO, planned.fusion_mode)
        self.assertEqual((Lane.OCR, Lane.VLM), planned.window.required_lanes)

    def test_fragment_hashes_preserve_pts_order_without_allowing_duplicates(self) -> None:
        ordered = window("ordered", 0, 4, (HASH_B, HASH_A))
        self.assertEqual((HASH_B, HASH_A), ordered.fragment_hashes)

    def test_audio_integrity_unresolved_is_not_mislabeled_as_no_audio(self) -> None:
        planner = VisitWindowPlanner(session_id="session-1", source_context=SourceContext.PHONE_DAILY)
        unresolved = SealedFragment(
            **{**fragment("f1", 0, 2, HASH_A).__dict__, "has_same_source_audio": False,
               "audio_status": AudioStatus.AUDIO_INTEGRITY_UNRESOLVED}
        )
        planned = planner.ingest(unresolved)
        self.assertEqual(FusionMode.EVIDENCE_INCOMPLETE, planned.fusion_mode)

    def test_old_visit_gap_does_not_block_current_visit_fusion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with SealedWindowLedger(Path(temp_dir) / "ledger.sqlite") as ledger:
                self.open_visit(ledger, "session-1:visit:0001", 0)
                self.open_visit(ledger, "session-1:visit:0002", 10)
                ledger.append_fragment(fragment("old", 0, 2, HASH_A))
                ledger.append_fragment(fragment("new", 10, 12, HASH_B))
                ledger.create_window(window("old", 0, 2, (HASH_A,)))
                ledger.create_window(window("new", 10, 12, (HASH_B,), visit_id="session-1:visit:0002"))
                for lane in (Lane.ASR, Lane.OCR, Lane.VLM):
                    lease = ledger.claim(lane, f"new-{lane}", now_ns=10, lease_ns=100)
                    if lease.window_id == "old":
                        lease = ledger.claim(lane, f"new-{lane}-parallel", now_ns=11, lease_ns=100)
                    ledger.complete(lease, evidence("new", lane, 10, 12, (HASH_B,), 20))
                candidates = ledger.fuse_ready(now_ns=30)
                self.assertEqual(["new"], [candidate.window_id for candidate in candidates])

    def test_terminal_failure_is_not_silently_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with SealedWindowLedger(Path(temp_dir) / "ledger.sqlite") as ledger:
                self.open_visit(ledger)
                ledger.append_fragment(fragment("f1", 0, 2, HASH_A))
                ledger.create_window(window("w1", 0, 2, (HASH_A,)))
                lease = ledger.claim(Lane.VLM, "worker", now_ns=10, lease_ns=100)
                self.assertEqual(
                    "UNRESOLVED",
                    ledger.fail(lease, error_code="MODEL_CRASH", now_ns=20, retry_delay_ns=5, max_attempts=1).value,
                )
                self.assertEqual("UNRESOLVED", ledger.job_state("w1", Lane.VLM))
                self.assertIsNone(ledger.claim(Lane.VLM, "worker-2", now_ns=100, lease_ns=10))


if __name__ == "__main__":
    unittest.main()
