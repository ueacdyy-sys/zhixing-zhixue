from __future__ import annotations

import sys
import tempfile
import unittest
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.contracts import (  # noqa: E402
    AnalysisRouteLease,
    AnalysisRouteState,
    AudioStatus,
    ContractError,
    FusedCandidate,
    FusionMode,
    Lane,
    SealedFragment,
    SourceContext,
    VisitClosureReason,
)
from realtime_runtime.analysis_route import AnalysisRouteError, AnalysisRouteLedger  # noqa: E402
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
        audio_sync_error_ns=(0 if audio else None),
        audio_sync_sample_hash=("s" * 64 if audio else None),
        audio_max_allowed_sync_error_ns=(120_000_000 if audio else None),
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

    def test_worker_event_cannot_claim_verified_audio_without_packet_sync_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            media = Path(temp_dir) / "fragments" / "fragment_000001.mkv"
            media.parent.mkdir()
            media.write_bytes(b"sealed-media")
            event = {
                "event_type": "FragmentCommitted", "session_id": "s1", "fragment_index": 1,
                "immutable_media_file": str(media), "sha256": hashlib.sha256(media.read_bytes()).hexdigest(),
                "audio_status": "SAME_SOURCE_AUDIO_VERIFIED", "has_same_source_audio": True,
                "start_pts_ns": 0, "end_pts_ns": 2, "pc_arrival_first_monotonic_ns": 1, "pc_sealed_monotonic_ns": 3,
            }
            with self.assertRaisesRegex(ContractError, "worker_audio_sync_evidence_required"):
                sealed_fragment_from_worker_event(
                    event, source_context=SourceContext.PHONE_DAILY, media_root=Path(temp_dir)
                )

    def test_worker_event_preserves_bounded_packet_sync_evidence_on_the_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            media = Path(temp_dir) / "fragments" / "fragment_000001.mkv"
            media.parent.mkdir()
            media.write_bytes(b"sealed-media")
            result = sealed_fragment_from_worker_event(
                {
                    "event_type": "FragmentCommitted", "session_id": "s1", "fragment_index": 1,
                    "capture_generation": 8,
                    "immutable_media_file": str(media), "sha256": hashlib.sha256(media.read_bytes()).hexdigest(),
                    "audio_status": "SAME_SOURCE_AUDIO_VERIFIED", "has_same_source_audio": True,
                    "audio_sync_error_ns": 10, "audio_sync_sample_hash": "a" * 64,
                    "audio_max_allowed_sync_error_ns": 20,
                    "start_pts_ns": 0, "end_pts_ns": 2, "pc_arrival_first_monotonic_ns": 1, "pc_sealed_monotonic_ns": 3,
                },
                source_context=SourceContext.PHONE_DAILY,
                media_root=Path(temp_dir),
            )

        self.assertEqual(10, result.audio_sync_error_ns)
        self.assertEqual("a" * 64, result.audio_sync_sample_hash)
        self.assertEqual(20, result.audio_max_allowed_sync_error_ns)
        self.assertEqual(8, result.capture_generation)

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

    def test_pipeline_refuses_a_fragment_when_its_v2_route_epoch_is_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "fragments" / "fragment_000001.mkv"
            media.parent.mkdir()
            media.write_bytes(b"sealed-media")
            event = {
                "event_type": "FragmentCommitted", "session_id": "s1", "fragment_index": 1,
                "immutable_media_file": str(media), "sha256": hashlib.sha256(media.read_bytes()).hexdigest(),
                "audio_status": "NO_AUDIO_TRACK_VERIFIED", "has_same_source_audio": False,
                "start_pts_ns": 0, "end_pts_ns": 2, "pc_arrival_first_monotonic_ns": 1, "pc_sealed_monotonic_ns": 3,
            }
            lease = AnalysisRouteLease(
                lease_id="route-1", learner_id="learner-1", session_id="s1", capture_consent_id="consent-1",
                consent_generation=1, route_epoch=2, state=AnalysisRouteState.PC_LOCAL_ACTIVE,
                owner_endpoint_id="pc-1", opened_receipt_hash="a" * 64, student_confirmation_hash="b" * 64,
                issued_elapsed_ns=0, last_renewed_elapsed_ns=0, expires_elapsed_ns=10_000,
            )
            with SealedWindowLedger(root / "ledger.sqlite") as ledger, AnalysisRouteLedger(root / "route.sqlite") as routes:
                routes.open(lease, now_elapsed_ns=1)
                pipeline = RealtimePipeline(
                    ledger=ledger, output_dir=root, session_id="s1", source_context=SourceContext.PHONE_DAILY,
                    route_authorizer=lambda: routes.assert_pc_ingress_authorized(
                        lease_id="route-1", learner_id="learner-1", session_id="s1", capture_consent_id="consent-1",
                        consent_generation=1, route_epoch=1, endpoint_id="pc-1", now_elapsed_ns=2,
                    ),
                )
                with self.assertRaisesRegex(AnalysisRouteError, "route_owner_or_epoch_denied"):
                    pipeline.on_fragment_committed(event)
                self.assertFalse((root / "runtime_events.jsonl").exists())

    def test_pipeline_rejects_stale_capture_generation_before_ledger_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "fragments" / "fragment_000001.mkv"
            media.parent.mkdir()
            media.write_bytes(b"sealed-media")
            event = {
                "event_type": "FragmentCommitted", "session_id": "s1", "fragment_index": 1,
                "capture_generation": 4,
                "immutable_media_file": str(media), "sha256": hashlib.sha256(media.read_bytes()).hexdigest(),
                "audio_status": "NO_AUDIO_TRACK_VERIFIED", "has_same_source_audio": False,
                "start_pts_ns": 0, "end_pts_ns": 2, "pc_arrival_first_monotonic_ns": 1, "pc_sealed_monotonic_ns": 3,
            }
            with SealedWindowLedger(root / "ledger.sqlite") as ledger:
                pipeline = RealtimePipeline(
                    ledger=ledger, output_dir=root, session_id="s1", source_context=SourceContext.PHONE_DAILY,
                    expected_capture_generation=5,
                )
                with self.assertRaisesRegex(ContractError, "worker_capture_generation_mismatch"):
                    pipeline.on_fragment_committed(event)
                count = ledger._connection.execute("SELECT COUNT(*) FROM fragments").fetchone()[0]

        self.assertEqual(0, count)

    def test_pipeline_persists_matching_l0_audio_telemetry_without_promoting_audio_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "fragments" / "fragment_000001.mkv"
            media.parent.mkdir()
            media.write_bytes(b"sealed-media")
            payload = {
                "snapshot_id": "audio-l0-1",
                "capture_generation": 7,
                "capture_path": "PLAYBACK",
                "status": "CAPTURE_ACTIVE_UNVERIFIED",
                "application_package_id": "tv.danmaku.bili",
                "restriction": "NONE",
                "failure_code": None,
                "video_pts_start_us": 1_000,
                "video_pts_end_us": 2_000,
                "audio_pts_start_us": 1_000,
                "audio_pts_end_us": 2_000,
                "session_epoch_id": "rtsp-11",
                "clock_domain": "ANDROID_ELAPSED_REALTIME_MONOTONIC",
                "anchor_elapsed_realtime_ns": 100,
                "sync_error_us": None,
                "recovery_attempt": 0,
            }
            canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            journal = root / "capture.audio-l0.jsonl"
            journal.write_text(
                json.dumps(
                    {
                        "event_type": "CaptureAudioCapabilityObservedL0",
                        "capture_session_id": "s1",
                        "payload": payload,
                        "payload_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                    }
                ) + "\n",
                encoding="utf-8",
            )
            event = {
                "event_type": "FragmentCommitted", "session_id": "s1", "fragment_index": 1,
                "capture_generation": 7,
                "immutable_media_file": str(media), "sha256": hashlib.sha256(media.read_bytes()).hexdigest(),
                "audio_status": "NO_AUDIO_TRACK_VERIFIED", "has_same_source_audio": False,
                "start_pts_ns": 1_000_000, "end_pts_ns": 2_000_000,
                "pc_arrival_first_monotonic_ns": 1, "pc_sealed_monotonic_ns": 3,
            }
            with SealedWindowLedger(root / "ledger.sqlite") as ledger:
                pipeline = RealtimePipeline(
                    ledger=ledger, output_dir=root, session_id="s1", source_context=SourceContext.PHONE_DAILY,
                    expected_capture_generation=7, audio_telemetry_journal=journal,
                )
                pipeline.on_fragment_committed(event)
                reference = ledger._connection.execute(
                    "SELECT snapshot_id, capture_path, status FROM fragment_l0_audio_telemetry_refs"
                ).fetchone()
                audio_status = ledger._connection.execute(
                    "SELECT audio_status FROM fragments WHERE fragment_id = 's1:fragment:000001'"
                ).fetchone()["audio_status"]

        self.assertEqual(("audio-l0-1", "PLAYBACK", "CAPTURE_ACTIVE_UNVERIFIED"), tuple(reference))
        self.assertEqual("NO_AUDIO_TRACK_VERIFIED", audio_status)

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
