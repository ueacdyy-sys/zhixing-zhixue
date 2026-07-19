from __future__ import annotations

import sys
import tempfile
import unittest
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.contracts import (  # noqa: E402
    AudioStatus,
    FusedCandidate,
    FusionMode,
    Lane,
    SealedFragment,
    SourceContext,
    VisitClosureReason,
)
from realtime_runtime.ledger import SealedWindowLedger  # noqa: E402
from realtime_runtime.notification import notification_eligibility  # noqa: E402
from realtime_runtime.orchestrator import RealtimeIngestor  # noqa: E402
from realtime_runtime.pipeline import RealtimePipeline  # noqa: E402
from realtime_runtime.worker_adapter import sealed_fragment_from_worker_event  # noqa: E402
from realtime_runtime.window_media import concat_manifest  # noqa: E402


def fragment(fragment_id: str, start: int, end: int, digest: str, *, audio: bool = True) -> SealedFragment:
    return SealedFragment(
        fragment_id=fragment_id,
        session_id="s1",
        source_context=SourceContext.PHONE_DAILY,
        start_pts_ns=start,
        end_pts_ns=end,
        media_uri=f"local://media/{fragment_id}.mkv",
        media_sha256=digest,
        has_video=True,
        has_same_source_audio=audio,
        audio_status=(AudioStatus.SAME_SOURCE_AUDIO_VERIFIED if audio else AudioStatus.NO_AUDIO_TRACK_VERIFIED),
        pc_arrival_first_ns=start + 1,
        pc_sealed_ns=end + 2,
    )


class RealtimeIngestorTests(unittest.TestCase):
    def test_append_only_transition_feed_consumes_only_due_swipes_once(self) -> None:
        from realtime_runtime.transitions import JsonlTransitionFeed

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transitions.jsonl"
            path.write_text(
                '{"event_type":"ContentTransitionCandidate","pc_monotonic_ns":20}\n'
                '{"event_type":"ContentTransitionCandidate","pc_monotonic_ns":50}\n',
                encoding="utf-8",
            )
            feed = JsonlTransitionFeed(path)
            self.assertFalse(feed.consume_before(19))
            self.assertTrue(feed.consume_before(20))
            self.assertFalse(feed.consume_before(20))
            self.assertTrue(feed.consume_before(55))

    def test_window_media_manifest_never_accepts_non_mp4_fragment(self) -> None:
        self.assertEqual("file 'C:/capture/a.mp4'\n", concat_manifest((Path("C:/capture/a.mp4"),)))
        with self.assertRaises(ValueError):
            concat_manifest((Path("C:/capture/a.mkv"),))

    def test_worker_event_requires_authorized_media_hash_and_explicit_audio_fact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            media = Path(temp_dir) / "fragments" / "fragment_000001.mkv"
            media.parent.mkdir()
            media.write_bytes(b"sealed-media")
            digest = hashlib.sha256(media.read_bytes()).hexdigest()
            result = sealed_fragment_from_worker_event(
                {
                    "event_type": "FragmentCommitted",
                    "session_id": "s1",
                    "fragment_index": 1,
                    "immutable_media_file": str(media),
                    "sha256": digest,
                    "audio_status": "NO_AUDIO_TRACK_VERIFIED",
                    "has_same_source_audio": False,
                    "start_pts_ns": 0,
                    "end_pts_ns": 2,
                    "pc_arrival_first_monotonic_ns": 1,
                    "pc_sealed_monotonic_ns": 3,
                },
                source_context=SourceContext.PHONE_DAILY,
                media_root=Path(temp_dir),
            )
            self.assertFalse(result.has_same_source_audio)
            self.assertEqual(AudioStatus.NO_AUDIO_TRACK_VERIFIED, result.audio_status)

    def test_pipeline_schedules_ledger_jobs_from_worker_commit_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "fragments" / "fragment_000001.mkv"
            media.parent.mkdir()
            media.write_bytes(b"sealed-media")
            event = {
                "event_type": "FragmentCommitted",
                "session_id": "s1",
                "fragment_index": 1,
                "immutable_media_file": str(media),
                "sha256": hashlib.sha256(media.read_bytes()).hexdigest(),
                "audio_status": "NO_AUDIO_TRACK_VERIFIED",
                "has_same_source_audio": False,
                "start_pts_ns": 0,
                "end_pts_ns": 2,
                "pc_arrival_first_monotonic_ns": 1,
                "pc_sealed_monotonic_ns": 3,
            }
            with SealedWindowLedger(root / "ledger.sqlite") as ledger:
                pipeline = RealtimePipeline(
                    ledger=ledger,
                    output_dir=root,
                    session_id="s1",
                    source_context=SourceContext.PHONE_DAILY,
                )
                pipeline.on_fragment_committed(event)
                self.assertTrue((root / "runtime_events.jsonl").is_file())
                self.assertEqual("PENDING", ledger.job_state("s1:window:000001", Lane.OCR))

    def test_transition_closes_old_visit_but_keeps_its_window_and_opens_new_visit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with SealedWindowLedger(Path(temp_dir) / "ledger.sqlite") as ledger:
                ingestor = RealtimeIngestor(ledger, session_id="s1", source_context=SourceContext.PHONE_DAILY)
                old = ingestor.ingest(fragment("f1", 0, 2, "a" * 64), now_ns=10)
                new = ingestor.ingest(fragment("f2", 2, 4, "b" * 64), now_ns=20, content_transition=True)

                self.assertEqual("s1:visit:0001", old.opened_visit_id)
                self.assertEqual("s1:visit:0001", new.closed_visit_id)
                self.assertEqual("s1:visit:0002", new.opened_visit_id)
                closed = ledger.visit("s1:visit:0001")
                self.assertEqual(2, closed.end_pts_ns)
                self.assertEqual(VisitClosureReason.CONTENT_SWITCH, closed.closure_reason)
                self.assertEqual("PENDING", ledger.job_state(old.planned_window.window.window_id, old.planned_window.window.required_lanes[0]))

    def test_notification_requires_current_visit_trimodal_evidence_and_freshness(self) -> None:
        candidate = FusedCandidate(
            window_id="w1",
            visit_id="s1:visit:0001",
            source_context=SourceContext.PHONE_DAILY,
            start_pts_ns=0,
            end_pts_ns=10,
            evidence_uris=("local://evidence/asr.json",),
            fused_at_ns=20,
            fusion_mode=FusionMode.TRIMODAL,
        )
        self.assertTrue(
            notification_eligibility(candidate, active_visit_id=candidate.visit_id, live_edge_pts_ns=12, maximum_lag_ns=3).eligible
        )
        self.assertFalse(
            notification_eligibility(candidate, active_visit_id="s1:visit:0002", live_edge_pts_ns=12, maximum_lag_ns=3).eligible
        )
        silent = FusedCandidate(**{**candidate.__dict__, "fusion_mode": FusionMode.VISUAL_TEXT_NO_AUDIO})
        self.assertFalse(
            notification_eligibility(silent, active_visit_id=silent.visit_id, live_edge_pts_ns=12, maximum_lag_ns=3).eligible
        )


if __name__ == "__main__":
    unittest.main()
