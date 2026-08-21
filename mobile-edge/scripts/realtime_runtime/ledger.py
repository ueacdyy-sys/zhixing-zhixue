"""SQLite WAL ledger for sealed media, retryable lane work, and PTS-safe fusion."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .contracts import (
    ContractError,
    FusionMode,
    FusedCandidate,
    JobLease,
    JobState,
    Lane,
    LaneEvidence,
    QualityStatus,
    SealedFragment,
    SemanticWindow,
    SourceContext,
    Visit,
    VisitClosureReason,
    WindowDescriptor,
)
from .l0_audio_telemetry import L0AudioTelemetryReference


class SealedWindowLedger:
    """The durable replacement for in-memory latest-window queues.

    Media stays in the file store; this database only stores immutable media
    identities, explicit task state, and evidence references.  A lease never
    removes a task.  It either becomes COMPLETE with matching evidence or
    returns to RETRY_WAIT after expiration.
    """

    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(database_path), isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._create_schema()
        self._backfill_fused_candidate_events()

    def __enter__(self) -> "SealedWindowLedger":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS fragments (
                fragment_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                source_context TEXT NOT NULL,
                start_pts_ns INTEGER NOT NULL,
                end_pts_ns INTEGER NOT NULL,
                media_uri TEXT NOT NULL,
                media_sha256 TEXT NOT NULL UNIQUE,
                has_video INTEGER NOT NULL,
                has_same_source_audio INTEGER NOT NULL,
                audio_status TEXT,
                capture_generation INTEGER,
                audio_sync_error_ns INTEGER,
                audio_sync_sample_hash TEXT,
                audio_max_allowed_sync_error_ns INTEGER,
                pc_arrival_first_ns INTEGER NOT NULL,
                pc_sealed_ns INTEGER NOT NULL,
                gap_before INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS semantic_windows (
                window_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                visit_id TEXT NOT NULL,
                source_context TEXT NOT NULL,
                start_pts_ns INTEGER NOT NULL,
                end_pts_ns INTEGER NOT NULL,
                fragment_hashes_json TEXT NOT NULL,
                required_lanes_json TEXT NOT NULL,
                fusion_mode TEXT NOT NULL DEFAULT 'TRIMODAL',
                created_ns INTEGER NOT NULL DEFAULT 0,
                fused_at_ns INTEGER
            );
            CREATE TABLE IF NOT EXISTS fragment_l0_audio_telemetry_refs (
                fragment_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                session_epoch_id TEXT NOT NULL,
                capture_path TEXT NOT NULL,
                status TEXT NOT NULL,
                restriction TEXT NOT NULL,
                video_pts_start_ns INTEGER NOT NULL,
                video_pts_end_ns INTEGER NOT NULL,
                PRIMARY KEY(fragment_id, snapshot_id),
                FOREIGN KEY(fragment_id) REFERENCES fragments(fragment_id)
            );
            CREATE TABLE IF NOT EXISTS visits (
                visit_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                source_context TEXT NOT NULL,
                start_pts_ns INTEGER NOT NULL,
                end_pts_ns INTEGER,
                closure_reason TEXT
            );
            CREATE TABLE IF NOT EXISTS jobs (
                window_id TEXT NOT NULL,
                lane TEXT NOT NULL,
                state TEXT NOT NULL,
                attempt_id INTEGER NOT NULL DEFAULT 0,
                worker_id TEXT,
                lease_deadline_ns INTEGER,
                next_eligible_ns INTEGER NOT NULL DEFAULT 0,
                last_error_code TEXT,
                terminal_ns INTEGER,
                PRIMARY KEY(window_id, lane),
                FOREIGN KEY(window_id) REFERENCES semantic_windows(window_id)
            );
            CREATE TABLE IF NOT EXISTS lane_evidence (
                window_id TEXT NOT NULL,
                lane TEXT NOT NULL,
                coverage_start_pts_ns INTEGER NOT NULL,
                coverage_end_pts_ns INTEGER NOT NULL,
                source_fragment_hashes_json TEXT NOT NULL,
                quality_status TEXT NOT NULL,
                artifact_uri TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                started_ns INTEGER NOT NULL,
                completed_ns INTEGER NOT NULL,
                PRIMARY KEY(window_id, lane),
                FOREIGN KEY(window_id, lane) REFERENCES jobs(window_id, lane)
            );
            CREATE TABLE IF NOT EXISTS fused_candidate_events (
                window_id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                source_context TEXT NOT NULL,
                start_pts_ns INTEGER NOT NULL,
                end_pts_ns INTEGER NOT NULL,
                evidence_uris_json TEXT NOT NULL,
                fusion_mode TEXT NOT NULL,
                fused_at_ns INTEGER NOT NULL,
                classification TEXT NOT NULL,
                FOREIGN KEY(window_id) REFERENCES semantic_windows(window_id)
            );
            CREATE INDEX IF NOT EXISTS jobs_claim_index
                ON jobs(lane, state, next_eligible_ns, lease_deadline_ns);
            CREATE INDEX IF NOT EXISTS windows_session_index
                ON semantic_windows(session_id, start_pts_ns, end_pts_ns);
            CREATE INDEX IF NOT EXISTS fragment_l0_audio_telemetry_fragment_index
                ON fragment_l0_audio_telemetry_refs(fragment_id, video_pts_start_ns, video_pts_end_ns);
            CREATE INDEX IF NOT EXISTS fused_candidate_events_pts_index
                ON fused_candidate_events(start_pts_ns, end_pts_ns, window_id);
            """
        )
        self._ensure_column("semantic_windows", "fusion_mode", "TEXT NOT NULL DEFAULT 'TRIMODAL'")
        self._ensure_column("semantic_windows", "created_ns", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("jobs", "last_error_code", "TEXT")
        self._ensure_column("jobs", "terminal_ns", "INTEGER")
        self._ensure_column("fragments", "audio_status", "TEXT")
        self._ensure_column("fragments", "capture_generation", "INTEGER")
        self._ensure_column("fragments", "audio_sync_error_ns", "INTEGER")
        self._ensure_column("fragments", "audio_sync_sample_hash", "TEXT")
        self._ensure_column("fragments", "audio_max_allowed_sync_error_ns", "INTEGER")

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {str(row["name"]) for row in self._connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _dump_lanes(lanes: tuple[Lane, ...]) -> str:
        return json.dumps([item.value for item in lanes], separators=(",", ":"))

    @staticmethod
    def _dump_hashes(hashes: tuple[str, ...]) -> str:
        return json.dumps(list(hashes), separators=(",", ":"))

    def _insert_fused_candidate_event(self, candidate: FusedCandidate) -> None:
        self._connection.execute(
            """
            INSERT OR IGNORE INTO fused_candidate_events(
                window_id, visit_id, source_context, start_pts_ns, end_pts_ns,
                evidence_uris_json, fusion_mode, fused_at_ns, classification
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.window_id,
                candidate.visit_id,
                candidate.source_context.value,
                candidate.start_pts_ns,
                candidate.end_pts_ns,
                json.dumps(candidate.evidence_uris, separators=(",", ":")),
                candidate.fusion_mode.value,
                candidate.fused_at_ns,
                candidate.classification,
            ),
        )

    def _backfill_fused_candidate_events(self) -> None:
        """Upgrade old ledgers only from already verified, fully fused windows."""

        windows = self._connection.execute(
            """
            SELECT semantic_windows.* FROM semantic_windows
            LEFT JOIN fused_candidate_events USING(window_id)
            WHERE semantic_windows.fused_at_ns IS NOT NULL
              AND fused_candidate_events.window_id IS NULL
            ORDER BY semantic_windows.start_pts_ns, semantic_windows.end_pts_ns, semantic_windows.window_id
            """
        ).fetchall()
        with self._connection:
            for window in windows:
                required_lanes = tuple(Lane(item) for item in json.loads(window["required_lanes_json"]))
                evidence = self._connection.execute(
                    "SELECT * FROM lane_evidence WHERE window_id = ? ORDER BY lane", (window["window_id"],)
                ).fetchall()
                expected_hashes = tuple(json.loads(window["fragment_hashes_json"]))
                if len(evidence) != len(required_lanes) or any(
                    row["quality_status"] != QualityStatus.FUSION_ELIGIBLE.value
                    or tuple(json.loads(row["source_fragment_hashes_json"])) != expected_hashes
                    or row["coverage_start_pts_ns"] != window["start_pts_ns"]
                    or row["coverage_end_pts_ns"] != window["end_pts_ns"]
                    for row in evidence
                ):
                    continue
                self._insert_fused_candidate_event(
                    FusedCandidate(
                        window_id=str(window["window_id"]),
                        visit_id=str(window["visit_id"]),
                        source_context=SourceContext(window["source_context"]),
                        start_pts_ns=int(window["start_pts_ns"]),
                        end_pts_ns=int(window["end_pts_ns"]),
                        evidence_uris=tuple(str(row["artifact_uri"]) for row in evidence),
                        fused_at_ns=int(window["fused_at_ns"]),
                        fusion_mode=FusionMode(window["fusion_mode"]),
                    )
                )

    def append_fragment(self, fragment: SealedFragment) -> None:
        self._connection.execute(
            """
            INSERT INTO fragments(
                fragment_id, session_id, source_context, start_pts_ns, end_pts_ns, media_uri, media_sha256,
                has_video, has_same_source_audio, audio_status, capture_generation, audio_sync_error_ns, audio_sync_sample_hash,
                audio_max_allowed_sync_error_ns, pc_arrival_first_ns, pc_sealed_ns, gap_before
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fragment.fragment_id,
                fragment.session_id,
                fragment.source_context.value,
                fragment.start_pts_ns,
                fragment.end_pts_ns,
                fragment.media_uri,
                fragment.media_sha256,
                int(fragment.has_video),
                int(fragment.has_same_source_audio),
                fragment.audio_status.value if fragment.audio_status else None,
                fragment.capture_generation,
                fragment.audio_sync_error_ns,
                fragment.audio_sync_sample_hash,
                fragment.audio_max_allowed_sync_error_ns,
                fragment.pc_arrival_first_ns,
                fragment.pc_sealed_ns,
                int(fragment.gap_before),
            ),
        )

    def append_l0_audio_telemetry_refs(
        self,
        fragment_id: str,
        references: tuple[L0AudioTelemetryReference, ...],
    ) -> None:
        """Attach already validated handset telemetry without upgrading its L0 status."""

        fragment = self._connection.execute(
            "SELECT start_pts_ns, end_pts_ns FROM fragments WHERE fragment_id = ?", (fragment_id,)
        ).fetchone()
        if fragment is None:
            raise ValueError("audio_telemetry_fragment_missing")
        fragment_start = int(fragment["start_pts_ns"])
        fragment_end = int(fragment["end_pts_ns"])
        for reference in references:
            if reference.video_pts_start_ns > fragment_end or reference.video_pts_end_ns < fragment_start:
                raise ValueError("audio_telemetry_reference_outside_fragment")
            existing = self._connection.execute(
                """
                SELECT payload_sha256, session_epoch_id, capture_path, status, restriction,
                       video_pts_start_ns, video_pts_end_ns
                FROM fragment_l0_audio_telemetry_refs
                WHERE fragment_id = ? AND snapshot_id = ?
                """,
                (fragment_id, reference.snapshot_id),
            ).fetchone()
            values = (
                reference.payload_sha256,
                reference.session_epoch_id,
                reference.capture_path,
                reference.status,
                reference.restriction,
                reference.video_pts_start_ns,
                reference.video_pts_end_ns,
            )
            if existing is not None:
                if tuple(existing) != values:
                    raise ValueError("audio_telemetry_reference_conflict")
                continue
            self._connection.execute(
                """
                INSERT INTO fragment_l0_audio_telemetry_refs(
                    fragment_id, snapshot_id, payload_sha256, session_epoch_id,
                    capture_path, status, restriction, video_pts_start_ns, video_pts_end_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (fragment_id, reference.snapshot_id, *values),
            )

    def open_visit(self, visit: Visit) -> None:
        self._connection.execute(
            """
            INSERT INTO visits(visit_id, session_id, source_context, start_pts_ns, end_pts_ns, closure_reason)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                visit.visit_id,
                visit.session_id,
                visit.source_context.value,
                visit.start_pts_ns,
                visit.end_pts_ns,
                visit.closure_reason.value if visit.closure_reason else None,
            ),
        )

    def close_visit(self, visit_id: str, *, end_pts_ns: int, reason: VisitClosureReason) -> None:
        updated = self._connection.execute(
            """
            UPDATE visits SET end_pts_ns = ?, closure_reason = ?
            WHERE visit_id = ? AND end_pts_ns IS NULL AND start_pts_ns < ?
            """,
            (end_pts_ns, reason.value, visit_id, end_pts_ns),
        )
        if updated.rowcount != 1:
            raise ValueError("visit_not_open_or_invalid_closure")

    def visit(self, visit_id: str) -> Visit | None:
        row = self._connection.execute("SELECT * FROM visits WHERE visit_id = ?", (visit_id,)).fetchone()
        if row is None:
            return None
        return Visit(
            visit_id=str(row["visit_id"]),
            session_id=str(row["session_id"]),
            source_context=SourceContext(row["source_context"]),
            start_pts_ns=int(row["start_pts_ns"]),
            end_pts_ns=int(row["end_pts_ns"]) if row["end_pts_ns"] is not None else None,
            closure_reason=VisitClosureReason(row["closure_reason"]) if row["closure_reason"] else None,
        )

    def create_window(self, window: SemanticWindow, *, fusion_mode: FusionMode | None = None, created_ns: int = 0) -> None:
        if created_ns < 0:
            raise ValueError("window_created_ns_invalid")
        visit = self._connection.execute("SELECT * FROM visits WHERE visit_id = ?", (window.visit_id,)).fetchone()
        if visit is None:
            raise ContractError("window_references_unknown_visit")
        if visit["session_id"] != window.session_id or visit["source_context"] != window.source_context.value:
            raise ContractError("window_visit_scope_mismatch")
        if window.start_pts_ns < visit["start_pts_ns"] or (
            visit["end_pts_ns"] is not None and window.end_pts_ns > visit["end_pts_ns"]
        ):
            raise ContractError("window_outside_visit_boundary")
        resolved_mode = fusion_mode or (
            FusionMode.TRIMODAL if Lane.ASR in window.required_lanes else FusionMode.VISUAL_TEXT_NO_AUDIO
        )
        expected_lanes = (
            (Lane.OCR, Lane.VLM)
            if resolved_mode is FusionMode.VISUAL_TEXT_NO_AUDIO
            else (Lane.ASR, Lane.OCR, Lane.VLM)
        )
        if window.required_lanes != expected_lanes:
            raise ContractError("window_lanes_do_not_match_fusion_mode")
        placeholders = ",".join("?" for _ in window.fragment_hashes)
        rows = self._connection.execute(
            f"SELECT media_sha256, session_id, source_context FROM fragments WHERE media_sha256 IN ({placeholders})",
            window.fragment_hashes,
        ).fetchall()
        if len(rows) != len(window.fragment_hashes):
            raise ContractError("window_references_unknown_fragment")
        if any(row["session_id"] != window.session_id or row["source_context"] != window.source_context.value for row in rows):
            raise ContractError("window_fragment_scope_mismatch")
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO semantic_windows(
                    window_id, session_id, visit_id, source_context, start_pts_ns, end_pts_ns,
                    fragment_hashes_json, required_lanes_json, fusion_mode, created_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    window.window_id,
                    window.session_id,
                    window.visit_id,
                    window.source_context.value,
                    window.start_pts_ns,
                    window.end_pts_ns,
                    self._dump_hashes(window.fragment_hashes),
                    self._dump_lanes(window.required_lanes),
                    resolved_mode.value,
                    created_ns,
                ),
            )
            self._connection.executemany(
                "INSERT INTO jobs(window_id, lane, state) VALUES (?, ?, ?)",
                [(window.window_id, lane.value, JobState.PENDING.value) for lane in window.required_lanes],
            )

    def claim(self, lane: Lane, worker_id: str, *, now_ns: int, lease_ns: int) -> JobLease | None:
        if not worker_id or lease_ns <= 0:
            raise ValueError("claim_configuration_invalid")
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                """
                SELECT jobs.window_id, jobs.attempt_id
                FROM jobs
                JOIN semantic_windows ON semantic_windows.window_id = jobs.window_id
                WHERE jobs.lane = ?
                  AND jobs.state IN (?, ?)
                  AND jobs.next_eligible_ns <= ?
                ORDER BY semantic_windows.start_pts_ns, semantic_windows.end_pts_ns, jobs.window_id
                LIMIT 1
                """,
                (lane.value, JobState.PENDING.value, JobState.RETRY_WAIT.value, now_ns),
            ).fetchone()
            if row is None:
                self._connection.execute("COMMIT")
                return None
            attempt_id = int(row["attempt_id"]) + 1
            deadline = now_ns + lease_ns
            self._connection.execute(
                """
                UPDATE jobs SET state = ?, attempt_id = ?, worker_id = ?, lease_deadline_ns = ?
                WHERE window_id = ? AND lane = ?
                """,
                (JobState.LEASED.value, attempt_id, worker_id, deadline, row["window_id"], lane.value),
            )
            self._connection.execute("COMMIT")
            return JobLease(row["window_id"], lane, worker_id, attempt_id, deadline)
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise

    def recover_expired_leases(self, *, now_ns: int) -> int:
        result = self._connection.execute(
            """
            UPDATE jobs
            SET state = ?, worker_id = NULL, lease_deadline_ns = NULL, next_eligible_ns = ?
            WHERE state = ? AND lease_deadline_ns < ?
            """,
            (JobState.RETRY_WAIT.value, now_ns, JobState.LEASED.value, now_ns),
        )
        return int(result.rowcount)

    def fail(
        self,
        lease: JobLease,
        *,
        error_code: str,
        now_ns: int,
        retry_delay_ns: int,
        max_attempts: int,
    ) -> JobState:
        if not error_code or now_ns < 0 or retry_delay_ns < 0 or max_attempts < 1:
            raise ValueError("failure_configuration_invalid")
        with self._connection:
            job = self._connection.execute(
                "SELECT * FROM jobs WHERE window_id = ? AND lane = ?", (lease.window_id, lease.lane.value)
            ).fetchone()
            if job is None or job["state"] != JobState.LEASED.value:
                raise ValueError("job_not_leased")
            if job["worker_id"] != lease.worker_id or job["attempt_id"] != lease.attempt_id:
                raise ValueError("lease_not_current")
            terminal = lease.attempt_id >= max_attempts
            state = JobState.UNRESOLVED if terminal else JobState.RETRY_WAIT
            self._connection.execute(
                """
                UPDATE jobs
                SET state = ?, worker_id = NULL, lease_deadline_ns = NULL,
                    next_eligible_ns = ?, last_error_code = ?, terminal_ns = ?
                WHERE window_id = ? AND lane = ?
                """,
                (
                    state.value,
                    now_ns if terminal else now_ns + retry_delay_ns,
                    error_code,
                    now_ns if terminal else None,
                    lease.window_id,
                    lease.lane.value,
                ),
            )
        return state

    def complete(self, lease: JobLease, evidence: LaneEvidence) -> None:
        if evidence.window_id != lease.window_id or evidence.lane != lease.lane:
            raise ValueError("evidence_lease_mismatch")
        window = self._connection.execute(
            "SELECT * FROM semantic_windows WHERE window_id = ?", (lease.window_id,)
        ).fetchone()
        if window is None:
            raise ValueError("unknown_window")
        required_hashes = tuple(json.loads(window["fragment_hashes_json"]))
        if (
            evidence.coverage_start_pts_ns != window["start_pts_ns"]
            or evidence.coverage_end_pts_ns != window["end_pts_ns"]
            or evidence.source_fragment_hashes != required_hashes
            or evidence.quality_status != QualityStatus.FUSION_ELIGIBLE
        ):
            raise ValueError("evidence_does_not_cover_sealed_window")
        with self._connection:
            job = self._connection.execute(
                "SELECT * FROM jobs WHERE window_id = ? AND lane = ?", (lease.window_id, lease.lane.value)
            ).fetchone()
            if job is None or job["state"] != JobState.LEASED.value:
                raise ValueError("job_not_leased")
            if job["worker_id"] != lease.worker_id or job["attempt_id"] != lease.attempt_id:
                raise ValueError("lease_not_current")
            self._connection.execute(
                """
                INSERT INTO lane_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(window_id, lane) DO UPDATE SET
                    coverage_start_pts_ns=excluded.coverage_start_pts_ns,
                    coverage_end_pts_ns=excluded.coverage_end_pts_ns,
                    source_fragment_hashes_json=excluded.source_fragment_hashes_json,
                    quality_status=excluded.quality_status,
                    artifact_uri=excluded.artifact_uri,
                    artifact_sha256=excluded.artifact_sha256,
                    started_ns=excluded.started_ns,
                    completed_ns=excluded.completed_ns
                """,
                (
                    evidence.window_id,
                    evidence.lane.value,
                    evidence.coverage_start_pts_ns,
                    evidence.coverage_end_pts_ns,
                    self._dump_hashes(evidence.source_fragment_hashes),
                    evidence.quality_status.value,
                    evidence.artifact_uri,
                    evidence.artifact_sha256,
                    evidence.started_ns,
                    evidence.completed_ns,
                ),
            )
            self._connection.execute(
                """
                UPDATE jobs SET state = ?, worker_id = NULL, lease_deadline_ns = NULL
                WHERE window_id = ? AND lane = ?
                """,
                (JobState.COMPLETE.value, lease.window_id, lease.lane.value),
            )

    def job_state(self, window_id: str, lane: Lane) -> str | None:
        row = self._connection.execute(
            "SELECT state FROM jobs WHERE window_id = ? AND lane = ?", (window_id, lane.value)
        ).fetchone()
        return str(row["state"]) if row else None

    def window_media(self, window_id: str) -> tuple[str, ...]:
        row = self._connection.execute(
            "SELECT fragment_hashes_json FROM semantic_windows WHERE window_id = ?", (window_id,)
        ).fetchone()
        if row is None:
            raise ValueError("unknown_window")
        hashes = tuple(json.loads(row["fragment_hashes_json"]))
        placeholders = ",".join("?" for _ in hashes)
        rows = self._connection.execute(
            f"SELECT media_sha256, media_uri FROM fragments WHERE media_sha256 IN ({placeholders})", hashes
        ).fetchall()
        by_hash = {str(item["media_sha256"]): str(item["media_uri"]) for item in rows}
        if set(by_hash) != set(hashes):
            raise ValueError("window_media_missing")
        return tuple(by_hash[item] for item in hashes)

    def window_descriptor(self, window_id: str) -> WindowDescriptor:
        """Return the exact sealed inputs available to a leased lane worker."""

        row = self._connection.execute(
            "SELECT * FROM semantic_windows WHERE window_id = ?", (window_id,)
        ).fetchone()
        if row is None:
            raise ValueError("unknown_window")
        return WindowDescriptor(
            window_id=str(row["window_id"]),
            visit_id=str(row["visit_id"]),
            source_context=SourceContext(row["source_context"]),
            start_pts_ns=int(row["start_pts_ns"]),
            end_pts_ns=int(row["end_pts_ns"]),
            fragment_hashes=tuple(json.loads(row["fragment_hashes_json"])),
            media_uris=self.window_media(window_id),
        )

    def contiguous_watermark(self, visit_id: str, lane: Lane) -> int | None:
        windows = self._connection.execute(
            "SELECT * FROM semantic_windows WHERE visit_id = ? ORDER BY start_pts_ns, end_pts_ns, window_id",
            (visit_id,),
        ).fetchall()
        watermark: int | None = None
        for window in windows:
            if FusionMode(window["fusion_mode"]) is FusionMode.EVIDENCE_INCOMPLETE:
                continue
            lanes = tuple(json.loads(window["required_lanes_json"]))
            if lane.value not in lanes:
                continue
            evidence = self._connection.execute(
                "SELECT * FROM lane_evidence WHERE window_id = ? AND lane = ?", (window["window_id"], lane.value)
            ).fetchone()
            if evidence is None or evidence["quality_status"] != QualityStatus.FUSION_ELIGIBLE.value:
                return watermark
            if evidence["coverage_start_pts_ns"] != window["start_pts_ns"] or evidence["coverage_end_pts_ns"] != window["end_pts_ns"]:
                return watermark
            if tuple(json.loads(evidence["source_fragment_hashes_json"])) != tuple(json.loads(window["fragment_hashes_json"])):
                return watermark
            if watermark is None:
                watermark = int(window["end_pts_ns"])
            elif int(window["start_pts_ns"]) <= watermark:
                watermark = max(watermark, int(window["end_pts_ns"]))
            else:
                return watermark
        return watermark

    def fuse_ready(self, *, now_ns: int) -> list[FusedCandidate]:
        candidates: list[FusedCandidate] = []
        windows = self._connection.execute(
            "SELECT * FROM semantic_windows WHERE fused_at_ns IS NULL ORDER BY start_pts_ns, end_pts_ns, window_id"
        ).fetchall()
        for window in windows:
            # An audio-integrity gap is retained as an explicit incomplete
            # window.  It must not be fused, but it also must not permanently
            # suppress a later independent window whose three lanes cover the
            # exact same PTS/hash range.  Candidates never combine evidence
            # across this gap.
            if FusionMode(window["fusion_mode"]) is FusionMode.EVIDENCE_INCOMPLETE:
                continue
            required_lanes = tuple(Lane(item) for item in json.loads(window["required_lanes_json"]))
            evidence = self._connection.execute(
                "SELECT * FROM lane_evidence WHERE window_id = ? ORDER BY lane", (window["window_id"],)
            ).fetchall()
            if len(evidence) != len(required_lanes):
                continue
            expected_hashes = tuple(json.loads(window["fragment_hashes_json"]))
            if any(
                row["quality_status"] != QualityStatus.FUSION_ELIGIBLE.value
                or tuple(json.loads(row["source_fragment_hashes_json"])) != expected_hashes
                or row["coverage_start_pts_ns"] != window["start_pts_ns"]
                or row["coverage_end_pts_ns"] != window["end_pts_ns"]
                for row in evidence
            ):
                continue
            candidate = FusedCandidate(
                window_id=str(window["window_id"]),
                visit_id=str(window["visit_id"]),
                source_context=SourceContext(window["source_context"]),
                start_pts_ns=int(window["start_pts_ns"]),
                end_pts_ns=int(window["end_pts_ns"]),
                evidence_uris=tuple(str(row["artifact_uri"]) for row in evidence),
                fused_at_ns=now_ns,
                fusion_mode=FusionMode(window["fusion_mode"]),
            )
            with self._connection:
                updated = self._connection.execute(
                    "UPDATE semantic_windows SET fused_at_ns = ? WHERE window_id = ? AND fused_at_ns IS NULL",
                    (now_ns, window["window_id"]),
                )
                if updated.rowcount:
                    self._insert_fused_candidate_event(candidate)
            if updated.rowcount:
                candidates.append(candidate)
        return candidates

    def fused_candidate_events(self) -> list[FusedCandidate]:
        """Read the durable fused-candidate outbox in media PTS order."""

        rows = self._connection.execute(
            "SELECT * FROM fused_candidate_events ORDER BY start_pts_ns, end_pts_ns, window_id"
        ).fetchall()
        return [
            FusedCandidate(
                window_id=str(row["window_id"]),
                visit_id=str(row["visit_id"]),
                source_context=SourceContext(row["source_context"]),
                start_pts_ns=int(row["start_pts_ns"]),
                end_pts_ns=int(row["end_pts_ns"]),
                evidence_uris=tuple(json.loads(row["evidence_uris_json"])),
                fused_at_ns=int(row["fused_at_ns"]),
                fusion_mode=FusionMode(row["fusion_mode"]),
                classification=str(row["classification"]),
            )
            for row in rows
        ]

    def fused_candidate_l0_inputs(self, candidate: FusedCandidate) -> tuple[str, tuple[str, ...]]:
        """Expose verified legacy inputs solely to the v2 L0 read-only adapter.

        This intentionally returns hashes rather than interpreting a candidate
        as a learning conclusion. The v2 adapter remains unable to create L1.
        """

        window = self._connection.execute(
            """
            SELECT window_id, visit_id FROM semantic_windows
            WHERE window_id = ? AND visit_id = ?
            """,
            (candidate.window_id, candidate.visit_id),
        ).fetchone()
        if window is None:
            raise ValueError("fused_candidate_window_missing")
        visit = self._connection.execute("SELECT session_id FROM visits WHERE visit_id = ?", (candidate.visit_id,)).fetchone()
        if visit is None:
            raise ValueError("fused_candidate_visit_missing")
        evidence = self._connection.execute(
            "SELECT artifact_uri, artifact_sha256 FROM lane_evidence WHERE window_id = ? ORDER BY lane",
            (candidate.window_id,),
        ).fetchall()
        uris = tuple(str(row["artifact_uri"]) for row in evidence)
        hashes = tuple(str(row["artifact_sha256"]) for row in evidence)
        if uris != candidate.evidence_uris or not hashes or any(len(item) != 64 for item in hashes):
            raise ValueError("fused_candidate_l0_evidence_mismatch")
        return str(visit["session_id"]), hashes
