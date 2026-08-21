"""Durable v2 L0 fact, watermark and scope-revision ledger.

This ledger intentionally has no candidate-card or notification dependency.
It stores immutable evidence facts and admission intents only; a later package
outbox is the sole component allowed to create an L1 delivery side effect.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3

from .contracts import (
    LateFactAdmission,
    L0HeartbeatState,
    L0SemanticHeartbeat,
    RealtimeSemanticFact,
    SemanticScope,
)


class SemanticLedgerError(ValueError):
    """Raised when an immutable v2 evidence relation cannot be proven."""


def _stable_hash(value: object) -> str:
    source = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


class RealtimeSemanticLedger:
    """SQLite ledger for one or more learner-scoped realtime sessions."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def __enter__(self) -> "RealtimeSemanticLedger":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS semantic_facts (
                fact_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                record_hash TEXT NOT NULL,
                learner_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                episode_id TEXT NOT NULL,
                capture_consent_id TEXT NOT NULL,
                consent_generation INTEGER NOT NULL,
                source_kind TEXT NOT NULL,
                start_pts_ns INTEGER NOT NULL,
                end_pts_ns INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                is_late INTEGER NOT NULL CHECK (is_late IN (0, 1))
            );
            CREATE INDEX IF NOT EXISTS semantic_facts_contiguous
                ON semantic_facts(episode_id, is_late, start_pts_ns, end_pts_ns);

            CREATE TABLE IF NOT EXISTS semantic_scopes (
                scope_id TEXT PRIMARY KEY,
                learner_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                episode_id TEXT NOT NULL,
                capture_consent_id TEXT NOT NULL,
                consent_generation INTEGER NOT NULL,
                scope_hash TEXT NOT NULL UNIQUE,
                semantic_revision INTEGER NOT NULL,
                predecessor_scope_id TEXT,
                predecessor_scope_hash TEXT,
                record_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scope_presentations (
                scope_id TEXT NOT NULL,
                semantic_revision INTEGER NOT NULL,
                presentation_revision_ref TEXT NOT NULL UNIQUE,
                PRIMARY KEY(scope_id, semantic_revision),
                FOREIGN KEY(scope_id) REFERENCES semantic_scopes(scope_id)
            );
            CREATE TABLE IF NOT EXISTS late_fact_admissions (
                admission_idempotency_key TEXT PRIMARY KEY,
                record_hash TEXT NOT NULL,
                fact_id TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                disposition TEXT NOT NULL,
                FOREIGN KEY(fact_id) REFERENCES semantic_facts(fact_id),
                FOREIGN KEY(scope_id) REFERENCES semantic_scopes(scope_id)
            );
            CREATE TABLE IF NOT EXISTS l0_semantic_heartbeats (
                learner_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                capture_consent_id TEXT NOT NULL,
                consent_generation INTEGER NOT NULL,
                route_lease_id TEXT NOT NULL,
                route_epoch INTEGER NOT NULL,
                heartbeat_id TEXT NOT NULL UNIQUE,
                processed_media_watermark_pts_ns INTEGER NOT NULL,
                semantic_watermark_pts_ns INTEGER NOT NULL,
                last_ack_fact_id TEXT NOT NULL,
                observed_elapsed_ns INTEGER NOT NULL,
                deadline_ns INTEGER NOT NULL,
                worker_health_lease_id TEXT NOT NULL,
                slo_policy_version TEXT NOT NULL,
                PRIMARY KEY(learner_id, session_id, capture_consent_id, consent_generation, route_epoch)
            );
            """
        )
        columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(l0_semantic_heartbeats)").fetchall()
        }
        if "last_ack_fact_id" not in columns:
            self._connection.execute(
                "ALTER TABLE l0_semantic_heartbeats ADD COLUMN last_ack_fact_id TEXT NOT NULL DEFAULT ''"
            )
        self._connection.commit()

    def append_fact(self, fact: RealtimeSemanticFact, *, is_late: bool = False) -> bool:
        """Persist an L0 fact once. Duplicate replay is harmless; collision is rejected."""

        record_hash = _stable_hash({"fact": asdict(fact), "is_late": is_late})
        existing = self._connection.execute(
            "SELECT record_hash FROM semantic_facts WHERE fact_id = ? OR idempotency_key = ?",
            (fact.fact_id, fact.idempotency_key),
        ).fetchone()
        if existing is not None:
            if str(existing["record_hash"]) != record_hash:
                raise SemanticLedgerError("semantic_fact_idempotency_conflict")
            return False
        self._connection.execute(
            """
            INSERT INTO semantic_facts(
                fact_id, idempotency_key, record_hash, learner_id, session_id,
                episode_id, capture_consent_id, consent_generation, source_kind,
                start_pts_ns, end_pts_ns, content_hash, is_late
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact.fact_id,
                fact.idempotency_key,
                record_hash,
                fact.learner_id,
                fact.session_id,
                fact.episode_id,
                fact.capture_consent_id,
                fact.consent_generation,
                fact.source_kind.value,
                fact.start_pts_ns,
                fact.end_pts_ns,
                fact.content_hash,
                int(is_late),
            ),
        )
        self._connection.commit()
        return True

    def has_durable_fact(
        self,
        *,
        fact_id: str,
        learner_id: str,
        session_id: str,
        episode_id: str,
        capture_consent_id: str,
        consent_generation: int,
        start_pts_ns: int,
        end_pts_ns: int,
        content_hash: str,
    ) -> bool:
        """Check a scope reducer input against the immutable L0 ledger.

        This deliberately returns only a boolean binding proof.  A reducer may
        prove that a lane observation was durably admitted, but it cannot read
        or reinterpret raw user media from this metadata ledger.
        """

        row = self._connection.execute(
            """
            SELECT 1 FROM semantic_facts
            WHERE fact_id=? AND learner_id=? AND session_id=? AND episode_id=?
              AND capture_consent_id=? AND consent_generation=?
              AND start_pts_ns=? AND end_pts_ns=? AND content_hash=? AND is_late=0
            """,
            (
                fact_id,
                learner_id,
                session_id,
                episode_id,
                capture_consent_id,
                consent_generation,
                start_pts_ns,
                end_pts_ns,
                content_hash,
            ),
        ).fetchone()
        return row is not None

    def contiguous_watermark(self, *, episode_id: str, continuity_start_pts_ns: int) -> int | None:
        """Return the non-late contiguous L0 watermark; never bridge a PTS hole."""

        rows = self._connection.execute(
            """
            SELECT start_pts_ns, end_pts_ns FROM semantic_facts
            WHERE episode_id = ? AND is_late = 0
            ORDER BY start_pts_ns, end_pts_ns, fact_id
            """,
            (episode_id,),
        ).fetchall()
        watermark: int | None = None
        for row in rows:
            start = int(row["start_pts_ns"])
            end = int(row["end_pts_ns"])
            if watermark is None:
                if start != continuity_start_pts_ns:
                    return None
                watermark = end
            elif start <= watermark:
                watermark = max(watermark, end)
            else:
                return watermark
        return watermark

    def record_scope(self, scope: SemanticScope) -> bool:
        """Store a scope revision with ancestry checked against durable prior state."""

        episode = scope.episode
        record_hash = _stable_hash(asdict(scope))
        existing = self._connection.execute(
            "SELECT record_hash FROM semantic_scopes WHERE scope_id = ? OR scope_hash = ?",
            (scope.scope_id, scope.scope_hash),
        ).fetchone()
        if existing is not None:
            if str(existing["record_hash"]) != record_hash:
                raise SemanticLedgerError("scope_idempotency_conflict")
            return False
        if scope.semantic_revision == 1:
            if scope.replaces_scope_id is not None:
                raise SemanticLedgerError("initial_scope_cannot_replace_predecessor")
        else:
            predecessor = self._connection.execute(
                "SELECT * FROM semantic_scopes WHERE scope_id = ?",
                (scope.replaces_scope_id,),
            ).fetchone()
            if predecessor is None:
                raise SemanticLedgerError("scope_predecessor_missing")
            if (
                str(predecessor["scope_hash"]) != scope.predecessor_scope_hash
                or str(predecessor["learner_id"]) != episode.learner_id
                or str(predecessor["session_id"]) != episode.session_id
                or str(predecessor["episode_id"]) != episode.episode_id
                or str(predecessor["capture_consent_id"]) != episode.capture_consent_id
                or int(predecessor["consent_generation"]) != episode.consent_generation
                or int(predecessor["semantic_revision"]) + 1 != scope.semantic_revision
            ):
                raise SemanticLedgerError("scope_predecessor_scope_mismatch")
        if scope.stability.value == "STABLE":
            watermark = self.contiguous_watermark(
                episode_id=episode.episode_id,
                continuity_start_pts_ns=episode.continuity_start_pts_ns,
            )
            if watermark is None or watermark < scope.end_pts_ns:
                raise SemanticLedgerError("stable_scope_exceeds_durable_watermark")
        self._connection.execute(
            """
            INSERT INTO semantic_scopes(
                scope_id, learner_id, session_id, episode_id, capture_consent_id,
                consent_generation, scope_hash, semantic_revision,
                predecessor_scope_id, predecessor_scope_hash, record_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scope.scope_id,
                episode.learner_id,
                episode.session_id,
                episode.episode_id,
                episode.capture_consent_id,
                episode.consent_generation,
                scope.scope_hash,
                scope.semantic_revision,
                scope.replaces_scope_id,
                scope.predecessor_scope_hash,
                record_hash,
            ),
        )
        self._connection.commit()
        return True

    def mark_scope_presented(self, *, scope_id: str, semantic_revision: int, presentation_revision_ref: str) -> None:
        scope = self._connection.execute(
            "SELECT semantic_revision FROM semantic_scopes WHERE scope_id = ?",
            (scope_id,),
        ).fetchone()
        if scope is None or int(scope["semantic_revision"]) != semantic_revision:
            raise SemanticLedgerError("presentation_scope_revision_unknown")
        self._connection.execute(
            "INSERT INTO scope_presentations(scope_id, semantic_revision, presentation_revision_ref) VALUES (?, ?, ?)",
            (scope_id, semantic_revision, presentation_revision_ref),
        )
        self._connection.commit()

    def admit_late_fact(self, admission: LateFactAdmission) -> bool:
        """Persist a late-admission intent only after resolving scope, fact and presentation truth."""

        fact = self._connection.execute("SELECT * FROM semantic_facts WHERE fact_id = ?", (admission.fact_id,)).fetchone()
        scope = self._connection.execute("SELECT * FROM semantic_scopes WHERE scope_id = ?", (admission.scope_id,)).fetchone()
        if fact is None or scope is None or not int(fact["is_late"]):
            raise SemanticLedgerError("late_admission_requires_persisted_late_fact_and_scope")
        if (
            str(fact["content_hash"]) != admission.fact_content_hash
            or str(fact["learner_id"]) != admission.learner_id
            or str(fact["session_id"]) != admission.session_id
            or str(fact["episode_id"]) != admission.episode_id
            or str(fact["capture_consent_id"]) != admission.capture_consent_id
            or int(fact["consent_generation"]) != admission.consent_generation
            or str(fact["source_kind"]) != admission.source_kind.value
            or int(fact["start_pts_ns"]) != admission.fact_start_pts_ns
            or int(fact["end_pts_ns"]) != admission.fact_end_pts_ns
            or str(scope["scope_hash"]) != admission.scope_hash
            or int(scope["semantic_revision"]) != admission.base_scope_revision
            or str(scope["learner_id"]) != admission.learner_id
            or str(scope["session_id"]) != admission.session_id
            or str(scope["episode_id"]) != admission.episode_id
            or str(scope["capture_consent_id"]) != admission.capture_consent_id
            or int(scope["consent_generation"]) != admission.consent_generation
        ):
            raise SemanticLedgerError("late_admission_scope_or_fact_mismatch")
        presentation = self._connection.execute(
            "SELECT presentation_revision_ref FROM scope_presentations WHERE scope_id = ? AND semantic_revision = ?",
            (admission.scope_id, admission.base_scope_revision),
        ).fetchone()
        actual_presentation = None if presentation is None else str(presentation["presentation_revision_ref"])
        if actual_presentation != admission.presentation_revision_ref:
            raise SemanticLedgerError("late_admission_presentation_mismatch")
        record_hash = _stable_hash(asdict(admission))
        existing = self._connection.execute(
            "SELECT record_hash FROM late_fact_admissions WHERE admission_idempotency_key = ?",
            (admission.admission_idempotency_key,),
        ).fetchone()
        if existing is not None:
            if str(existing["record_hash"]) != record_hash:
                raise SemanticLedgerError("late_admission_idempotency_conflict")
            return False
        self._connection.execute(
            "INSERT INTO late_fact_admissions(admission_idempotency_key, record_hash, fact_id, scope_id, disposition) VALUES (?, ?, ?, ?, ?)",
            (
                admission.admission_idempotency_key,
                record_hash,
                admission.fact_id,
                admission.scope_id,
                admission.disposition.value,
            ),
        )
        self._connection.commit()
        return True

    def record_heartbeat(self, heartbeat: L0SemanticHeartbeat) -> None:
        """Advance a dual-clock L0 lease; stale media progress cannot renew it."""

        fact = self._connection.execute("SELECT * FROM semantic_facts WHERE fact_id = ? AND is_late = 0", (heartbeat.last_ack_fact_id,)).fetchone()
        if (
            fact is None
            or str(fact["learner_id"]) != heartbeat.learner_id
            or str(fact["session_id"]) != heartbeat.session_id
            or str(fact["capture_consent_id"]) != heartbeat.capture_consent_id
            or int(fact["consent_generation"]) != heartbeat.consent_generation
            or int(fact["end_pts_ns"]) != heartbeat.semantic_watermark_pts_ns
        ):
            raise SemanticLedgerError("l0_heartbeat_ack_fact_mismatch")
        key = (
            heartbeat.learner_id,
            heartbeat.session_id,
            heartbeat.capture_consent_id,
            heartbeat.consent_generation,
            heartbeat.route_epoch,
        )
        current = self._connection.execute(
            """
            SELECT * FROM l0_semantic_heartbeats
            WHERE learner_id = ? AND session_id = ? AND capture_consent_id = ?
              AND consent_generation = ? AND route_epoch = ?
            """,
            key,
        ).fetchone()
        if current is not None:
            if (
                str(current["route_lease_id"]) != heartbeat.route_lease_id
                or heartbeat.observed_elapsed_ns <= int(current["observed_elapsed_ns"])
                or heartbeat.processed_media_watermark_pts_ns <= int(current["processed_media_watermark_pts_ns"])
                or heartbeat.semantic_watermark_pts_ns < int(current["semantic_watermark_pts_ns"])
            ):
                raise SemanticLedgerError("l0_heartbeat_not_monotonic_or_route_mismatch")
            self._connection.execute(
                """
                UPDATE l0_semantic_heartbeats
                SET heartbeat_id = ?, processed_media_watermark_pts_ns = ?, semantic_watermark_pts_ns = ?,
                    last_ack_fact_id = ?, observed_elapsed_ns = ?, deadline_ns = ?, worker_health_lease_id = ?, slo_policy_version = ?
                WHERE learner_id = ? AND session_id = ? AND capture_consent_id = ?
                  AND consent_generation = ? AND route_epoch = ?
                """,
                (
                    heartbeat.heartbeat_id,
                    heartbeat.processed_media_watermark_pts_ns,
                    heartbeat.semantic_watermark_pts_ns,
                    heartbeat.last_ack_fact_id,
                    heartbeat.observed_elapsed_ns,
                    heartbeat.deadline_ns,
                    heartbeat.worker_health_lease_id,
                    heartbeat.slo_policy_version,
                    *key,
                ),
            )
        else:
            self._connection.execute(
                """
                INSERT INTO l0_semantic_heartbeats(
                    learner_id, session_id, capture_consent_id, consent_generation, route_lease_id, route_epoch,
                    heartbeat_id, processed_media_watermark_pts_ns, semantic_watermark_pts_ns,
                    last_ack_fact_id, observed_elapsed_ns, deadline_ns, worker_health_lease_id, slo_policy_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    heartbeat.learner_id,
                    heartbeat.session_id,
                    heartbeat.capture_consent_id,
                    heartbeat.consent_generation,
                    heartbeat.route_lease_id,
                    heartbeat.route_epoch,
                    heartbeat.heartbeat_id,
                    heartbeat.processed_media_watermark_pts_ns,
                    heartbeat.semantic_watermark_pts_ns,
                    heartbeat.last_ack_fact_id,
                    heartbeat.observed_elapsed_ns,
                    heartbeat.deadline_ns,
                    heartbeat.worker_health_lease_id,
                    heartbeat.slo_policy_version,
                ),
            )
        self._connection.commit()

    def heartbeat_state(
        self,
        *,
        learner_id: str,
        session_id: str,
        capture_consent_id: str,
        consent_generation: int,
        route_epoch: int,
        now_elapsed_ns: int,
    ) -> L0HeartbeatState:
        row = self._connection.execute(
            """
            SELECT observed_elapsed_ns, deadline_ns FROM l0_semantic_heartbeats
            WHERE learner_id = ? AND session_id = ? AND capture_consent_id = ?
              AND consent_generation = ? AND route_epoch = ?
            """,
            (learner_id, session_id, capture_consent_id, consent_generation, route_epoch),
        ).fetchone()
        if row is None or now_elapsed_ns < 0:
            return L0HeartbeatState.SEMANTIC_STALLED
        if now_elapsed_ns > int(row["observed_elapsed_ns"]) + int(row["deadline_ns"]):
            return L0HeartbeatState.SEMANTIC_STALLED
        return L0HeartbeatState.ACTIVE
