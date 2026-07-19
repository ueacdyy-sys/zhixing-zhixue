#!/usr/bin/env python3
"""Build learning evidence cards and lightweight interest microtasks.

    This module is the automatic product gate, not a manual labeling workflow. It
    emits cards when full-video VLM evidence and high-quality aligned ASR evidence
    are both bound to the same canonical media. Human review is recorded only as
    offline acceptance evidence for a competition/demo sample.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


ALLOWED_MICROTASK_TYPES = {"explain", "extend", "save", "watch_later", "review"}
FORBIDDEN_MICROTASK_PATTERNS = [
    "出题",
    "题目",
    "选择题",
    "练习题",
    "考试",
    "测验",
    "quiz",
    "question",
    "exercise recommendation",
    "recommend exercise",
]


class EvidenceBuildError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvidenceBuildError("json_object_required", f"expected object JSON: {path}")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _time_range_valid(item: dict[str, Any], duration_s: float | None) -> bool:
    start_s = item.get("start_s")
    end_s = item.get("end_s")
    if (
        not _is_number(start_s)
        or not _is_number(end_s)
        or float(start_s) < 0
        or float(end_s) <= float(start_s)
    ):
        return False
    return duration_s is None or float(end_s) <= duration_s + 0.25


def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return float(left["start_s"]) < float(right["end_s"]) and float(right["start_s"]) < float(left["end_s"])


def _assert_bound_report(understanding: dict[str, Any], asr_report: dict[str, Any]) -> tuple[str, str, float | None]:
    if understanding.get("input_mode") != "canonical_full_video":
        raise EvidenceBuildError("full_video_input_required", "understanding report must come from canonical_full_video input")
    if understanding.get("status") != "production_ready" or understanding.get("production_ready") is not True:
        raise EvidenceBuildError("full_video_vlm_not_ready", "full-video VLM result is not production ready")
    if asr_report.get("quality_status") != "pass":
        raise EvidenceBuildError("asr_quality_not_pass", "ASR quality must pass before building evidence cards")
    capture_id = understanding.get("capture_id")
    media_sha = understanding.get("source_media_sha256") or understanding.get("media_sha256")
    if not isinstance(capture_id, str) or not capture_id.strip():
        raise EvidenceBuildError("capture_id_missing", "understanding capture_id missing")
    if not isinstance(media_sha, str) or len(media_sha) != 64:
        raise EvidenceBuildError("media_sha256_missing", "understanding media SHA missing")
    if asr_report.get("capture_id") != capture_id or asr_report.get("source_media_sha256") != media_sha:
        raise EvidenceBuildError("asr_understanding_binding_mismatch", "ASR and VLM reports are not bound to the same capture")
    media = understanding.get("media") if isinstance(understanding.get("media"), dict) else {}
    duration = media.get("duration_s")
    duration_s = float(duration) if _is_number(duration) else None
    return capture_id, media_sha, duration_s


def _asr_snippets_for_event(event: dict[str, Any], asr_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snippets = []
    for result in asr_results:
        if not isinstance(result, dict) or result.get("status") != "success":
            continue
        if not _time_range_valid(result, None) or not _overlaps(event, result):
            continue
        text = str(result.get("text") or "").strip()
        if text:
            snippets.append(
                {
                    "segment_index": result.get("segment_index"),
                    "start_s": float(result["start_s"]),
                    "end_s": float(result["end_s"]),
                    "text": text,
                    "evidence_refs": result.get("evidence_refs", []),
                }
            )
    return snippets


def _clean_terms(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out


def _microtask_for_card(card: dict[str, Any]) -> dict[str, Any]:
    concepts = card.get("concepts") if isinstance(card.get("concepts"), list) else []
    anchor = concepts[0] if concepts else card["video_event_summary"][:24]
    action = (
        f"用自己的话解释“{anchor}”为什么会出现在这个片段里，"
        "并把它和最近一次课内/项目学习中的一个概念连接起来。"
    )
    task = {
        "microtask_id": f"task_{card['card_id'].split('_', 1)[1]}",
        "type": "explain",
        "interest_entry": anchor,
        "lightweight_action": action,
        "evidence_card_id": card["card_id"],
        "production_allowed": True,
        "truth_label": "推断",
        "forbidden_task_policy": "no_quiz_no_direct_exercise_recommendation",
    }
    validate_microtask(task)
    return task


def validate_microtask(task: dict[str, Any]) -> None:
    task_type = task.get("type")
    if task_type not in ALLOWED_MICROTASK_TYPES:
        raise EvidenceBuildError("microtask_type_forbidden", f"forbidden microtask type: {task_type}")
    # Policy metadata may legitimately contain words such as "exercise" while
    # documenting what is forbidden.  Only student-visible content is subject
    # to the language gate.
    haystack = " ".join(
        str(task.get(field, ""))
        for field in ("type", "interest_entry", "lightweight_action")
    ).lower()
    if any(pattern.lower() in haystack for pattern in FORBIDDEN_MICROTASK_PATTERNS):
        raise EvidenceBuildError("question_like_microtask_forbidden", "microtask looks like a question/exercise recommendation")


def build_evidence(
    *,
    understanding: dict[str, Any],
    asr_report: dict[str, Any],
    human_verified: bool = False,
) -> dict[str, Any]:
    capture_id, media_sha, duration_s = _assert_bound_report(understanding, asr_report)
    events = understanding.get("results")
    if not isinstance(events, list) or not events:
        raise EvidenceBuildError("vlm_events_missing", "understanding report has no VLM events")
    asr_results = asr_report.get("results")
    if not isinstance(asr_results, list) or not asr_results:
        raise EvidenceBuildError("asr_results_missing", "ASR aligned results missing")

    cards = []
    microtasks = []
    for event in events:
        if not isinstance(event, dict) or event.get("status") != "success":
            continue
        if not _time_range_valid(event, duration_s):
            raise EvidenceBuildError("vlm_event_time_invalid", "VLM event time range is invalid")
        summary = str(event.get("summary") or event.get("text") or "").strip()
        if not summary:
            raise EvidenceBuildError("vlm_event_summary_missing", "VLM event summary missing")
        event_refs = event.get("evidence_refs")
        if not isinstance(event_refs, list) or not event_refs:
            raise EvidenceBuildError("vlm_event_evidence_refs_missing", "VLM event evidence refs missing")
        snippets = _asr_snippets_for_event(event, asr_results)
        if not snippets:
            raise EvidenceBuildError("asr_overlap_missing", "each evidence card requires overlapping ASR text")
        card_index = len(cards) + 1
        card = {
            "card_id": f"card_{card_index:04d}",
            "capture_id": capture_id,
            "source_media_sha256": media_sha,
            "input_media_path": understanding.get("input_media_path"),
            "start_s": float(event["start_s"]),
            "end_s": float(event["end_s"]),
            "video_event_summary": summary,
            "concepts": _clean_terms(event.get("concepts")),
            "expressions": _clean_terms(event.get("expressions")),
            "uncertainty": event.get("uncertainty", "unknown"),
            "vlm_evidence_refs": [str(ref) for ref in event_refs],
            "asr_evidence": snippets,
            "fact_status": "已实测",
            "interpretation_status": "推断",
            "machine_evidence_ready": True,
            "automatic_loop_allowed": True,
            "human_review_status": "passed" if human_verified else "not_reviewed",
            "competition_acceptance_status": (
                "accepted" if human_verified else "needs_offline_sample_review"
            ),
            "evidence_gaps": [] if human_verified else ["offline_sample_review_not_recorded"],
        }
        cards.append(card)
        microtasks.append(_microtask_for_card(card))
    if not cards:
        raise EvidenceBuildError("no_usable_events", "no usable VLM+ASR evidence event")
    for task in microtasks:
        task["machine_evidence_ready"] = True
        task["automatic_loop_allowed"] = True
        task["human_review_status"] = "passed" if human_verified else "not_reviewed"
        task["competition_acceptance_status"] = (
            "accepted" if human_verified else "needs_offline_sample_review"
        )
        if not human_verified:
            task["evidence_gaps"] = ["offline_sample_review_not_recorded"]
    return {
        "schema_version": "learning_evidence_bundle.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "capture_id": capture_id,
        "source_media_sha256": media_sha,
        "machine_evidence_ready": True,
        "automatic_loop_allowed": True,
        "human_review_status": "passed" if human_verified else "not_reviewed",
        "competition_acceptance_status": (
            "accepted" if human_verified else "needs_offline_sample_review"
        ),
        "truth_label": "已实测",
        "interpretation_label": "推断",
        "cards": cards,
        "microtasks": microtasks,
        "policy": {
            "requires_full_video_vlm_pass": True,
            "requires_high_quality_asr_pass": True,
            "ocr_is_auxiliary_only": True,
            "human_review_is_not_runtime_gate": True,
            "forbidden_microtask_patterns": FORBIDDEN_MICROTASK_PATTERNS,
        },
    }


def _blocked_bundle(code: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": "learning_evidence_bundle.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "machine_evidence_ready": False,
        "automatic_loop_allowed": False,
        "human_review_status": "not_applicable",
        "competition_acceptance_status": "blocked_before_review",
        "truth_label": "未满足",
        "errors": [{"code": code, "message": message}],
        "cards": [],
        "microtasks": [],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build evidence cards and interest microtasks.")
    parser.add_argument("--understanding-report", required=True)
    parser.add_argument("--asr-report", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--human-verified",
        action="store_true",
        help="Set only after manual video/ASR/card review has actually passed.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    try:
        bundle = build_evidence(
            understanding=_read_json(Path(args.understanding_report)),
            asr_report=_read_json(Path(args.asr_report)),
            human_verified=args.human_verified,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, EvidenceBuildError) as exc:
        code = exc.code if isinstance(exc, EvidenceBuildError) else "input_error"
        bundle = _blocked_bundle(code, str(exc))
    out_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(out_dir / "learning_evidence_bundle.json", bundle)
    _atomic_write_json(out_dir / "evidence_cards.json", bundle["cards"])
    _atomic_write_json(out_dir / "microtasks.json", bundle["microtasks"])
    print(json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if bundle.get("demo_usable") else 4


if __name__ == "__main__":
    raise SystemExit(main())
