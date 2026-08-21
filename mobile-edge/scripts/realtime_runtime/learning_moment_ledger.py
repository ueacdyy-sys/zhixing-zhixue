"""Durable LearningMoment identity, revision and notification-slot ledger.

This is deliberately a PC domain ledger.  It never posts Android notifications:
it only makes it impossible for scope/package/graph retries to mint a second
ordinary intervention key.  Android must mirror these invariants in its Room
transaction before T099 can be marked complete.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3

from .contracts import LearningMoment, LearningMomentRevision
from .content_package import ContentAnalysisPackageV2


class LearningMomentLedgerError(ValueError):
    """A moment identity, revision chain or intervention budget was violated."""


class ReservationState:
    RESERVED = "RESERVED"
    ALREADY_RESERVED = "ALREADY_RESERVED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


@dataclass(frozen=True)
class MomentClaim:
    moment_id: str
    intervention_key: str
    current_revision_id: str
    created: bool


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LearningMomentLedger:
    """SQLite authority for stable learning anchors inside one media episode."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def __enter__(self) -> "LearningMomentLedger":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS learning_moments (
                moment_id TEXT PRIMARY KEY,
                learner_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                episode_id TEXT NOT NULL,
                capture_consent_id TEXT NOT NULL,
                consent_generation INTEGER NOT NULL,
                source_kind TEXT NOT NULL,
                semantic_lineage_id TEXT NOT NULL,
                learning_anchor_id TEXT NOT NULL,
                intervention_key TEXT NOT NULL UNIQUE,
                current_revision_id TEXT NOT NULL,
                state TEXT NOT NULL,
                created_elapsed_ns INTEGER NOT NULL,
                policy_version TEXT NOT NULL,
                record_hash TEXT NOT NULL,
                UNIQUE(learner_id, episode_id, semantic_lineage_id, learning_anchor_id)
            );
            CREATE TABLE IF NOT EXISTS learning_moment_revisions (
                revision_id TEXT PRIMARY KEY,
                moment_id TEXT NOT NULL,
                revision_number INTEGER NOT NULL,
                replaces_revision_id TEXT,
                anchor_scope_id TEXT NOT NULL,
                anchor_scope_hash TEXT NOT NULL,
                anchor_scope_revision INTEGER NOT NULL,
                interest_assessment_id TEXT NOT NULL,
                learning_offer_assessment_id TEXT NOT NULL,
                evidence_hash TEXT NOT NULL,
                revision_reason TEXT NOT NULL,
                created_elapsed_ns INTEGER NOT NULL,
                record_hash TEXT NOT NULL,
                UNIQUE(moment_id, revision_number),
                FOREIGN KEY(moment_id) REFERENCES learning_moments(moment_id),
                FOREIGN KEY(replaces_revision_id) REFERENCES learning_moment_revisions(revision_id)
            );
            CREATE TABLE IF NOT EXISTS normal_intervention_slots (
                learner_id TEXT NOT NULL,
                episode_id TEXT NOT NULL,
                slot_number INTEGER NOT NULL CHECK(slot_number IN (1, 2)),
                moment_id TEXT NOT NULL,
                substantial_anchor_evidence_hash TEXT,
                student_subscription_attestation_id TEXT,
                reserved_elapsed_ns INTEGER NOT NULL,
                PRIMARY KEY(learner_id, episode_id, slot_number),
                UNIQUE(moment_id),
                FOREIGN KEY(moment_id) REFERENCES learning_moments(moment_id)
            );
            CREATE TABLE IF NOT EXISTS correction_intervention_slots (
                moment_id TEXT PRIMARY KEY,
                correction_revision_id TEXT NOT NULL UNIQUE,
                presented_brief_id TEXT NOT NULL,
                substantive_error_evidence_hash TEXT NOT NULL,
                reserved_elapsed_ns INTEGER NOT NULL,
                FOREIGN KEY(moment_id) REFERENCES learning_moments(moment_id),
                FOREIGN KEY(correction_revision_id) REFERENCES learning_moment_revisions(revision_id)
            );
            """
        )
        self._connection.commit()

    def claim(self, moment: LearningMoment) -> MomentClaim:
        """Create a stable anchor once, or return the canonical previous one.

        The uniqueness key intentionally excludes scope/package/assessment IDs.
        A retry with a freshly generated moment ID therefore cannot escape the
        original intervention key.
        """

        episode = moment.episode
        existing = self._connection.execute(
            """
            SELECT moment_id, intervention_key, current_revision_id
            FROM learning_moments
            WHERE learner_id = ? AND episode_id = ? AND semantic_lineage_id = ? AND learning_anchor_id = ?
            """,
            (episode.learner_id, episode.episode_id, moment.semantic_lineage_id, moment.learning_anchor_id),
        ).fetchone()
        if existing is not None:
            return MomentClaim(
                moment_id=str(existing["moment_id"]),
                intervention_key=str(existing["intervention_key"]),
                current_revision_id=str(existing["current_revision_id"]),
                created=False,
            )
        record_hash = _canonical_hash(asdict(moment))
        try:
            self._connection.execute(
                """
                INSERT INTO learning_moments(
                    moment_id, learner_id, session_id, episode_id, capture_consent_id,
                    consent_generation, source_kind, semantic_lineage_id, learning_anchor_id,
                    intervention_key, current_revision_id, state, created_elapsed_ns,
                    policy_version, record_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    moment.moment_id,
                    episode.learner_id,
                    episode.session_id,
                    episode.episode_id,
                    episode.capture_consent_id,
                    episode.consent_generation,
                    episode.source_kind.value,
                    moment.semantic_lineage_id,
                    moment.learning_anchor_id,
                    moment.intervention_key,
                    moment.current_revision_id,
                    moment.status.value,
                    moment.created_elapsed_ns,
                    moment.policy_version,
                    record_hash,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise LearningMomentLedgerError("learning_moment_identity_conflict") from error
        self._connection.commit()
        return MomentClaim(
            moment_id=moment.moment_id,
            intervention_key=moment.intervention_key,
            current_revision_id=moment.current_revision_id,
            created=True,
        )

    def record_revision(self, revision: LearningMomentRevision) -> bool:
        """Append one immutable revision and atomically move the current pointer."""

        moment = revision.moment
        row = self._connection.execute(
            "SELECT * FROM learning_moments WHERE moment_id = ?", (moment.moment_id,)
        ).fetchone()
        if row is None:
            raise LearningMomentLedgerError("learning_moment_missing")
        if (
            str(row["learner_id"]) != moment.episode.learner_id
            or str(row["session_id"]) != moment.episode.session_id
            or str(row["episode_id"]) != moment.episode.episode_id
            or str(row["capture_consent_id"]) != moment.episode.capture_consent_id
            or int(row["consent_generation"]) != moment.episode.consent_generation
            or str(row["semantic_lineage_id"]) != moment.semantic_lineage_id
            or str(row["learning_anchor_id"]) != moment.learning_anchor_id
            or str(row["intervention_key"]) != moment.intervention_key
        ):
            raise LearningMomentLedgerError("learning_moment_scope_mismatch")
        record_hash = _canonical_hash(asdict(revision))
        existing = self._connection.execute(
            "SELECT record_hash FROM learning_moment_revisions WHERE revision_id = ?", (revision.revision_id,)
        ).fetchone()
        if existing is not None:
            if str(existing["record_hash"]) != record_hash:
                raise LearningMomentLedgerError("learning_moment_revision_idempotency_conflict")
            return False
        current_revision_id = str(row["current_revision_id"])
        if revision.revision == 1:
            if revision.revision_id != current_revision_id or revision.replaces_revision_id is not None:
                raise LearningMomentLedgerError("initial_moment_revision_mismatch")
        else:
            if revision.replaces_revision_id != current_revision_id:
                raise LearningMomentLedgerError("moment_revision_predecessor_mismatch")
            predecessor = self._connection.execute(
                "SELECT revision_number FROM learning_moment_revisions WHERE revision_id = ? AND moment_id = ?",
                (revision.replaces_revision_id, moment.moment_id),
            ).fetchone()
            if predecessor is None or int(predecessor["revision_number"]) + 1 != revision.revision:
                raise LearningMomentLedgerError("moment_revision_predecessor_mismatch")
            if moment.current_revision_id != revision.revision_id:
                raise LearningMomentLedgerError("moment_current_revision_mismatch")
        scope = revision.anchor_scope
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                """
                INSERT INTO learning_moment_revisions(
                    revision_id, moment_id, revision_number, replaces_revision_id,
                    anchor_scope_id, anchor_scope_hash, anchor_scope_revision,
                    interest_assessment_id, learning_offer_assessment_id, evidence_hash,
                    revision_reason, created_elapsed_ns, record_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision.revision_id,
                    moment.moment_id,
                    revision.revision,
                    revision.replaces_revision_id,
                    scope.scope_id,
                    scope.scope_hash,
                    scope.semantic_revision,
                    revision.interest_assessment_id,
                    revision.learning_offer_assessment_id,
                    _canonical_hash(revision.evidence_hashes),
                    revision.revision_reason,
                    revision.created_elapsed_ns,
                    record_hash,
                ),
            )
            self._connection.execute(
                """
                UPDATE learning_moments
                SET current_revision_id = ?, state = ?
                WHERE moment_id = ?
                """,
                (revision.revision_id, moment.status.value, moment.moment_id),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return True

    def assert_package_registered(self, package: ContentAnalysisPackageV2) -> None:
        """Require PC delivery to reference the durable moment revision it claims.

        This is deliberately checked before the package enters the PC outbox,
        rather than after an Android ACK.  A package cannot make a transient
        scope/graph retry look like a fresh learning opportunity.
        """

        moment = package.learning_moment
        revision = package.learning_moment_revision
        row = self._connection.execute(
            """
            SELECT learner_id, session_id, episode_id, capture_consent_id,
                   consent_generation, semantic_lineage_id, intervention_key,
                   current_revision_id
            FROM learning_moments WHERE moment_id = ?
            """,
            (moment.moment_id,),
        ).fetchone()
        if row is None:
            raise LearningMomentLedgerError("content_package_moment_unregistered")
        episode = moment.episode
        if (
            str(row["learner_id"]) != package.learner_id
            or str(row["session_id"]) != package.session_id
            or str(row["episode_id"]) != package.episode_id
            or str(row["capture_consent_id"]) != package.capture_consent_id
            or int(row["consent_generation"]) != package.consent_generation
            or str(row["semantic_lineage_id"]) != package.semantic_scope.semantic_lineage_id
            or str(row["intervention_key"]) != package.l1.l1_intervention_key
            or str(row["current_revision_id"]) != revision.revision_id
            or episode.episode_id != package.episode_id
        ):
            raise LearningMomentLedgerError("content_package_moment_scope_mismatch")
        stored_revision = self._connection.execute(
            """
            SELECT moment_id, anchor_scope_id, anchor_scope_hash, anchor_scope_revision,
                   interest_assessment_id, learning_offer_assessment_id
            FROM learning_moment_revisions WHERE revision_id = ?
            """,
            (revision.revision_id,),
        ).fetchone()
        scope = package.semantic_scope
        if stored_revision is None or (
            str(stored_revision["moment_id"]) != moment.moment_id
            or str(stored_revision["anchor_scope_id"]) != scope.scope_id
            or str(stored_revision["anchor_scope_hash"]) != scope.scope_hash
            or int(stored_revision["anchor_scope_revision"]) != scope.semantic_revision
            or str(stored_revision["interest_assessment_id"]) != package.interest_assessment.assessment_id
            or str(stored_revision["learning_offer_assessment_id"])
            != package.learning_offer_assessment.assessment_id
        ):
            raise LearningMomentLedgerError("content_package_moment_revision_unregistered")

    def reserve_normal_slot(self, moment: LearningMoment, *, now_elapsed_ns: int) -> str:
        return self._reserve_slot(moment, slot_number=1, now_elapsed_ns=now_elapsed_ns)

    def reserve_second_slot(
        self,
        moment: LearningMoment,
        *,
        now_elapsed_ns: int,
        substantial_anchor_evidence_hash: str | None,
        student_subscription_attestation_id: str | None,
    ) -> str:
        if (
            substantial_anchor_evidence_hash is None
            or len(substantial_anchor_evidence_hash) != 64
            or not student_subscription_attestation_id
        ):
            raise LearningMomentLedgerError("second_slot_policy_evidence_required")
        return self._reserve_slot(
            moment,
            slot_number=2,
            now_elapsed_ns=now_elapsed_ns,
            substantial_anchor_evidence_hash=substantial_anchor_evidence_hash,
            student_subscription_attestation_id=student_subscription_attestation_id,
        )

    def reserve_correction_slot(
        self,
        moment: LearningMoment,
        *,
        correction_revision_id: str,
        now_elapsed_ns: int,
        presented_brief_id: str | None,
        substantive_error_evidence_hash: str | None,
    ) -> str:
        """Reserve one exceptional correction notice, never a normal slot retry."""

        if (
            not correction_revision_id
            or not presented_brief_id
            or substantive_error_evidence_hash is None
            or len(substantive_error_evidence_hash) != 64
            or now_elapsed_ns < 0
        ):
            raise LearningMomentLedgerError("correction_policy_evidence_required")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            stored_revision = self._connection.execute(
                "SELECT moment_id FROM learning_moment_revisions WHERE revision_id = ?",
                (correction_revision_id,),
            ).fetchone()
            if stored_revision is None or str(stored_revision["moment_id"]) != moment.moment_id:
                raise LearningMomentLedgerError("correction_revision_scope_mismatch")
            existing = self._connection.execute(
                "SELECT correction_revision_id FROM correction_intervention_slots WHERE moment_id = ?",
                (moment.moment_id,),
            ).fetchone()
            if existing is not None:
                self._connection.commit()
                return ReservationState.ALREADY_RESERVED
            self._connection.execute(
                """
                INSERT INTO correction_intervention_slots(
                    moment_id, correction_revision_id, presented_brief_id,
                    substantive_error_evidence_hash, reserved_elapsed_ns
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    moment.moment_id,
                    correction_revision_id,
                    presented_brief_id,
                    substantive_error_evidence_hash,
                    now_elapsed_ns,
                ),
            )
            self._connection.commit()
            return ReservationState.RESERVED
        except Exception:
            self._connection.rollback()
            raise

    def _reserve_slot(
        self,
        moment: LearningMoment,
        *,
        slot_number: int,
        now_elapsed_ns: int,
        substantial_anchor_evidence_hash: str | None = None,
        student_subscription_attestation_id: str | None = None,
    ) -> str:
        if now_elapsed_ns < 0:
            raise LearningMomentLedgerError("intervention_slot_time_invalid")
        episode = moment.episode
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            stored = self._connection.execute(
                "SELECT learner_id, episode_id, learning_anchor_id FROM learning_moments WHERE moment_id = ?",
                (moment.moment_id,),
            ).fetchone()
            if stored is None:
                raise LearningMomentLedgerError("intervention_slot_unknown_moment")
            if str(stored["learner_id"]) != episode.learner_id or str(stored["episode_id"]) != episode.episode_id:
                raise LearningMomentLedgerError("intervention_slot_scope_mismatch")
            already = self._connection.execute(
                "SELECT slot_number FROM normal_intervention_slots WHERE moment_id = ?", (moment.moment_id,)
            ).fetchone()
            if already is not None:
                self._connection.commit()
                return ReservationState.ALREADY_RESERVED
            occupied = self._connection.execute(
                """
                SELECT s.moment_id, m.learning_anchor_id
                FROM normal_intervention_slots s
                JOIN learning_moments m ON m.moment_id = s.moment_id
                WHERE s.learner_id = ? AND s.episode_id = ? AND s.slot_number = ?
                """,
                (episode.learner_id, episode.episode_id, slot_number),
            ).fetchone()
            if occupied is not None:
                self._connection.commit()
                return ReservationState.BUDGET_EXHAUSTED
            if slot_number == 2:
                first = self._connection.execute(
                    """
                    SELECT m.learning_anchor_id FROM normal_intervention_slots s
                    JOIN learning_moments m ON m.moment_id = s.moment_id
                    WHERE s.learner_id = ? AND s.episode_id = ? AND s.slot_number = 1
                    """,
                    (episode.learner_id, episode.episode_id),
                ).fetchone()
                if first is None or str(first["learning_anchor_id"]) == str(stored["learning_anchor_id"]):
                    raise LearningMomentLedgerError("second_slot_requires_distinct_anchor")
            self._connection.execute(
                """
                INSERT INTO normal_intervention_slots(
                    learner_id, episode_id, slot_number, moment_id,
                    substantial_anchor_evidence_hash, student_subscription_attestation_id,
                    reserved_elapsed_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode.learner_id,
                    episode.episode_id,
                    slot_number,
                    moment.moment_id,
                    substantial_anchor_evidence_hash,
                    student_subscription_attestation_id,
                    now_elapsed_ns,
                ),
            )
            self._connection.commit()
            return ReservationState.RESERVED
        except Exception:
            self._connection.rollback()
            raise
