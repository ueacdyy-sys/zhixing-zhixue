from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.contracts import (  # noqa: E402
    ContentEpisode,
    EpisodeStatus,
    RealtimeSemanticFact,
    SemanticAudioRequirement,
    SourceKind,
)
from realtime_runtime.semantic_ledger import RealtimeSemanticLedger  # noqa: E402
from realtime_runtime.v2_semantic_scope_reducer import (  # noqa: E402
    V2SemanticLaneEvidence,
    V2SemanticScopeReducer,
    V2SemanticWindowAssessment,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def _episode() -> ContentEpisode:
    return ContentEpisode(
        episode_id="episode-v2-1",
        learner_id="learner-1",
        session_id="capture-1",
        capture_consent_id="consent-1",
        consent_generation=3,
        source_kind=SourceKind.PHONE_SCREEN,
        start_pts_ns=0,
        continuity_start_pts_ns=0,
        end_pts_ns=None,
        status=EpisodeStatus.OPEN,
        boundary_confidence=1.0,
        boundary_reason="v2-contiguous-capture",
        resolver_version="v2-episode.v1",
        policy_version="semantic.v2",
    )


def _fact(fact_id: str, content_hash: str) -> RealtimeSemanticFact:
    return RealtimeSemanticFact(
        fact_id=fact_id,
        idempotency_key=f"idem-{fact_id}",
        learner_id="learner-1",
        session_id="capture-1",
        episode_id="episode-v2-1",
        capture_consent_id="consent-1",
        consent_generation=3,
        source_kind=SourceKind.PHONE_SCREEN,
        start_pts_ns=0,
        end_pts_ns=100,
        fact_kind="v2-semantic-lane-evidence",
        content_hash=content_hash,
        evidence_hashes=(content_hash,),
        semantic_policy_version="semantic.v2",
        provenance_hash=HASH_D,
    )


def _assessment(*, audio_requirement: SemanticAudioRequirement | None = None, risk: str = "CLEAR") -> V2SemanticWindowAssessment:
    return V2SemanticWindowAssessment(
        episode=_episode(),
        start_pts_ns=0,
        end_pts_ns=100,
        semantic_lineage_id="lineage-v2-1",
        inference_provenance_hash=HASH_D,
        runtime_semantic_risk=risk,
        semantic_audio_requirement=audio_requirement,
        lane_evidence=(
            V2SemanticLaneEvidence("OCR", "fact-ocr", 0, 100, HASH_A),
            V2SemanticLaneEvidence("ASR", "fact-asr", 0, 100, HASH_B),
            V2SemanticLaneEvidence("VLM", "fact-vlm", 0, 100, HASH_C),
        ),
    )


def test_complete_v2_trimodal_window_records_a_stable_scope_only_after_all_l0_evidence_is_durable() -> None:
    with tempfile.TemporaryDirectory() as temp_dir, RealtimeSemanticLedger(Path(temp_dir) / "semantic.sqlite") as ledger:
        for fact_id, content_hash in (("fact-ocr", HASH_A), ("fact-asr", HASH_B), ("fact-vlm", HASH_C)):
            assert ledger.append_fact(_fact(fact_id, content_hash))

        result = V2SemanticScopeReducer(ledger).reduce(_assessment())

    assert result.state == "SCOPE_RECORDED"
    assert result.scope is not None
    assert result.scope.scope_id.startswith("v2-scope:")
    assert result.scope.completeness.value == "WINDOW_COMPLETE"
    assert result.scope.stability.value == "STABLE"


@pytest.mark.parametrize(
    ("assessment", "expected"),
    (
        (_assessment(audio_requirement=SemanticAudioRequirement.AUDIO_REQUIRED_UNRESOLVED), "L0_ONLY_AUDIO_REQUIRED_UNRESOLVED"),
        (_assessment(risk="ABSTAIN_L0_ONLY"), "L0_ONLY_RUNTIME_RISK"),
        (
            V2SemanticWindowAssessment(
                **{
                    **_assessment().__dict__,
                    "lane_evidence": (
                        V2SemanticLaneEvidence("OCR", "fact-ocr", 0, 100, HASH_A),
                        V2SemanticLaneEvidence("VLM", "fact-vlm", 0, 100, HASH_C),
                    ),
                }
            ),
            "L0_ONLY_MODALITY_INCOMPLETE",
        ),
        (
            V2SemanticWindowAssessment(
                **{
                    **_assessment().__dict__,
                    "lane_evidence": (
                        V2SemanticLaneEvidence("OCR", "fact-ocr", 0, 100, HASH_A),
                        V2SemanticLaneEvidence("ASR", "fact-asr", 10, 100, HASH_B),
                        V2SemanticLaneEvidence("VLM", "fact-vlm", 0, 100, HASH_C),
                    ),
                }
            ),
            "L0_ONLY_EVIDENCE_RANGE_MISMATCH",
        ),
    ),
)
def test_v2_scope_reducer_fails_closed_for_audio_risk_missing_modalities_or_misaligned_evidence(
    assessment: V2SemanticWindowAssessment,
    expected: str,
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir, RealtimeSemanticLedger(Path(temp_dir) / "semantic.sqlite") as ledger:
        for fact_id, content_hash in (("fact-ocr", HASH_A), ("fact-asr", HASH_B), ("fact-vlm", HASH_C)):
            assert ledger.append_fact(_fact(fact_id, content_hash))

        result = V2SemanticScopeReducer(ledger).reduce(assessment)

    assert result.state == expected
    assert result.scope is None
