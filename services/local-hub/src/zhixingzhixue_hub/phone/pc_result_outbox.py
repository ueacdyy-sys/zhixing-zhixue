"""PC 本地中枢向已配对手机投递分析结果的持久化 outbox。"""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


class MobileResultOutboxError(ValueError):
    """Raised when a pairing, delivery, or acknowledgement contract is invalid."""


class MobileResultOutboxAuthenticationError(MobileResultOutboxError):
    """Raised when a device token cannot authorize the requested operation."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _digest(secret: str) -> str:
    return sha256(secret.encode("utf-8")).hexdigest()


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise MobileResultOutboxError(f"{field}_required")
    return value.strip()


class MobileResultOutbox:
    """At-least-once local delivery for PC analysis results, without ADB transport."""

    def __init__(self, root: Path, *, now: Callable[[], datetime] = _utc_now) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._now = now
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self.root / "mobile-result-outbox.sqlite3",
            check_same_thread=False,
        )
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS mobile_pairing_tokens (
                    token_sha256 TEXT PRIMARY KEY,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    paired_device_id TEXT
                );

                CREATE TABLE IF NOT EXISTS mobile_devices (
                    device_id TEXT PRIMARY KEY,
                    access_token_sha256 TEXT NOT NULL,
                    paired_at TEXT NOT NULL,
                    revoked_at TEXT
                );

                CREATE TABLE IF NOT EXISTS mobile_result_outbox (
                    message_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL REFERENCES mobile_devices(device_id),
                    idempotency_key TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('PENDING', 'DELIVERED', 'ACKED')),
                    created_at TEXT NOT NULL,
                    delivered_at TEXT,
                    acknowledged_at TEXT,
                    UNIQUE(device_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS mobile_result_outbox_delivery_idx
                    ON mobile_result_outbox(device_id, status, created_at);
                """
            )
            self._connection.commit()

    def issue_pairing_token(self, *, ttl_seconds: int = 300) -> dict[str, str]:
        """Issue a one-time, short-lived token which is never persisted in clear text."""
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise MobileResultOutboxError("pairing_token_ttl_seconds_must_be_positive")
        now = self._now()
        token = secrets.token_urlsafe(32)
        issued_at = _timestamp(now)
        expires_at = _timestamp(now + timedelta(seconds=ttl_seconds))
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO mobile_pairing_tokens(token_sha256, issued_at, expires_at, consumed_at, paired_device_id)
                VALUES (?, ?, ?, NULL, NULL)
                """,
                (_digest(token), issued_at, expires_at),
            )
            self._connection.commit()
        return {"pairing_token": token, "issued_at": issued_at, "expires_at": expires_at}

    def pair_device(self, *, device_id: str, pairing_token: str) -> dict[str, str]:
        """Redeem a one-time pairing token for a per-device access token."""
        device_id = _required_text({"device_id": device_id}, "device_id")
        pairing_token = _required_text({"pairing_token": pairing_token}, "pairing_token")
        now = _timestamp(self._now())
        access_token = secrets.token_urlsafe(32)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT expires_at, consumed_at FROM mobile_pairing_tokens WHERE token_sha256 = ?
                """,
                (_digest(pairing_token),),
            ).fetchone()
            if row is None or row[1] is not None or row[0] < now:
                raise MobileResultOutboxAuthenticationError("pairing_token_invalid_or_expired")
            self._connection.execute(
                """
                UPDATE mobile_pairing_tokens
                SET consumed_at = ?, paired_device_id = ?
                WHERE token_sha256 = ?
                """,
                (now, device_id, _digest(pairing_token)),
            )
            self._connection.execute(
                """
                INSERT INTO mobile_devices(device_id, access_token_sha256, paired_at, revoked_at)
                VALUES (?, ?, ?, NULL)
                ON CONFLICT(device_id) DO UPDATE SET
                    access_token_sha256 = excluded.access_token_sha256,
                    paired_at = excluded.paired_at,
                    revoked_at = NULL
                """,
                (device_id, _digest(access_token), now),
            )
            self._connection.commit()
        return {"device_id": device_id, "access_token": access_token, "paired_at": now}

    def enqueue_analysis_result(
        self,
        *,
        device_id: str,
        analysis_result: Mapping[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Persist an opaque versioned PC result until the paired phone ACKs it."""
        device_id = _required_text({"device_id": device_id}, "device_id")
        idempotency_key = _required_text({"idempotency_key": idempotency_key}, "idempotency_key")
        result = self._validate_analysis_result(analysis_result)
        payload = {
            "schema_version": "mobile_result_message.v1",
            "message_type": "ANALYSIS_RESULT",
            "analysis_result": result,
        }
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        payload_sha256 = sha256(payload_json.encode("utf-8")).hexdigest()
        with self._lock:
            self._require_registered_device(device_id)
            existing = self._connection.execute(
                """
                SELECT message_id, payload_sha256, payload_json, status, created_at, delivered_at, acknowledged_at
                FROM mobile_result_outbox WHERE device_id = ? AND idempotency_key = ?
                """,
                (device_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing[1] != payload_sha256:
                    raise MobileResultOutboxError("idempotency_key_reused_with_different_result")
                return self._row_to_message(existing)

            message_id = f"pc-result-{uuid4()}"
            created_at = _timestamp(self._now())
            self._connection.execute(
                """
                INSERT INTO mobile_result_outbox(
                    message_id, device_id, idempotency_key, payload_sha256, payload_json, status,
                    created_at, delivered_at, acknowledged_at
                ) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, NULL, NULL)
                """,
                (message_id, device_id, idempotency_key, payload_sha256, payload_json, created_at),
            )
            self._connection.commit()
        return {
            "message_id": message_id,
            "payload": payload,
            "status": "PENDING",
            "created_at": created_at,
            "delivered_at": None,
            "acknowledged_at": None,
        }

    def pull(self, *, device_id: str, access_token: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return pending and unacknowledged deliveries; ACK is required for removal."""
        device_id = _required_text({"device_id": device_id}, "device_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise MobileResultOutboxError("pull_limit_must_be_between_1_and_100")
        with self._lock:
            self._authorize(device_id, access_token)
            rows = self._connection.execute(
                """
                SELECT message_id, payload_sha256, payload_json, status, created_at, delivered_at, acknowledged_at
                FROM mobile_result_outbox
                WHERE device_id = ? AND status IN ('PENDING', 'DELIVERED')
                ORDER BY created_at, message_id LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
            delivered_at = _timestamp(self._now())
            pending_ids = [row[0] for row in rows if row[3] == "PENDING"]
            if pending_ids:
                self._connection.executemany(
                    """
                    UPDATE mobile_result_outbox SET status = 'DELIVERED', delivered_at = ?
                    WHERE message_id = ? AND status = 'PENDING'
                    """,
                    [(delivered_at, message_id) for message_id in pending_ids],
                )
                self._connection.commit()
            messages = [self._row_to_message(row) for row in rows]
        for message in messages:
            if message["status"] == "PENDING":
                message["status"] = "DELIVERED"
                message["delivered_at"] = delivered_at
        return messages

    def acknowledge(self, *, device_id: str, access_token: str, message_id: str) -> dict[str, Any]:
        """Idempotently acknowledge a delivery owned by the calling paired device."""
        device_id = _required_text({"device_id": device_id}, "device_id")
        message_id = _required_text({"message_id": message_id}, "message_id")
        with self._lock:
            self._authorize(device_id, access_token)
            row = self._connection.execute(
                """
                SELECT message_id, payload_sha256, payload_json, status, created_at, delivered_at, acknowledged_at
                FROM mobile_result_outbox WHERE message_id = ? AND device_id = ?
                """,
                (message_id, device_id),
            ).fetchone()
            if row is None:
                raise MobileResultOutboxError("outbox_message_not_found")
            if row[3] != "ACKED":
                acknowledged_at = _timestamp(self._now())
                self._connection.execute(
                    """
                    UPDATE mobile_result_outbox
                    SET status = 'ACKED', acknowledged_at = ?
                    WHERE message_id = ? AND device_id = ?
                    """,
                    (acknowledged_at, message_id, device_id),
                )
                self._connection.commit()
                row = (*row[:3], "ACKED", *row[4:6], acknowledged_at)
            return self._row_to_message(row)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _require_registered_device(self, device_id: str) -> None:
        row = self._connection.execute(
            "SELECT 1 FROM mobile_devices WHERE device_id = ? AND revoked_at IS NULL", (device_id,)
        ).fetchone()
        if row is None:
            raise MobileResultOutboxError("paired_device_not_found")

    def _authorize(self, device_id: str, access_token: str) -> None:
        access_token = _required_text({"access_token": access_token}, "access_token")
        row = self._connection.execute(
            """
            SELECT 1 FROM mobile_devices
            WHERE device_id = ? AND access_token_sha256 = ? AND revoked_at IS NULL
            """,
            (device_id, _digest(access_token)),
        ).fetchone()
        if row is None:
            raise MobileResultOutboxAuthenticationError("mobile_device_access_denied")

    @staticmethod
    def _validate_analysis_result(value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise MobileResultOutboxError("analysis_result_must_be_an_object")
        result = dict(value)
        if result.get("schema_version") != "pc_knowledge_analysis_result.v1":
            raise MobileResultOutboxError("analysis_result_schema_version_not_supported")
        for field in ("result_id", "session_id", "visit_id", "created_at"):
            _required_text(result, field)
        evidence_refs = result.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs or not all(
            isinstance(reference, str) and reference.strip() for reference in evidence_refs
        ):
            raise MobileResultOutboxError("analysis_result_evidence_refs_must_be_a_non_empty_string_list")
        associations = result.get("associations")
        if not isinstance(associations, list) or not all(
            isinstance(association, Mapping) for association in associations
        ):
            raise MobileResultOutboxError("analysis_result_associations_must_be_an_object_list")
        return result

    @staticmethod
    def _row_to_message(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "message_id": row[0],
            "payload": json.loads(row[2]),
            "status": row[3],
            "created_at": row[4],
            "delivered_at": row[5],
            "acknowledged_at": row[6],
        }
