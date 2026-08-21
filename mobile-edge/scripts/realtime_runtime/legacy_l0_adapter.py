"""Read-only adapter from legacy fused windows to v2 immutable L0 facts.

It is deliberately incapable of creating SemanticScope, L1, graph, interest
or notification output. T007 may use it only while the lane workers still
write their legacy evidence ledger.
"""

from __future__ import annotations

import hashlib
import json

from .contracts import FusedCandidate, RealtimeSemanticFact, SourceContext, SourceKind


class LegacyL0AdapterError(ValueError):
    """A legacy record that cannot safely enter the v2 L0-only migration path."""


_SOURCE_KIND = {
    SourceContext.PHONE_DAILY: SourceKind.PHONE_SCREEN,
    SourceContext.PC_LEARNING: SourceKind.PC_LEARNING,
    SourceContext.GLASSES_LEARNING: SourceKind.GLASSES_FIRST_PERSON,
}
_POLICY_VERSION = "legacy-fused-window-read-only-adapter.v2"
_PROVENANCE_HASH = hashlib.sha256(_POLICY_VERSION.encode("utf-8")).hexdigest()


def _hash_payload(candidate: FusedCandidate, evidence_hashes: tuple[str, ...]) -> str:
    payload = {
        "window_id": candidate.window_id,
        "visit_id": candidate.visit_id,
        "source_context": candidate.source_context.value,
        "start_pts_ns": candidate.start_pts_ns,
        "end_pts_ns": candidate.end_pts_ns,
        "evidence_uris": candidate.evidence_uris,
        "evidence_hashes": evidence_hashes,
        "fusion_mode": candidate.fusion_mode.value,
        "classification": candidate.classification,
    }
    source = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(source).hexdigest()


def fused_candidate_to_l0_fact(
    candidate: FusedCandidate,
    *,
    session_id: str,
    learner_id: str,
    capture_consent_id: str,
    consent_generation: int,
    evidence_hashes: tuple[str, ...],
) -> RealtimeSemanticFact:
    """Create an auditable evidence fact, never a learning conclusion.

    ``evidence_hashes`` must come from the existing sealed lane-evidence
    ledger; URIs alone never prove the artifact bytes that were analysed.
    """

    if candidate.classification != "CANDIDATE_ONLY":
        raise LegacyL0AdapterError("legacy_candidate_classification_not_read_only")
    if not session_id or not learner_id or not capture_consent_id:
        raise LegacyL0AdapterError("legacy_l0_scope_identity_invalid")
    if len(evidence_hashes) != len(candidate.evidence_uris) or not evidence_hashes:
        raise LegacyL0AdapterError("legacy_l0_evidence_count_invalid")
    if any(len(item) != 64 for item in evidence_hashes) or len(set(evidence_hashes)) != len(evidence_hashes):
        raise LegacyL0AdapterError("legacy_l0_evidence_hashes_invalid")
    content_hash = _hash_payload(candidate, evidence_hashes)
    return RealtimeSemanticFact(
        fact_id=f"v2-l0:{content_hash}",
        idempotency_key=f"legacy-fused-window:{candidate.window_id}:{content_hash}",
        learner_id=learner_id,
        session_id=session_id,
        episode_id=f"legacy-read-only:{candidate.visit_id}",
        capture_consent_id=capture_consent_id,
        consent_generation=consent_generation,
        source_kind=_SOURCE_KIND[candidate.source_context],
        start_pts_ns=candidate.start_pts_ns,
        end_pts_ns=candidate.end_pts_ns,
        fact_kind="LEGACY_FUSED_WINDOW_EVIDENCE_ONLY",
        content_hash=content_hash,
        evidence_hashes=evidence_hashes,
        semantic_policy_version=_POLICY_VERSION,
        provenance_hash=_PROVENANCE_HASH,
    )
