"""Fail-closed reducer from durable v2 lane evidence to a semantic scope.

The reducer is intentionally narrower than an L1 pipeline.  It can only
record that a bounded, continuous media range has complete and stable semantic
evidence.  Interest, learning value, packages, notifications and all student
facing effects remain downstream gates.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .contracts import (
    ContentEpisode,
    SemanticAudioRequirement,
    SemanticCompleteness,
    SemanticScope,
    SemanticScopeStability,
)
from .semantic_ledger import RealtimeSemanticLedger


_REQUIRED_LANES = frozenset({"OCR", "ASR", "VLM"})
_POLICY_VERSION = "v2-durable-trimodal-scope-reducer.v1"


def _stable_hash(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class V2SemanticLaneEvidence:
    """One analyzer result, bound to the L0 fact that made it durable."""

    lane: str
    fact_id: str
    coverage_start_pts_ns: int
    coverage_end_pts_ns: int
    evidence_hash: str

    def __post_init__(self) -> None:
        if (
            self.lane not in _REQUIRED_LANES
            or not self.fact_id
            or self.coverage_start_pts_ns < 0
            or self.coverage_end_pts_ns <= self.coverage_start_pts_ns
            or len(self.evidence_hash) != 64
        ):
            raise ValueError("v2_semantic_lane_evidence_invalid")


@dataclass(frozen=True)
class V2SemanticWindowAssessment:
    """A prospective stable scope; all bytes stay with the owning lane."""

    episode: ContentEpisode
    start_pts_ns: int
    end_pts_ns: int
    semantic_lineage_id: str
    inference_provenance_hash: str
    runtime_semantic_risk: str
    semantic_audio_requirement: SemanticAudioRequirement | None
    lane_evidence: tuple[V2SemanticLaneEvidence, ...]

    def __post_init__(self) -> None:
        if (
            self.start_pts_ns < self.episode.continuity_start_pts_ns
            or self.end_pts_ns <= self.start_pts_ns
            or not self.semantic_lineage_id
            or len(self.inference_provenance_hash) != 64
            or not self.runtime_semantic_risk
        ):
            raise ValueError("v2_semantic_window_assessment_invalid")


@dataclass(frozen=True)
class V2SemanticScopeReduction:
    state: str
    scope: SemanticScope | None


class V2SemanticScopeReducer:
    """Records scopes only after every window-level safety proof is present."""

    def __init__(self, ledger: RealtimeSemanticLedger) -> None:
        self._ledger = ledger

    def reduce(self, assessment: V2SemanticWindowAssessment) -> V2SemanticScopeReduction:
        if assessment.semantic_audio_requirement is SemanticAudioRequirement.AUDIO_REQUIRED_UNRESOLVED:
            return V2SemanticScopeReduction("L0_ONLY_AUDIO_REQUIRED_UNRESOLVED", None)
        if assessment.runtime_semantic_risk != "CLEAR":
            return V2SemanticScopeReduction("L0_ONLY_RUNTIME_RISK", None)

        lane_names = tuple(item.lane for item in assessment.lane_evidence)
        if frozenset(lane_names) != _REQUIRED_LANES or len(lane_names) != len(_REQUIRED_LANES):
            return V2SemanticScopeReduction("L0_ONLY_MODALITY_INCOMPLETE", None)
        if any(
            item.coverage_start_pts_ns != assessment.start_pts_ns
            or item.coverage_end_pts_ns != assessment.end_pts_ns
            for item in assessment.lane_evidence
        ):
            return V2SemanticScopeReduction("L0_ONLY_EVIDENCE_RANGE_MISMATCH", None)

        episode = assessment.episode
        if any(
            not self._ledger.has_durable_fact(
                fact_id=item.fact_id,
                learner_id=episode.learner_id,
                session_id=episode.session_id,
                episode_id=episode.episode_id,
                capture_consent_id=episode.capture_consent_id,
                consent_generation=episode.consent_generation,
                start_pts_ns=assessment.start_pts_ns,
                end_pts_ns=assessment.end_pts_ns,
                content_hash=item.evidence_hash,
            )
            for item in assessment.lane_evidence
        ):
            return V2SemanticScopeReduction("L0_ONLY_EVIDENCE_NOT_DURABLE", None)

        scope_hash = _stable_hash(
            {
                "policy_version": _POLICY_VERSION,
                "episode_id": episode.episode_id,
                "start_pts_ns": assessment.start_pts_ns,
                "end_pts_ns": assessment.end_pts_ns,
                "semantic_lineage_id": assessment.semantic_lineage_id,
                "inference_provenance_hash": assessment.inference_provenance_hash,
                "semantic_audio_requirement": (
                    None if assessment.semantic_audio_requirement is None else assessment.semantic_audio_requirement.value
                ),
                "lane_evidence": [
                    {
                        "lane": item.lane,
                        "fact_id": item.fact_id,
                        "evidence_hash": item.evidence_hash,
                    }
                    for item in sorted(assessment.lane_evidence, key=lambda item: item.lane)
                ],
            }
        )
        scope = SemanticScope(
            scope_id=f"v2-scope:{scope_hash[:32]}",
            episode=episode,
            start_pts_ns=assessment.start_pts_ns,
            end_pts_ns=assessment.end_pts_ns,
            scope_hash=scope_hash,
            semantic_lineage_id=assessment.semantic_lineage_id,
            completeness=SemanticCompleteness.WINDOW_COMPLETE,
            stability=SemanticScopeStability.STABLE,
            semantic_revision=1,
            event_time_watermark_ns=assessment.end_pts_ns,
        )
        self._ledger.record_scope(scope)
        return V2SemanticScopeReduction("SCOPE_RECORDED", scope)
