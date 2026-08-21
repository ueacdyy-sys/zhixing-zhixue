"""Private, durable PC-side buffer for authenticated v2 media fragments.

The buffer is deliberately below the semantic pipeline: a fragment is first
authenticated by :mod:`media_security`, then its original ciphertext is
fsync'ed into a private directory and only then can a resume receipt be
created.  The control database contains hashes and routing identity, never
media plaintext or keys.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from .contracts import PcBufferedFragment, PcBufferGapDisposition, PcBufferResumeReceipt
from .media_security import AcceptedMediaFragment


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class PcBufferResumeCursor:
    epoch: int
    sequence: int
    range_hash: str


class PcMediaBufferCapacity:
    NORMAL = "NORMAL"
    SOFT = "SOFT"
    HARD = "HARD"


@dataclass(frozen=True)
class PcBufferCapacitySnapshot:
    state: str
    bytes_used: int
    soft_limit_bytes: int
    hard_limit_bytes: int


class PcMediaBuffer:
    """SQLite-indexed encrypted fragment files with explicit revoke fences."""

    def __init__(
        self,
        root: Path,
        *,
        soft_limit_bytes: int = 256 * 1024 * 1024,
        hard_limit_bytes: int = 512 * 1024 * 1024,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        if soft_limit_bytes <= 0 or hard_limit_bytes < soft_limit_bytes:
            raise ValueError("media_buffer_capacity_invalid")
        self.root = Path(root)
        self.fragments_dir = self.root / "fragments"
        self.fragments_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
            os.chmod(self.fragments_dir, 0o700)
        except OSError:
            pass
        self.db_path = self.root / "buffer.sqlite3"
        self.soft_limit_bytes = soft_limit_bytes
        self.hard_limit_bytes = hard_limit_bytes
        self._now_ms = now_ms or (lambda: 0)
        self._lock = threading.RLock()
        with self._database() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS fragments (
                    fragment_id TEXT PRIMARY KEY,
                    media_security_session_id TEXT NOT NULL DEFAULT '',
                    device_id TEXT NOT NULL DEFAULT '',
                    learner_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    consent_id TEXT NOT NULL,
                    consent_generation INTEGER NOT NULL,
                    route_lease_id TEXT NOT NULL,
                    route_epoch INTEGER NOT NULL,
                    capture_epoch INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    start_pts_ns INTEGER NOT NULL,
                    end_pts_ns INTEGER NOT NULL,
                    media_hash TEXT NOT NULL,
                    local_storage_hash TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    outbox_id TEXT NOT NULL,
                    replay_key TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    state TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_ms INTEGER NOT NULL,
                    UNIQUE(media_security_session_id, capture_epoch, sequence)
                );
                CREATE TABLE IF NOT EXISTS ack_cursors (
                    learner_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    consent_id TEXT NOT NULL,
                    consent_generation INTEGER NOT NULL,
                    route_epoch INTEGER NOT NULL,
                    capture_epoch INTEGER NOT NULL,
                    media_security_session_id TEXT NOT NULL DEFAULT '',
                    sequence INTEGER NOT NULL,
                    PRIMARY KEY(learner_id, session_id, consent_generation, route_epoch, capture_epoch, media_security_session_id)
                );
                CREATE TABLE IF NOT EXISTS revoked_scopes (
                    learner_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    consent_generation INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    revoked_ms INTEGER NOT NULL,
                    PRIMARY KEY(learner_id, session_id, consent_generation)
                );
                """
            )
            columns = {str(row["name"]) for row in db.execute("PRAGMA table_info(fragments)").fetchall()}
            if "media_security_session_id" not in columns:
                db.execute("ALTER TABLE fragments ADD COLUMN media_security_session_id TEXT NOT NULL DEFAULT ''")
            if "device_id" not in columns:
                db.execute("ALTER TABLE fragments ADD COLUMN device_id TEXT NOT NULL DEFAULT ''")
            self._migrate_security_session_sequence_scope(db)
            self._migrate_ack_cursor_security_session_scope(db)
            db.execute(
                "CREATE INDEX IF NOT EXISTS fragments_scope "
                "ON fragments(learner_id, session_id, consent_generation, capture_epoch, sequence)"
            )

    @staticmethod
    def _migrate_security_session_sequence_scope(db: sqlite3.Connection) -> None:
        """Replace the pre-rekey uniqueness key without discarding buffered media.

        A media-security session is intentionally short lived, and Android
        restarts fragment sequence at zero after an in-place ECDH rotation.
        The older ``session_id,capture_epoch,sequence`` unique constraint made
        that correct rotation look like a duplicate media upload.  SQLite
        cannot drop a table-level UNIQUE constraint, so rebuild only this
        private index table inside its opening transaction.
        """

        row = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='fragments'"
        ).fetchone()
        definition = "" if row is None or row["sql"] is None else str(row["sql"])
        normalized = "".join(definition.split()).lower()
        if "unique(session_id,capture_epoch,sequence)" not in normalized:
            return
        db.execute("ALTER TABLE fragments RENAME TO fragments_pre_security_sequence_scope")
        db.execute(
            """
            CREATE TABLE fragments (
                fragment_id TEXT PRIMARY KEY,
                media_security_session_id TEXT NOT NULL DEFAULT '',
                device_id TEXT NOT NULL DEFAULT '',
                learner_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                consent_id TEXT NOT NULL,
                consent_generation INTEGER NOT NULL,
                route_lease_id TEXT NOT NULL,
                route_epoch INTEGER NOT NULL,
                capture_epoch INTEGER NOT NULL,
                sequence INTEGER NOT NULL,
                start_pts_ns INTEGER NOT NULL,
                end_pts_ns INTEGER NOT NULL,
                media_hash TEXT NOT NULL,
                local_storage_hash TEXT NOT NULL,
                file_name TEXT NOT NULL,
                outbox_id TEXT NOT NULL,
                replay_key TEXT NOT NULL,
                byte_size INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'ACTIVE',
                created_ms INTEGER NOT NULL,
                UNIQUE(media_security_session_id, capture_epoch, sequence)
            )
            """
        )
        db.execute(
            """
            INSERT INTO fragments(
                fragment_id,media_security_session_id,device_id,learner_id,session_id,consent_id,consent_generation,
                route_lease_id,route_epoch,capture_epoch,sequence,start_pts_ns,end_pts_ns,media_hash,
                local_storage_hash,file_name,outbox_id,replay_key,byte_size,state,created_ms
            )
            SELECT
                fragment_id,media_security_session_id,device_id,learner_id,session_id,consent_id,consent_generation,
                route_lease_id,route_epoch,capture_epoch,sequence,start_pts_ns,end_pts_ns,media_hash,
                local_storage_hash,file_name,outbox_id,replay_key,byte_size,state,created_ms
            FROM fragments_pre_security_sequence_scope
            """
        )
        db.execute("DROP TABLE fragments_pre_security_sequence_scope")

    @staticmethod
    def _migrate_ack_cursor_security_session_scope(db: sqlite3.Connection) -> None:
        columns = {str(row["name"]) for row in db.execute("PRAGMA table_info(ack_cursors)").fetchall()}
        if "media_security_session_id" in columns:
            return
        db.execute("ALTER TABLE ack_cursors RENAME TO ack_cursors_pre_security_session_scope")
        db.execute(
            """
            CREATE TABLE ack_cursors (
                learner_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                consent_id TEXT NOT NULL,
                consent_generation INTEGER NOT NULL,
                route_epoch INTEGER NOT NULL,
                capture_epoch INTEGER NOT NULL,
                media_security_session_id TEXT NOT NULL DEFAULT '',
                sequence INTEGER NOT NULL,
                PRIMARY KEY(learner_id, session_id, consent_generation, route_epoch, capture_epoch, media_security_session_id)
            )
            """
        )
        db.execute(
            """
            INSERT INTO ack_cursors(
                learner_id,session_id,consent_id,consent_generation,route_epoch,capture_epoch,media_security_session_id,sequence
            )
            SELECT learner_id,session_id,consent_id,consent_generation,route_epoch,capture_epoch,'',sequence
            FROM ack_cursors_pre_security_session_scope
            """
        )
        db.execute("DROP TABLE ack_cursors_pre_security_session_scope")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def _database(self):
        db = self._connect()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def persist(self, accepted: AcceptedMediaFragment, *, capture_epoch: int, device_id: str = "") -> PcBufferedFragment:
        if capture_epoch < 1:
            raise ValueError("media_buffer_capture_epoch_invalid")
        envelope = accepted.envelope
        if envelope is None:
            raise ValueError("media_buffer_envelope_missing")
        header = accepted.header
        blob = (envelope.nonce_b64 + "." + envelope.ciphertext_b64).encode("ascii")
        local_hash = _hash(blob)
        fragment_id = _hash(
            f"{header.media_security_session_id}:{capture_epoch}:{header.sequence}".encode("utf-8")
        )[:32]
        file_name = f"{fragment_id}.bin"
        path = self.fragments_dir / file_name
        with self._lock:
            with self._database() as db:
                revoked = db.execute(
                    "SELECT 1 FROM revoked_scopes WHERE learner_id=? AND session_id=? AND consent_generation=?",
                    (header.learner_id, header.capture_session_id, header.consent_generation),
                ).fetchone()
                if revoked:
                    raise ValueError("media_buffer_revoked")
                existing = db.execute("SELECT * FROM fragments WHERE fragment_id=?", (fragment_id,)).fetchone()
                if existing:
                    if existing["local_storage_hash"] != local_hash:
                        raise ValueError("media_buffer_idempotency_conflict")
                    return self._contract(existing)
                tmp = path.with_suffix(".tmp")
                with tmp.open("wb") as handle:
                    handle.write(blob)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
                outbox_id = f"pc-media-{uuid.uuid4().hex}"
                replay_key = _hash(f"{fragment_id}:replay.v1".encode("utf-8"))
                db.execute(
                    """INSERT INTO fragments(fragment_id,media_security_session_id,device_id,learner_id,session_id,consent_id,consent_generation,
                       route_lease_id,route_epoch,capture_epoch,sequence,start_pts_ns,end_pts_ns,media_hash,
                       local_storage_hash,file_name,outbox_id,replay_key,byte_size,state,created_ms)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        fragment_id, header.media_security_session_id, device_id, header.learner_id, header.capture_session_id, header.capture_consent_id,
                        header.consent_generation, header.route_lease_id, header.route_epoch, capture_epoch,
                        header.sequence, header.pts_start_us * 1000, header.pts_end_us * 1000,
                        header.media_sha256, local_hash, file_name, outbox_id, replay_key, len(blob),
                        "ACTIVE", self._now_ms(),
                    ),
                )
                return PcBufferedFragment(
                    fragment_id=fragment_id, sequence=header.sequence, start_pts_ns=header.pts_start_us * 1000,
                    end_pts_ns=header.pts_end_us * 1000, media_hash=header.media_sha256,
                    local_storage_hash=local_hash, outbox_id=outbox_id, replay_idempotency_key=replay_key,
                )

    def read_encrypted(self, fragment_id: str) -> bytes:
        with self._lock, self._database() as db:
            row = db.execute("SELECT file_name,local_storage_hash FROM fragments WHERE fragment_id=? AND state IN ('ACTIVE','REVOKED')", (fragment_id,)).fetchone()
            if row is None:
                raise KeyError(fragment_id)
            data = (self.fragments_dir / row["file_name"]).read_bytes()
            if _hash(data) != row["local_storage_hash"]:
                raise ValueError("media_buffer_storage_hash_mismatch")
            return data

    def pending_count(self) -> int:
        with self._database() as db:
            return int(db.execute("SELECT COUNT(*) FROM fragments WHERE state='ACTIVE'").fetchone()[0])

    def capacity(self) -> PcBufferCapacitySnapshot:
        with self._connect() as db:
            used = int(db.execute("SELECT COALESCE(SUM(byte_size),0) FROM fragments WHERE state='ACTIVE'").fetchone()[0])
        state = PcMediaBufferCapacity.HARD if used >= self.hard_limit_bytes else PcMediaBufferCapacity.SOFT if used >= self.soft_limit_bytes else PcMediaBufferCapacity.NORMAL
        return PcBufferCapacitySnapshot(state, used, self.soft_limit_bytes, self.hard_limit_bytes)

    def ack(self, *, learner_id: str, session_id: str, capture_consent_id: str, consent_generation: int, route_epoch: int, capture_epoch: int, sequence: int, media_security_session_id: str | None = None) -> None:
        with self._lock, self._database() as db:
            if db.execute("SELECT 1 FROM revoked_scopes WHERE learner_id=? AND session_id=? AND consent_generation=?", (learner_id, session_id, consent_generation)).fetchone():
                raise ValueError("media_buffer_revoked")
            query = "SELECT fragment_id,file_name,media_security_session_id FROM fragments WHERE learner_id=? AND session_id=? AND consent_id=? AND consent_generation=? AND route_epoch=? AND capture_epoch=? AND sequence=? AND state='ACTIVE'"
            values: list[object] = [learner_id, session_id, capture_consent_id, consent_generation, route_epoch, capture_epoch, sequence]
            if media_security_session_id is not None:
                query += " AND media_security_session_id=?"
                values.append(media_security_session_id)
            row = db.execute(query, values).fetchone()
            if row is None:
                raise KeyError(sequence)
            cursor_security_session_id = media_security_session_id or str(row["media_security_session_id"])
            db.execute(
                """
                INSERT INTO ack_cursors(
                    learner_id,session_id,consent_id,consent_generation,route_epoch,capture_epoch,media_security_session_id,sequence
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(learner_id,session_id,consent_generation,route_epoch,capture_epoch,media_security_session_id)
                DO UPDATE SET sequence=MAX(sequence,excluded.sequence)
                """,
                (learner_id, session_id, capture_consent_id, consent_generation, route_epoch, capture_epoch, cursor_security_session_id, sequence),
            )
            db.execute("DELETE FROM fragments WHERE fragment_id=?", (row["fragment_id"],))
            try:
                (self.fragments_dir / row["file_name"]).unlink()
            except FileNotFoundError:
                pass

    def revoke(self, *, learner_id: str, session_id: str, consent_generation: int, reason: str = "CONSENT_REVOKED") -> None:
        with self._lock, self._database() as db:
            db.execute("INSERT OR REPLACE INTO revoked_scopes VALUES(?,?,?,?,?)", (learner_id, session_id, consent_generation, reason, self._now_ms()))
            db.execute("UPDATE fragments SET state='REVOKED' WHERE learner_id=? AND session_id=? AND consent_generation=?", (learner_id, session_id, consent_generation))

    def revoke_device(self, device_id: str, reason: str = "DEVICE_CREDENTIAL_REVOKED") -> None:
        """Fence retained encrypted blobs when their device credential is revoked."""
        with self._lock, self._database() as db:
            db.execute("UPDATE fragments SET state='REVOKED' WHERE device_id=?", (device_id,))

    def resume(self, *, learner_id: str, session_id: str, capture_consent_id: str, consent_generation: int, route_lease_id: str, route_epoch: int, capture_epoch: int, owner_endpoint_id: str, resume_attempt_id: str, cursor: PcBufferResumeCursor | None = None, media_security_session_id: str | None = None) -> PcBufferResumeReceipt:
        with self._lock, self._database() as db:
            if db.execute("SELECT 1 FROM revoked_scopes WHERE learner_id=? AND session_id=? AND consent_generation=?", (learner_id, session_id, consent_generation)).fetchone():
                raise ValueError("media_buffer_revoked")
            query = "SELECT * FROM fragments WHERE learner_id=? AND session_id=? AND consent_id=? AND consent_generation=? AND route_lease_id=? AND route_epoch=? AND capture_epoch=? AND state='ACTIVE'"
            values: list[object] = [learner_id, session_id, capture_consent_id, consent_generation, route_lease_id, route_epoch, capture_epoch]
            if media_security_session_id is not None:
                query += " AND media_security_session_id=?"
                values.append(media_security_session_id)
            rows = db.execute(query + " ORDER BY sequence", values).fetchall()
            if not rows:
                raise ValueError("media_buffer_empty")
            security_session_ids = {str(row["media_security_session_id"]) for row in rows}
            if media_security_session_id is None and len(security_session_ids) != 1:
                raise ValueError("media_buffer_security_session_required")
            cursor_security_session_id = media_security_session_id or next(iter(security_session_ids))
            run = [rows[0]]
            for row in rows[1:]:
                if row["sequence"] != run[-1]["sequence"] + 1:
                    break
                run.append(row)
            fragments = tuple(self._contract(row) for row in run)
            manifest = _hash(json.dumps([f.__dict__ for f in fragments], sort_keys=True, separators=(",", ":")).encode("utf-8"))
            range_hash = _hash(json.dumps([(f.sequence, f.start_pts_ns, f.end_pts_ns) for f in fragments], separators=(",", ":")).encode("utf-8"))
            disposition = PcBufferGapDisposition.CONTIGUOUS if len(run) == len(rows) and all(a.end_pts_ns == b.start_pts_ns for a, b in zip(fragments, fragments[1:])) else PcBufferGapDisposition.QUARANTINED
            if cursor is not None and (cursor.epoch != capture_epoch or cursor.range_hash != range_hash or cursor.sequence > fragments[-1].sequence):
                disposition = PcBufferGapDisposition.QUARANTINED
            ack_row = db.execute(
                """SELECT sequence FROM ack_cursors
                   WHERE learner_id=? AND session_id=? AND consent_generation=? AND route_epoch=? AND capture_epoch=?
                     AND media_security_session_id=?""",
                (learner_id, session_id, consent_generation, route_epoch, capture_epoch, cursor_security_session_id),
            ).fetchone()
            last_acked = int(ack_row[0]) if ack_row else -1
            return PcBufferResumeReceipt(receipt_id=uuid.uuid4().hex, learner_id=learner_id, session_id=session_id, capture_consent_id=capture_consent_id, consent_generation=consent_generation, route_lease_id=route_lease_id, route_epoch=route_epoch, capture_epoch=capture_epoch, owner_endpoint_id=owner_endpoint_id, buffered_start_pts_ns=fragments[0].start_pts_ns, buffered_end_pts_ns=fragments[-1].end_pts_ns, cache_manifest_hash=manifest, resumed_owner_endpoint_id=owner_endpoint_id, fragments=fragments, last_acked_sequence=last_acked, resume_attempt_id=resume_attempt_id, replay_idempotency_key=_hash(f"{session_id}:{resume_attempt_id}".encode("utf-8")), gap_disposition=disposition)

    @staticmethod
    def _contract(row: sqlite3.Row) -> PcBufferedFragment:
        return PcBufferedFragment(fragment_id=row["fragment_id"], sequence=row["sequence"], start_pts_ns=row["start_pts_ns"], end_pts_ns=row["end_pts_ns"], media_hash=row["media_hash"], local_storage_hash=row["local_storage_hash"], outbox_id=row["outbox_id"], replay_idempotency_key=row["replay_key"])
