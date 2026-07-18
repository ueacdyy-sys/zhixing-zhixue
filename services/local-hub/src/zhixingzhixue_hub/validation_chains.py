"""两条可复现的领域端到端验证链。"""

from __future__ import annotations

from typing import Any

from zhixingzhixue_hub.analysis.fast_path import build_fast_path_candidate
from zhixingzhixue_hub.evidence.card_builder import build_evidence_card
from zhixingzhixue_hub.export.evidence_package import build_evidence_export
from zhixingzhixue_hub.pc.task_workbench import (
    add_pc_task_phase,
    create_pc_task_session,
    record_pc_learning_behavior,
)
from zhixingzhixue_hub.phone.interest_session import start_interest_session
from zhixingzhixue_hub.phone.receipt import write_phone_receipt
from zhixingzhixue_hub.quality.modality_gate import assess_modality_quality, create_downgrade_log
from zhixingzhixue_hub.timeline.aligner import build_pc_timeline


def run_phone_validation_chain() -> dict[str, Any]:
    """Verify full phone evidence admission, card construction, and voluntary receipt."""
    media = {
        "capture_id": "cap-validation-phone-001",
        "session_id": "ses-validation-phone-001",
        "media_uri": "local://captures/cap-validation-phone-001/segment.mkv",
        "audio_uri": "local://captures/cap-validation-phone-001/audio.m4a",
        "start_ts": "2026-07-17T22:00:00+08:00",
        "end_ts": "2026-07-17T22:01:00+08:00",
        "source": "phone",
    }
    session = start_interest_session(media)
    card = build_evidence_card(
        window_id="window-validation-phone-001",
        semantic_evidence={
            "analysis_status": "SEMANTIC_ANALYSIS_COMPLETE",
            "facts": [
                {
                    "statement": "完整公开媒体片段已留存，可按时间回放。",
                    "evidence_uri": media["media_uri"],
                }
            ],
            "quality_flags": [],
        },
        interpretation=None,
        counterevidence=["尚未观察到跨场景重复行为。"],
        uncertainty=["语义结果只覆盖本片段。"],
        confidence="low",
        action="由学生自行查看并决定是否保存。",
    )
    receipt = write_phone_receipt(
        {
            "evidence_card_id": card["card_id"],
            "action": "save",
            "recorded_at": "2026-07-17T22:02:00+08:00",
        }
    )
    return {
        "chain": "phone_public_media",
        "session_status": session["status"],
        "card": card,
        "receipt": receipt,
        "evidence_refs": [media["media_uri"]],
    }


def run_pc_validation_chain() -> dict[str, Any]:
    """Verify PC-native collection, conservative candidate, quality log, and export."""
    task = create_pc_task_session(
        {
            "session_id": "ses-validation-pc-001",
            "task_id": "task-validation-pc-001",
            "task_type": "video_course",
            "goal": "完成一段算法课程并记录学习事实。",
            "knowledge_tags": ["算法"],
            "started_at": "2026-07-17T22:10:00+08:00",
            "source": "pc",
        }
    )
    phase = add_pc_task_phase(
        task,
        {
            "phase_id": "phase-validation-pc-001",
            "task_id": task["task_id"],
            "phase_type": "watch",
            "started_at": "2026-07-17T22:10:00+08:00",
            "ended_at": "2026-07-17T22:20:00+08:00",
            "source": "pc",
        },
    )
    behavior = record_pc_learning_behavior(
        task,
        {
            "event_id": "evt-validation-pc-001",
            "session_id": task["session_id"],
            "task_id": task["task_id"],
            "phase_id": phase["phase_id"],
            "source": "pc",
            "modality": "behavior",
            "event_type": "edit",
            "start_ts": "2026-07-17T22:12:00+08:00",
            "end_ts": "2026-07-17T22:13:00+08:00",
            "confidence": 0.9,
            "quality_flags": [],
            "evidence_uri": "local://pc/ses-validation-pc-001/events/evt-validation-pc-001.json",
            "privacy_level": "local_only",
            "review_status": "auto",
        },
    )
    timeline = build_pc_timeline(task, [behavior], phases=[phase])
    candidate = build_fast_path_candidate(timeline)
    quality_gate = assess_modality_quality(
        {
            "session_id": task["session_id"],
            "capture_id": "cap-validation-wearable-001",
            "source": "wearable",
            "modality": "eeg_trend",
            "evidence_uri": "local://captures/cap-validation-wearable-001/raw.bin",
            "connection_status": "connected",
            "quality": "degraded",
            "alignment_residual_ms": 200,
            "quality_flags": ["artifact"],
        }
    )
    quality_log = create_downgrade_log(quality_gate, recorded_at="2026-07-17T22:14:00+08:00")
    card = build_evidence_card(
        window_id="window-validation-pc-001",
        semantic_evidence={
            "analysis_status": "SEMANTIC_ANALYSIS_COMPLETE",
            "facts": [
                {
                    "statement": "PC 学习行为事件已留存，可按阶段和时间回放。",
                    "evidence_uri": behavior["evidence_uri"],
                }
            ],
            "quality_flags": quality_gate["canonical_flags"],
        },
        interpretation="该事实事件归属于当前 PC 学习阶段。",
        counterevidence=["当前仅有一条事件证据。"],
        uncertainty=["可穿戴辅助信号质量不足。"],
        confidence="medium",
        action="由学生查看证据边界后自行决定。",
    )
    card_envelope = {
        "session_id": task["session_id"],
        "origin_source": "pc",
        "evidence_refs": [behavior["evidence_uri"]],
        "card": card,
    }
    export = build_evidence_export(
        session_id=task["session_id"],
        events=[behavior],
        card_envelopes=[card_envelope],
        quality_logs=[quality_log],
        created_at="2026-07-17T22:15:00+08:00",
    )
    return {
        "chain": "pc_independent_learning",
        "task": task,
        "phase": phase,
        "timeline": timeline,
        "candidate": candidate,
        "quality_log": quality_log,
        "card": card,
        "export": export,
    }
