"""Durable evidence-bound cache for visual encodings or native model KV blocks."""

from __future__ import annotations

import hashlib
import json
import os
import time
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .contracts import CacheAction, CacheQuality, EvidenceWindowKey, InnovationContractError


@dataclass(frozen=True)
class CachedBlock:
    block_id: str
    key: EvidenceWindowKey
    quality: CacheQuality
    token_count: int
    storage_bytes: int
    encoding: str
    created_ns: int
    parent_block_id: str | None = None


class EvidenceAwareVisualCache:
    """A metadata-first cache that refuses cross-video or cross-visit reuse.

    Payloads are opaque bytes: callers may store visual encodings or framework
    supported KV serialisations.  Quantisation is accepted only via a real
    caller-provided encoder, never by relabelling arbitrary bytes as quantized.
    """

    def __init__(self, root: Path, *, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise InnovationContractError("cache_budget_must_be_positive")
        self.root = root.resolve()
        self.blocks = self.root / "blocks"
        self.events = self.root / "cache_events.jsonl"
        self.max_bytes = max_bytes
        self.blocks.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _id(key: EvidenceWindowKey) -> str:
        raw = "|".join((key.session_id, key.visit_id, key.source_video_hash, str(key.start_pts_ns), str(key.end_pts_ns), key.model_version))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def _meta_path(self, block_id: str) -> Path:
        return self.blocks / f"{block_id}.json"

    def _payload_path(self, block_id: str) -> Path:
        return self.blocks / f"{block_id}.bin"

    def _emit(self, action: CacheAction, block_id: str | None, reason: str, **extra: object) -> None:
        document = {"event_ns": time.monotonic_ns(), "action": action.value, "block_id": block_id, "reason": reason, **extra}
        with self.events.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n")

    def _load(self, block_id: str) -> CachedBlock | None:
        path = self._meta_path(block_id)
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        key = EvidenceWindowKey(**raw.pop("key"))
        quality = CacheQuality(**raw.pop("quality"))
        return CachedBlock(key=key, quality=quality, **raw)

    def total_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.blocks.glob("*.bin"))

    def keep(self, key: EvidenceWindowKey, quality: CacheQuality, payload: bytes, *, token_count: int, encoding: str) -> CachedBlock:
        if not payload or token_count <= 0 or not encoding:
            raise InnovationContractError("cache_payload_or_metadata_invalid")
        block_id = self._id(key)
        payload_path = self._payload_path(block_id)
        temporary = payload_path.with_suffix(".partial")
        temporary.write_bytes(payload)
        os.replace(temporary, payload_path)
        block = CachedBlock(block_id, key, quality, token_count, len(payload), encoding, time.monotonic_ns())
        self._meta_path(block_id).write_text(
            json.dumps({**asdict(block), "key": asdict(key), "quality": asdict(quality)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._emit(CacheAction.KEEP, block_id, "router_keep", total_bytes=self.total_bytes())
        self.enforce_budget()
        return block

    def reuse(self, block_id: str, target: EvidenceWindowKey, *, target_quality: CacheQuality, max_gap_ns: int) -> bytes | None:
        block = self._load(block_id)
        if block is None or not self._payload_path(block_id).is_file():
            self._emit(CacheAction.RECOMPUTE, block_id, "cache_block_missing")
            return None
        if not block.key.same_boundary_as(target):
            self._emit(CacheAction.RECOMPUTE, block_id, "cross_boundary_reuse_refused")
            return None
        if target.start_pts_ns - block.key.end_pts_ns > max_gap_ns or target_quality.content_change > 0.35:
            self._emit(CacheAction.RECOMPUTE, block_id, "temporal_or_content_continuity_failed")
            return None
        if target_quality.ui_interference > 0.70 or target_quality.ocr_asr_support < 0.25:
            self._emit(CacheAction.RECOMPUTE, block_id, "target_evidence_quality_too_low")
            return None
        self._emit(CacheAction.REUSE, block_id, "same_visit_same_video_continuity_verified")
        return self._payload_path(block_id).read_bytes()

    def compress(self, block_id: str) -> CachedBlock:
        block = self._load(block_id)
        if block is None:
            raise InnovationContractError("compress_unknown_block")
        original = self._payload_path(block_id).read_bytes()
        compressed = zlib.compress(original, level=9)
        if len(compressed) >= len(original):
            self._emit(CacheAction.COMPRESS, block_id, "compression_not_beneficial")
            return block
        return self.keep(block.key, block.quality, compressed, token_count=block.token_count, encoding=f"zlib:{block.encoding}")

    def quantize(self, block_id: str, quantizer: Callable[[bytes], bytes], *, encoding: str) -> CachedBlock:
        if not encoding:
            raise InnovationContractError("real_quantizer_encoding_required")
        block = self._load(block_id)
        if block is None:
            raise InnovationContractError("quantize_unknown_block")
        converted = quantizer(self._payload_path(block_id).read_bytes())
        if not converted:
            raise InnovationContractError("quantizer_returned_empty_payload")
        result = self.keep(block.key, block.quality, converted, token_count=block.token_count, encoding=encoding)
        self._emit(CacheAction.QUANTIZE, result.block_id, "caller_supplied_real_quantizer")
        return result

    def evict(self, block_id: str, *, reason: str) -> bool:
        existed = False
        for path in (self._meta_path(block_id), self._payload_path(block_id)):
            if path.exists():
                path.unlink()
                existed = True
        self._emit(CacheAction.EVICT, block_id, reason)
        return existed

    def enforce_budget(self) -> None:
        candidates = [block for path in self.blocks.glob("*.json") if (block := self._load(path.stem)) is not None]
        candidates.sort(key=lambda block: (block.quality.ui_interference - block.quality.ocr_asr_support, block.created_ns), reverse=True)
        while self.total_bytes() > self.max_bytes and candidates:
            victim = candidates.pop(0)
            self.evict(victim.block_id, reason="memory_budget_exceeded")
