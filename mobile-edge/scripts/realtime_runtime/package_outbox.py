"""Durable PC outbox for immutable CONTENT_ANALYSIS_PACKAGE.v2.l1 revisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3

from .content_package import ContentAnalysisPackageV2, PackagePersistenceReceipt
from .learning_moment_ledger import LearningMomentLedger


class PackageOutboxError(ValueError):
    """A package retry, lease or ACK would break delivery linearity."""


@dataclass(frozen=True)
class ClaimedPackage:
    package_id: str
    package_revision_id: str
    learner_id: str
    message_id: str
    lease_id: str
    lease_deadline_elapsed_ns: int
    payload_json: str
    payload_hash: str


def _canonical_hash(value: object) -> str:
    source = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


class PackageOutbox:
    """PC-side durable outbox; only an Android persistence receipt completes delivery."""

    def __init__(self, path: Path, *, learning_moment_ledger: LearningMomentLedger) -> None:
        self._learning_moment_ledger = learning_moment_ledger
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def __enter__(self) -> "PackageOutbox":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS content_package_outbox (
                package_id TEXT NOT NULL,
                package_revision_id TEXT NOT NULL,
                learner_id TEXT NOT NULL,
                message_id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL,
                capture_consent_id TEXT NOT NULL,
                consent_generation INTEGER NOT NULL,
                processing_eligibility_grant_id TEXT,
                policy_bundle_hash TEXT NOT NULL,
                protocol_profile_id TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('PENDING', 'LEASED', 'ACKED')),
                lease_id TEXT,
                lease_deadline_elapsed_ns INTEGER,
                ack_receipt_id TEXT,
                PRIMARY KEY(package_id, package_revision_id)
            );
            CREATE TABLE IF NOT EXISTS package_persistence_receipts (
                receipt_id TEXT PRIMARY KEY,
                receipt_message_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                package_id TEXT NOT NULL,
                package_revision_id TEXT NOT NULL,
                learner_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                capture_consent_id TEXT NOT NULL,
                consent_generation INTEGER NOT NULL,
                processing_eligibility_grant_id TEXT,
                policy_bundle_hash TEXT NOT NULL,
                protocol_profile_id TEXT NOT NULL,
                delivered_message_id TEXT NOT NULL,
                delivery_lease_id TEXT NOT NULL,
                package_payload_hash TEXT NOT NULL,
                receipt_hash TEXT NOT NULL UNIQUE,
                transaction_hash TEXT NOT NULL,
                persisted_elapsed_ns INTEGER NOT NULL,
                disposition TEXT NOT NULL
            );
            """
        )
        self._add_legacy_columns()
        self._connection.commit()

    def _add_legacy_columns(self) -> None:
        """Keep pre-release local databases readable while new receipts fail closed."""

        outbox_required = {
            "session_id": "TEXT",
            "capture_consent_id": "TEXT",
            "consent_generation": "INTEGER",
            "processing_eligibility_grant_id": "TEXT",
            "policy_bundle_hash": "TEXT",
            "protocol_profile_id": "TEXT",
        }
        columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(content_package_outbox)").fetchall()
        }
        for name, sql_type in outbox_required.items():
            if name not in columns:
                self._connection.execute(f"ALTER TABLE content_package_outbox ADD COLUMN {name} {sql_type}")
        receipt_required = {
            "receipt_message_id": "TEXT",
            "idempotency_key": "TEXT",
            "created_at": "TEXT",
            "session_id": "TEXT",
            "capture_consent_id": "TEXT",
            "consent_generation": "INTEGER",
            "processing_eligibility_grant_id": "TEXT",
            "policy_bundle_hash": "TEXT",
            "protocol_profile_id": "TEXT",
            "delivered_message_id": "TEXT",
            "delivery_lease_id": "TEXT",
            "package_payload_hash": "TEXT",
            "disposition": "TEXT",
        }
        receipt_columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(package_persistence_receipts)").fetchall()
        }
        for name, sql_type in receipt_required.items():
            if name not in receipt_columns:
                self._connection.execute(f"ALTER TABLE package_persistence_receipts ADD COLUMN {name} {sql_type}")

    def enqueue(self, package: ContentAnalysisPackageV2) -> bool:
        self._learning_moment_ledger.assert_package_registered(package)
        payload = asdict(package)
        payload_hash = _canonical_hash(payload)
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        existing = self._connection.execute(
            "SELECT payload_hash FROM content_package_outbox WHERE package_id = ? AND package_revision_id = ?",
            (package.package_id, package.package_revision_id),
        ).fetchone()
        if existing is not None:
            if str(existing["payload_hash"]) != payload_hash:
                raise PackageOutboxError("package_revision_payload_conflict")
            return False
        try:
            self._connection.execute(
                """
                INSERT INTO content_package_outbox(
                    package_id, package_revision_id, learner_id, message_id,
                    session_id, capture_consent_id, consent_generation,
                    processing_eligibility_grant_id, policy_bundle_hash,
                    protocol_profile_id, payload_hash, payload_json, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    package.package_id,
                    package.package_revision_id,
                    package.learner_id,
                    package.message_id,
                    package.session_id,
                    package.capture_consent_id,
                    package.consent_generation,
                    package.processing_eligibility_grant_id,
                    package.policy_bundle_hash,
                    package.protocol_profile_id,
                    payload_hash,
                    payload_json,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise PackageOutboxError("package_message_id_conflict") from error
        self._connection.commit()
        return True

    def claim(self, *, lease_id: str, now_elapsed_ns: int, lease_duration_ns: int) -> ClaimedPackage | None:
        if not lease_id or now_elapsed_ns < 0 or lease_duration_ns <= 0:
            raise PackageOutboxError("package_lease_arguments_invalid")
        self._connection.execute(
            """
            UPDATE content_package_outbox
            SET state = 'PENDING', lease_id = NULL, lease_deadline_elapsed_ns = NULL
            WHERE state = 'LEASED' AND lease_deadline_elapsed_ns <= ?
            """,
            (now_elapsed_ns,),
        )
        row = self._connection.execute(
            """
            SELECT * FROM content_package_outbox
            WHERE state = 'PENDING'
            ORDER BY rowid
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            self._connection.commit()
            return None
        updated = self._connection.execute(
            """
            UPDATE content_package_outbox
            SET state = 'LEASED', lease_id = ?, lease_deadline_elapsed_ns = ?
            WHERE package_id = ? AND package_revision_id = ? AND state = 'PENDING'
            """,
            (lease_id, now_elapsed_ns + lease_duration_ns, row["package_id"], row["package_revision_id"]),
        )
        self._connection.commit()
        if updated.rowcount != 1:
            return None
        return ClaimedPackage(
            package_id=str(row["package_id"]),
            package_revision_id=str(row["package_revision_id"]),
            learner_id=str(row["learner_id"]),
            message_id=str(row["message_id"]),
            lease_id=lease_id,
            lease_deadline_elapsed_ns=now_elapsed_ns + lease_duration_ns,
            payload_json=str(row["payload_json"]),
            payload_hash=str(row["payload_hash"]),
        )

    def acknowledge(self, receipt: PackagePersistenceReceipt, *, lease_id: str, now_elapsed_ns: int) -> bool:
        if not lease_id or now_elapsed_ns < 0:
            raise PackageOutboxError("package_ack_arguments_invalid")
        receipt_hash = _canonical_hash(asdict(receipt))
        existing_receipt = self._connection.execute(
            """
            SELECT receipt_hash FROM package_persistence_receipts
            WHERE receipt_id = ? OR receipt_message_id = ? OR idempotency_key = ?
            """,
            (receipt.receipt_id, receipt.receipt_message_id, receipt.idempotency_key),
        ).fetchone()
        if existing_receipt is not None:
            if str(existing_receipt["receipt_hash"]) != receipt_hash:
                raise PackageOutboxError("package_receipt_idempotency_conflict")
            return False
        row = self._connection.execute(
            """
            SELECT * FROM content_package_outbox
            WHERE package_id = ? AND package_revision_id = ?
            """,
            (receipt.package_id, receipt.package_revision_id),
        ).fetchone()
        if row is None:
            raise PackageOutboxError("package_ack_unknown_revision")
        if (
            str(row["learner_id"]) != receipt.learner_id
            or str(row["session_id"]) != receipt.session_id
            or str(row["capture_consent_id"]) != receipt.capture_consent_id
            or int(row["consent_generation"]) != receipt.consent_generation
            or row["processing_eligibility_grant_id"] != receipt.processing_eligibility_grant_id
            or str(row["policy_bundle_hash"]) != receipt.policy_bundle_hash
            or str(row["protocol_profile_id"]) != receipt.protocol_profile_id
            or str(row["message_id"]) != receipt.delivered_message_id
            or str(row["payload_hash"]) != receipt.package_payload_hash
            or str(row["state"]) != "LEASED"
            or receipt.delivery_lease_id != lease_id
            or str(row["lease_id"]) != receipt.delivery_lease_id
            or int(row["lease_deadline_elapsed_ns"]) <= now_elapsed_ns
        ):
            raise PackageOutboxError("package_ack_lease_or_scope_denied")
        self._connection.execute(
            """
            INSERT INTO package_persistence_receipts(
                receipt_id, receipt_message_id, idempotency_key, created_at,
                package_id, package_revision_id, learner_id, session_id,
                capture_consent_id, consent_generation, processing_eligibility_grant_id,
                policy_bundle_hash, protocol_profile_id, delivered_message_id,
                delivery_lease_id, package_payload_hash, receipt_hash,
                transaction_hash, persisted_elapsed_ns, disposition
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt.receipt_id,
                receipt.receipt_message_id,
                receipt.idempotency_key,
                receipt.created_at,
                receipt.package_id,
                receipt.package_revision_id,
                receipt.learner_id,
                receipt.session_id,
                receipt.capture_consent_id,
                receipt.consent_generation,
                receipt.processing_eligibility_grant_id,
                receipt.policy_bundle_hash,
                receipt.protocol_profile_id,
                receipt.delivered_message_id,
                receipt.delivery_lease_id,
                receipt.package_payload_hash,
                receipt_hash,
                receipt.transaction_hash,
                receipt.persisted_elapsed_ns,
                receipt.disposition,
            ),
        )
        self._connection.execute(
            """
            UPDATE content_package_outbox
            SET state = 'ACKED', ack_receipt_id = ?, lease_id = NULL, lease_deadline_elapsed_ns = NULL
            WHERE package_id = ? AND package_revision_id = ?
            """,
            (receipt.receipt_id, receipt.package_id, receipt.package_revision_id),
        )
        self._connection.commit()
        return True
