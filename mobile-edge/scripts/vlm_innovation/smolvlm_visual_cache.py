"""Real SmolVLM image-hidden-state caching through the supported model API.

SmolVLM's ``forward`` accepts ``image_hidden_states`` and rejects simultaneous
``pixel_values``.  This adapter uses that documented boundary: it caches the
vision encoder output unchanged, then supplies it back to a later generation.
It does not edit KV values and it cannot be used without a verified cache key.
"""

from __future__ import annotations

import io
from typing import Any

from .cache import EvidenceAwareVisualCache
from .contracts import CacheQuality, EvidenceWindowKey, InnovationContractError


class SmolVlmVisualTokenAdapter:
    def __init__(self, model: Any, cache: EvidenceAwareVisualCache) -> None:
        self.model = model
        self.cache = cache

    @staticmethod
    def _torch() -> Any:
        try:
            import torch
        except ImportError as error:
            raise RuntimeError("smolvlm_visual_cache_requires_torch") from error
        return torch

    def encode_and_keep(
        self,
        *,
        key: EvidenceWindowKey,
        quality: CacheQuality,
        pixel_values: Any,
        pixel_attention_mask: Any | None,
    ) -> str:
        """Run the actual vision encoder once and persist its unmodified output."""

        torch = self._torch()
        core = getattr(self.model, "model", None)
        encoder = getattr(core, "get_image_features", None)
        if encoder is None:
            raise InnovationContractError("smolvlm_image_feature_api_unavailable")
        with torch.inference_mode():
            hidden = encoder(pixel_values, pixel_attention_mask).detach().cpu()
        stream = io.BytesIO()
        torch.save({"image_hidden_states": hidden, "shape": list(hidden.shape), "dtype": str(hidden.dtype)}, stream)
        block = self.cache.keep(
            key,
            quality,
            stream.getvalue(),
            token_count=int(hidden.numel()),
            encoding="torch.save:SmolVLM.image_hidden_states",
        )
        return block.block_id

    def try_reuse(
        self,
        *,
        block_id: str,
        target: EvidenceWindowKey,
        target_quality: CacheQuality,
        max_gap_ns: int,
    ) -> Any | None:
        """Load a prior visual encoding only after EvidenceAwareVisualCache approves it."""

        payload = self.cache.reuse(block_id, target, target_quality=target_quality, max_gap_ns=max_gap_ns)
        if payload is None:
            return None
        torch = self._torch()
        decoded = torch.load(io.BytesIO(payload), map_location="cpu", weights_only=True)
        hidden = decoded.get("image_hidden_states") if isinstance(decoded, dict) else None
        if hidden is None:
            raise InnovationContractError("cached_visual_payload_invalid")
        return hidden

    @staticmethod
    def replace_pixels_with_cached_hidden(inputs: dict[str, Any], image_hidden_states: Any) -> dict[str, Any]:
        """Prepare supported SmolVLM generation input without running vision encoding again."""

        if "input_ids" not in inputs:
            raise InnovationContractError("smolvlm_input_ids_required_for_cached_visual_generation")
        result = dict(inputs)
        result.pop("pixel_values", None)
        result.pop("pixel_attention_mask", None)
        result["image_hidden_states"] = image_hidden_states
        return result
