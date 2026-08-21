"""Durable single-owner routing for PC-local, buffer-only and cloud analysis."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from .contracts import AnalysisRouteLease, AnalysisRouteState


class AnalysisRouteError(ValueError):
    """A route change that could duplicate, leak or silently reroute media."""


class AnalysisRouteLedger:
    """Route authority ledger. Media transport must query this before ingress/resume."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def __enter__(self) -> "AnalysisRouteLedger":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS analysis_route_leases (
                lease_id TEXT PRIMARY KEY,
                learner_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                capture_consent_id TEXT NOT NULL,
                consent_generation INTEGER NOT NULL,
                route_epoch INTEGER NOT NULL,
                state TEXT NOT NULL,
                owner_endpoint_id TEXT,
                opened_receipt_hash TEXT NOT NULL,
                student_confirmation_hash TEXT NOT NULL,
                issued_elapsed_ns INTEGER NOT NULL,
                last_renewed_elapsed_ns INTEGER NOT NULL,
                expires_elapsed_ns INTEGER NOT NULL,
                close_receipt_hash TEXT,
                active INTEGER NOT NULL CHECK (active IN (0, 1))
            );
            CREATE UNIQUE INDEX IF NOT EXISTS analysis_route_active_scope
                ON analysis_route_leases(learner_id, session_id, capture_consent_id, consent_generation)
                WHERE active = 1;
            """
        )
        columns = {str(row["name"]) for row in self._connection.execute("PRAGMA table_info(analysis_route_leases)")}
        # A development database from the pre-lease schema is deliberately
        # conservative after migration: its active row receives an expiry of
        # zero, so it cannot keep authorizing media without a fresh lease.
        for name in ("issued_elapsed_ns", "last_renewed_elapsed_ns", "expires_elapsed_ns"):
            if name not in columns:
                self._connection.execute(
                    f"ALTER TABLE analysis_route_leases ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0"
                )
        self._connection.commit()

    def open(self, lease: AnalysisRouteLease, *, now_elapsed_ns: int) -> None:
        if lease.state not in {AnalysisRouteState.PC_LOCAL_ACTIVE, AnalysisRouteState.CLOUD_ACTIVE, AnalysisRouteState.UNAVAILABLE}:
            raise AnalysisRouteError("route_open_state_invalid")
        self._assert_open_time(lease, now_elapsed_ns)
        existing = self._connection.execute(
            "SELECT * FROM analysis_route_leases WHERE lease_id = ?", (lease.lease_id,)
        ).fetchone()
        if existing is not None:
            if self._matches(existing, lease):
                self._assert_not_expired(existing, now_elapsed_ns)
                return
            raise AnalysisRouteError("route_lease_idempotency_conflict")
        self._expire_scope_if_needed(lease, now_elapsed_ns)
        maximum_epoch = self._connection.execute(
            """
            SELECT MAX(route_epoch) AS maximum_epoch FROM analysis_route_leases
            WHERE learner_id = ? AND session_id = ? AND capture_consent_id = ? AND consent_generation = ?
            """,
            (lease.learner_id, lease.session_id, lease.capture_consent_id, lease.consent_generation),
        ).fetchone()["maximum_epoch"]
        if maximum_epoch is not None and lease.route_epoch <= int(maximum_epoch):
            raise AnalysisRouteError("route_epoch_not_monotonic")
        try:
            self._connection.execute(
                """
                INSERT INTO analysis_route_leases(
                    lease_id, learner_id, session_id, capture_consent_id,
                    consent_generation, route_epoch, state, owner_endpoint_id,
                    opened_receipt_hash, student_confirmation_hash,
                    issued_elapsed_ns, last_renewed_elapsed_ns, expires_elapsed_ns, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    lease.lease_id,
                    lease.learner_id,
                    lease.session_id,
                    lease.capture_consent_id,
                    lease.consent_generation,
                    lease.route_epoch,
                    lease.state.value,
                    lease.owner_endpoint_id,
                    lease.opened_receipt_hash,
                    lease.student_confirmation_hash,
                    lease.issued_elapsed_ns,
                    lease.last_renewed_elapsed_ns,
                    lease.expires_elapsed_ns,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise AnalysisRouteError("route_scope_already_has_owner") from error
        self._connection.commit()

    def transition_pc_buffer(self, *, lease_id: str, route_epoch: int, endpoint_id: str, now_elapsed_ns: int) -> None:
        row = self._current(lease_id, now_elapsed_ns)
        self._assert_pc_owner(row, route_epoch, endpoint_id, AnalysisRouteState.PC_LOCAL_ACTIVE)
        self._connection.execute(
            "UPDATE analysis_route_leases SET state = ? WHERE lease_id = ?",
            (AnalysisRouteState.PC_BUFFER_ONLY.value, lease_id),
        )
        self._connection.commit()

    def restore_pc(self, *, lease_id: str, route_epoch: int, endpoint_id: str, now_elapsed_ns: int) -> None:
        row = self._current(lease_id, now_elapsed_ns)
        self._assert_pc_owner(row, route_epoch, endpoint_id, AnalysisRouteState.PC_BUFFER_ONLY)
        self._connection.execute(
            "UPDATE analysis_route_leases SET state = ? WHERE lease_id = ?",
            (AnalysisRouteState.PC_LOCAL_ACTIVE.value, lease_id),
        )
        self._connection.commit()

    def close_pc(self, *, lease_id: str, route_epoch: int, endpoint_id: str, close_receipt_hash: str, now_elapsed_ns: int) -> None:
        if len(close_receipt_hash) != 64:
            raise AnalysisRouteError("route_close_receipt_hash_invalid")
        row = self._current(lease_id, now_elapsed_ns)
        if str(row["state"]) not in {AnalysisRouteState.PC_LOCAL_ACTIVE.value, AnalysisRouteState.PC_BUFFER_ONLY.value}:
            raise AnalysisRouteError("route_close_requires_pc_route")
        self._assert_pc_owner(row, route_epoch, endpoint_id, AnalysisRouteState(str(row["state"])))
        self._connection.execute(
            "UPDATE analysis_route_leases SET state = ?, active = 0, close_receipt_hash = ? WHERE lease_id = ?",
            (AnalysisRouteState.CLOSED.value, close_receipt_hash, lease_id),
        )
        self._connection.commit()

    def open_cloud_after_pc_closed(
        self,
        lease: AnalysisRouteLease,
        *,
        prior_pc_lease_id: str | None,
        prior_close_receipt_hash: str | None,
        now_elapsed_ns: int,
    ) -> None:
        if lease.state is not AnalysisRouteState.CLOUD_ACTIVE:
            raise AnalysisRouteError("cloud_open_requires_cloud_state")
        if prior_pc_lease_id is not None:
            prior = self._connection.execute(
                "SELECT * FROM analysis_route_leases WHERE lease_id = ?", (prior_pc_lease_id,)
            ).fetchone()
            if (
                prior is None
                or str(prior["learner_id"]) != lease.learner_id
                or str(prior["state"]) != AnalysisRouteState.CLOSED.value
                or str(prior["close_receipt_hash"]) != prior_close_receipt_hash
                or str(prior["session_id"]) == lease.session_id
            ):
                raise AnalysisRouteError("cloud_open_requires_closed_prior_pc_session")
        elif prior_close_receipt_hash is not None:
            raise AnalysisRouteError("cloud_open_unbound_prior_receipt")
        self.open(lease, now_elapsed_ns=now_elapsed_ns)

    def renew(
        self,
        *,
        lease_id: str,
        route_epoch: int,
        endpoint_id: str,
        now_elapsed_ns: int,
        new_expires_elapsed_ns: int,
    ) -> None:
        row = self._current(lease_id, now_elapsed_ns)
        state = AnalysisRouteState(str(row["state"]))
        if state not in {AnalysisRouteState.PC_LOCAL_ACTIVE, AnalysisRouteState.PC_BUFFER_ONLY}:
            raise AnalysisRouteError("route_renew_requires_pc_route")
        self._assert_pc_owner(row, route_epoch, endpoint_id, state)
        if new_expires_elapsed_ns <= now_elapsed_ns or new_expires_elapsed_ns <= int(row["expires_elapsed_ns"]):
            raise AnalysisRouteError("route_renew_expiry_invalid")
        self._connection.execute(
            """
            UPDATE analysis_route_leases
            SET last_renewed_elapsed_ns = ?, expires_elapsed_ns = ?
            WHERE lease_id = ?
            """,
            (now_elapsed_ns, new_expires_elapsed_ns, lease_id),
        )
        self._connection.commit()

    def assert_pc_resume_authorized(
        self,
        *,
        lease_id: str,
        learner_id: str,
        session_id: str,
        capture_consent_id: str,
        consent_generation: int,
        route_epoch: int,
        endpoint_id: str,
        now_elapsed_ns: int,
    ) -> None:
        row = self._current(lease_id, now_elapsed_ns)
        if (
            str(row["learner_id"]) != learner_id
            or str(row["session_id"]) != session_id
            or str(row["capture_consent_id"]) != capture_consent_id
            or int(row["consent_generation"]) != consent_generation
        ):
            raise AnalysisRouteError("resume_route_scope_mismatch")
        self._assert_pc_owner(row, route_epoch, endpoint_id, AnalysisRouteState.PC_BUFFER_ONLY)

    def assert_pc_ingress_authorized(
        self,
        *,
        lease_id: str,
        learner_id: str,
        session_id: str,
        capture_consent_id: str,
        consent_generation: int,
        route_epoch: int,
        endpoint_id: str,
        now_elapsed_ns: int,
    ) -> None:
        """Require the active PC-local owner before v2 L0 accepts new output."""

        row = self._current(lease_id, now_elapsed_ns)
        if (
            str(row["learner_id"]) != learner_id
            or str(row["session_id"]) != session_id
            or str(row["capture_consent_id"]) != capture_consent_id
            or int(row["consent_generation"]) != consent_generation
        ):
            raise AnalysisRouteError("ingress_route_scope_mismatch")
        self._assert_pc_owner(row, route_epoch, endpoint_id, AnalysisRouteState.PC_LOCAL_ACTIVE)

    def _current(self, lease_id: str, now_elapsed_ns: int) -> sqlite3.Row:
        if now_elapsed_ns < 0:
            raise AnalysisRouteError("route_time_invalid")
        row = self._connection.execute(
            "SELECT * FROM analysis_route_leases WHERE lease_id = ? AND active = 1", (lease_id,)
        ).fetchone()
        if row is None:
            raise AnalysisRouteError("route_lease_not_active")
        self._assert_not_expired(row, now_elapsed_ns)
        return row

    def _expire_scope_if_needed(self, lease: AnalysisRouteLease, now_elapsed_ns: int) -> None:
        self._connection.execute(
            """
            UPDATE analysis_route_leases
            SET state = ?, active = 0
            WHERE learner_id = ? AND session_id = ? AND capture_consent_id = ? AND consent_generation = ?
              AND active = 1 AND expires_elapsed_ns <= ?
            """,
            (
                AnalysisRouteState.EXPIRED.value,
                lease.learner_id,
                lease.session_id,
                lease.capture_consent_id,
                lease.consent_generation,
                now_elapsed_ns,
            ),
        )

    def _assert_not_expired(self, row: sqlite3.Row, now_elapsed_ns: int) -> None:
        if int(row["expires_elapsed_ns"]) > now_elapsed_ns:
            return
        self._connection.execute(
            "UPDATE analysis_route_leases SET state = ?, active = 0 WHERE lease_id = ? AND active = 1",
            (AnalysisRouteState.EXPIRED.value, str(row["lease_id"])),
        )
        self._connection.commit()
        raise AnalysisRouteError("route_lease_expired")

    @staticmethod
    def _assert_open_time(lease: AnalysisRouteLease, now_elapsed_ns: int) -> None:
        if now_elapsed_ns < 0 or lease.issued_elapsed_ns > now_elapsed_ns or lease.last_renewed_elapsed_ns > now_elapsed_ns:
            raise AnalysisRouteError("route_time_invalid")
        if lease.expires_elapsed_ns <= now_elapsed_ns:
            raise AnalysisRouteError("route_lease_expired")

    @staticmethod
    def _assert_pc_owner(row: sqlite3.Row, route_epoch: int, endpoint_id: str, expected_state: AnalysisRouteState) -> None:
        if (
            str(row["state"]) != expected_state.value
            or int(row["route_epoch"]) != route_epoch
            or str(row["owner_endpoint_id"]) != endpoint_id
        ):
            raise AnalysisRouteError("route_owner_or_epoch_denied")

    @staticmethod
    def _matches(row: sqlite3.Row, lease: AnalysisRouteLease) -> bool:
        return (
            str(row["learner_id"]) == lease.learner_id
            and str(row["session_id"]) == lease.session_id
            and str(row["capture_consent_id"]) == lease.capture_consent_id
            and int(row["consent_generation"]) == lease.consent_generation
            and int(row["route_epoch"]) == lease.route_epoch
            and str(row["state"]) == lease.state.value
            and row["owner_endpoint_id"] == lease.owner_endpoint_id
            and str(row["opened_receipt_hash"]) == lease.opened_receipt_hash
            and str(row["student_confirmation_hash"]) == lease.student_confirmation_hash
            and int(row["issued_elapsed_ns"]) == lease.issued_elapsed_ns
            and int(row["last_renewed_elapsed_ns"]) == lease.last_renewed_elapsed_ns
            and int(row["expires_elapsed_ns"]) == lease.expires_elapsed_ns
        )
