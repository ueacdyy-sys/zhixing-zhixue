"""证据卡片构建函数。"""

from __future__ import annotations

from typing import Any


def build_evidence_card(
    window_id: str,
    semantic_evidence: dict[str, Any],
    interpretation: str | None,
    counterevidence: list[str],
    uncertainty: list[str],
    confidence: str,
    action: str,
) -> dict[str, Any]:
    """构建证据卡片。
    
    Args:
        window_id: 时间窗口标识
        semantic_evidence: 语义证据
        interpretation: 解释
        counterevidence: 反证
        uncertainty: 不确定性
        confidence: 置信度
        action: 后续动作
        
    Returns:
        证据卡片字典
    """
    # Extract facts from semantic_evidence
    facts = [fact["statement"] for fact in semantic_evidence.get("facts", [])]
    
    return {
        "card_id": f"card-{window_id}",
        "window_id": window_id,
        "facts": facts,
        "interpretation": interpretation,
        "counterevidence": counterevidence,
        "uncertainty": uncertainty,
        "confidence": confidence,
        "action": action,
        "review_status": "auto",
        "downgrade_reason": None,
    }
