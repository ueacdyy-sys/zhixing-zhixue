"""A real trainable temporal Router, kept optional until the CUDA runtime is used."""

from __future__ import annotations

from typing import Any


def build_temporal_expert_router(*, feature_dim: int, hidden_dim: int = 96) -> Any:
    """Build a PyTorch module only in the full-video runtime.

    The output heads cover five expert weights, six cache actions, complete-VLM
    execution, conflict fusion and reject/answer state.  No fixed policy is
    embedded here; training learns the decision surface from labelled windows.
    """

    try:
        import torch
        from torch import nn
    except ImportError as error:
        raise RuntimeError("temporal_router_requires_fullvideo_runtime_with_torch") from error
    if feature_dim < 1 or hidden_dim < 8:
        raise ValueError("router_dimensions_invalid")

    class TemporalExpertRouter(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.input_norm = nn.LayerNorm(feature_dim)
            self.history = nn.GRU(feature_dim, hidden_dim, batch_first=True)
            self.current = nn.Sequential(nn.Linear(feature_dim, hidden_dim), nn.GELU(), nn.Dropout(0.10))
            self.shared = nn.Sequential(nn.Linear(hidden_dim * 2, hidden_dim), nn.GELU(), nn.Dropout(0.10))
            self.expert_logits = nn.Linear(hidden_dim, 5)
            self.cache_logits = nn.Linear(hidden_dim, 6)
            self.execution_logits = nn.Linear(hidden_dim, 3)  # full VLM, conflict fusion, reject
            self.confidence = nn.Sequential(nn.Linear(hidden_dim, 1), nn.Sigmoid())

        def forward(self, current_features: Any, history_features: Any) -> dict[str, Any]:
            current = self.input_norm(current_features)
            history, _ = self.history(history_features)
            fused = self.shared(torch.cat((self.current(current), history[:, -1, :]), dim=-1))
            return {
                "expert_weights": torch.softmax(self.expert_logits(fused), dim=-1),
                "cache_logits": self.cache_logits(fused),
                "execution_logits": self.execution_logits(fused),
                "confidence": self.confidence(fused).squeeze(-1),
            }

    return TemporalExpertRouter()


def router_loss(output: Any, targets: dict[str, Any], *, cache_weight: float = 1.0, execution_weight: float = 1.0) -> Any:
    """Supervised loss; callers must pass labels, never fabricated policy targets."""

    import torch.nn.functional as functional

    expert = functional.kl_div(output["expert_weights"].log(), targets["expert_weights"], reduction="batchmean")
    cache = functional.cross_entropy(output["cache_logits"], targets["cache_action"])
    execution = functional.binary_cross_entropy_with_logits(output["execution_logits"], targets["execution"])
    confidence = functional.mse_loss(output["confidence"], targets["confidence"])
    return expert + cache_weight * cache + execution_weight * execution + confidence
