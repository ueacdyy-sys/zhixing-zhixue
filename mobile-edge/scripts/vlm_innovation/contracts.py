"""Contracts shared by the dataset, Router and visual-cache experiments."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InnovationContractError(ValueError):
    """Raised before an experiment can make an unsafe evidence claim."""


class CacheAction(StrEnum):
    KEEP = "KEEP"
    REUSE = "REUSE"
    COMPRESS = "COMPRESS"
    QUANTIZE = "QUANTIZE"
    EVICT = "EVICT"
    RECOMPUTE = "RECOMPUTE"


def _require_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise InnovationContractError(f"{field}_must_be_sha256")


@dataclass(frozen=True)
class EvidenceWindowKey:
    """Non-negotiable reuse boundary for visual tokens or native KV blocks."""

    session_id: str
    visit_id: str
    source_video_hash: str
    start_pts_ns: int
    end_pts_ns: int
    model_version: str

    def __post_init__(self) -> None:
        if not self.session_id or not self.visit_id or not self.model_version:
            raise InnovationContractError("cache_identity_missing")
        _require_sha256(self.source_video_hash, "source_video_hash")
        if self.start_pts_ns < 0 or self.end_pts_ns <= self.start_pts_ns:
            raise InnovationContractError("cache_pts_invalid")

    def same_boundary_as(self, other: "EvidenceWindowKey") -> bool:
        return (
            self.session_id == other.session_id
            and self.visit_id == other.visit_id
            and self.source_video_hash == other.source_video_hash
            and self.model_version == other.model_version
        )


@dataclass(frozen=True)
class CacheQuality:
    ui_interference: float
    ocr_asr_support: float
    content_change: float

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if not 0.0 <= value <= 1.0:
                raise InnovationContractError(f"{name}_outside_unit_interval")


@dataclass(frozen=True)
class RouterDecision:
    """Model output after decoding; not a hand-written routing rule."""

    expert_weights: tuple[float, ...]
    cache_action: CacheAction
    call_full_vlm: bool
    fuse_conflicts: bool
    reject_answer: bool
    confidence: float
    uncertainty_reason: str

    def __post_init__(self) -> None:
        if len(self.expert_weights) != 5 or any(weight < 0 for weight in self.expert_weights):
            raise InnovationContractError("router_expert_weights_invalid")
        if not 0.0 <= self.confidence <= 1.0:
            raise InnovationContractError("router_confidence_invalid")
        if self.reject_answer and not self.uncertainty_reason:
            raise InnovationContractError("rejection_requires_reason")
