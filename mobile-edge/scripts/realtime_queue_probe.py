from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "queue_probe_report.v2"
TOOL_NAME = "realtime_queue_probe"
TOOL_VERSION = "2.0.0"
RULE_VERSION = "queue-semantic-evidence.v2"
CAPTURE_ID_PATTERN = re.compile(r"^cap_[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass
class QueueTask:
    task_id: str
    capture_id: str
    probe_run_id: str
    segment_index: int | None
    stage: str
    status: str
    created_at_timeline_s: float
    deadline_at_timeline_s: float | None
    estimated_cost_ms: float | None
    evidence: list[str]
    reason: str


@dataclass
class GateDecision:
    capture_id: str
    probe_run_id: str
    segment_index: int
    timeline_range_s: str
    status: str
    allowed_to_generate_microtask: bool
    reasons: list[str]
    available_evidence: list[str]
    blocked_evidence: list[str]


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if not math.isfinite(out):
            return None
        return out
    except (TypeError, ValueError):
        return None


def summarize(values: list[float | None]) -> dict[str, float | None]:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if not clean:
        return {"min": None, "p50": None, "p90": None, "p95": None, "max": None, "mean": None}
    clean.sort()
    return {
        "min": clean[0],
        "p50": float(statistics.median(clean)),
        "p90": float(clean[min(len(clean) - 1, int(math.ceil(len(clean) * 0.90)) - 1)]),
        "p95": float(clean[min(len(clean) - 1, int(math.ceil(len(clean) * 0.95)) - 1)]),
        "max": clean[-1],
        "mean": float(statistics.mean(clean)),
    }


def stream_has_audio(report: dict[str, Any]) -> bool:
    streams = (((report.get("raw_recording") or {}).get("ffprobe") or {}).get("streams") or [])
    return any(stream.get("codec_type") == "audio" for stream in streams)


def evidence_files_for_segment(segment: dict[str, Any]) -> list[str]:
    files = segment.get("evidence_files") or []
    return [str(item) for item in files if item]


class TimelineValidationError(ValueError):
    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__("timeline segment validation failed")
        self.errors = errors


def validate_timeline_segments(report: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    capture_id = report.get("capture_id")
    if not isinstance(capture_id, str) or not CAPTURE_ID_PATTERN.fullmatch(capture_id):
        errors.append(
            {
                "code": "capture_id_invalid",
                "message": "capture_id must be a non-empty cap_* string.",
            }
        )

    raw_recording = report.get("raw_recording")
    if not isinstance(raw_recording, dict):
        errors.append(
            {
                "code": "raw_recording_object_required",
                "message": "raw_recording must be an object.",
            }
        )
    else:
        if raw_recording.get("capture_id") != capture_id:
            errors.append(
                {
                    "code": "raw_capture_id_mismatch",
                    "message": "raw_recording.capture_id must match capture_id.",
                }
            )
        ffprobe = raw_recording.get("ffprobe")
        if not isinstance(ffprobe, dict):
            errors.append(
                {
                    "code": "ffprobe_object_required",
                    "message": "raw_recording.ffprobe must be an object.",
                }
            )
        else:
            streams = ffprobe.get("streams")
            if not isinstance(streams, list):
                errors.append(
                    {
                        "code": "ffprobe_streams_list_required",
                        "message": "raw_recording.ffprobe.streams must be a list.",
                    }
                )
            else:
                for position, stream in enumerate(streams, start=1):
                    if not isinstance(stream, dict):
                        errors.append(
                            {
                                "code": "ffprobe_stream_object_required",
                                "position": position,
                                "message": "each ffprobe stream must be an object.",
                            }
                        )

    samples = report.get("samples")
    if not isinstance(samples, list):
        errors.append(
            {
                "code": "samples_list_required",
                "message": "samples must be a list.",
            }
        )
    else:
        sample_indices: list[int] = []
        for position, sample in enumerate(samples, start=1):
            if not isinstance(sample, dict):
                errors.append(
                    {
                        "code": "sample_object_required",
                        "position": position,
                        "message": "each sample must be an object.",
                    }
                )
                continue
            index = sample.get("sample_index")
            if not isinstance(index, int) or isinstance(index, bool) or index <= 0:
                errors.append(
                    {
                        "code": "sample_index_invalid",
                        "position": position,
                        "message": "sample_index must be a positive integer.",
                    }
                )
            else:
                sample_indices.append(index)
        if len(sample_indices) != len(set(sample_indices)):
            errors.append(
                {
                    "code": "sample_indices_not_unique",
                    "message": "sample_index values must be unique.",
                }
            )

    segments = report.get("segments")
    duration = safe_float(report.get("timeline_duration_s"))
    if duration is None or duration <= 0:
        errors.append(
            {
                "code": "timeline_duration_invalid",
                "message": "timeline_duration_s must be a positive finite number.",
            }
        )
    if not isinstance(segments, list) or not segments:
        errors.append(
            {
                "code": "segments_required",
                "message": "segments must be a non-empty list.",
            }
        )
        return errors

    indices: list[int] = []
    valid_bounds: list[tuple[int, float, float]] = []
    for position, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            errors.append(
                {
                    "code": "segment_object_required",
                    "position": position,
                    "message": "each segment must be an object.",
                }
            )
            continue

        index = segment.get("segment_index")
        if not isinstance(index, int) or isinstance(index, bool):
            errors.append(
                {
                    "code": "segment_index_invalid",
                    "position": position,
                    "message": "segment_index must be an integer.",
                }
            )
        else:
            indices.append(index)

        start = safe_float(segment.get("start_s"))
        end = safe_float(segment.get("end_s"))
        if start is None or end is None or start < 0 or end <= start:
            errors.append(
                {
                    "code": "segment_time_range_invalid",
                    "position": position,
                    "segment_index": index,
                    "message": "segment start/end must satisfy 0 <= start_s < end_s.",
                }
            )
        else:
            valid_bounds.append((position, start, end))
            if duration is not None and duration > 0 and end > duration:
                errors.append(
                    {
                        "code": "segment_end_exceeds_timeline_duration",
                        "position": position,
                        "segment_index": index,
                        "message": "segment end_s exceeds timeline_duration_s.",
                    }
                )

        evidence_files = segment.get("evidence_files")
        if not isinstance(evidence_files, list) or not any(
            isinstance(item, str) and item.strip() for item in evidence_files
        ):
            errors.append(
                {
                    "code": "segment_evidence_files_required",
                    "position": position,
                    "segment_index": index,
                    "message": "segment evidence_files must contain a non-empty path.",
                }
            )

    if len(indices) != len(set(indices)):
        errors.append(
            {
                "code": "segment_indices_not_unique",
                "message": "segment_index values must be unique.",
            }
        )
    if len(indices) == len(segments) and indices != list(range(1, len(segments) + 1)):
        errors.append(
            {
                "code": "segment_indices_not_contiguous_1_based",
                "message": "segment_index values must follow list order as 1..N.",
            }
        )

    previous_end: float | None = None
    for position, start, end in valid_bounds:
        if previous_end is not None and start < previous_end:
            errors.append(
                {
                    "code": "segments_overlap_or_out_of_order",
                    "position": position,
                    "message": "segments must be ordered and must not overlap.",
                }
            )
        previous_end = end
    return errors


def build_tasks(
    report: dict[str, Any],
    ocr_ms_per_frame: float,
    visual_deadline_ms: float,
    segment_deadline_ms: float,
    microtask_deadline_s: float,
    vlm_available: bool,
    probe_run_id: str,
) -> tuple[list[QueueTask], list[GateDecision]]:
    validation_errors = validate_timeline_segments(report)
    if validation_errors:
        raise TimelineValidationError(validation_errors)

    tasks: list[QueueTask] = []
    gates: list[GateDecision] = []
    capture_id = str(report["capture_id"])
    has_audio = stream_has_audio(report)
    source_kind = report.get("source_kind")

    samples = report.get("samples") or []
    process_by_sample = {
        int(sample.get("sample_index")): safe_float(sample.get("process_wall_ms"))
        for sample in samples
        if sample.get("sample_index") is not None
    }
    for sample in samples:
        idx = int(sample.get("sample_index"))
        timeline_s = safe_float(sample.get("timeline_s")) or 0.0
        process_ms = process_by_sample.get(idx)
        status = "within_budget" if process_ms is not None and process_ms <= visual_deadline_ms else "over_budget"
        reason = (
            f"visual sample cost {process_ms:.3f}ms <= {visual_deadline_ms:.3f}ms"
            if status == "within_budget" and process_ms is not None
            else f"visual sample cost {process_ms}ms exceeds {visual_deadline_ms:.3f}ms or is missing"
        )
        tasks.append(
            QueueTask(
                task_id=f"{capture_id}:{probe_run_id}:visual_signal_fast_path:{idx:04d}",
                capture_id=capture_id,
                probe_run_id=probe_run_id,
                segment_index=None,
                stage="visual_signal_fast_path",
                status=status,
                created_at_timeline_s=timeline_s,
                deadline_at_timeline_s=timeline_s + visual_deadline_ms / 1000.0,
                estimated_cost_ms=process_ms,
                evidence=[str(sample.get("evidence_file"))] if sample.get("evidence_file") else [],
                reason=reason,
            )
        )

    for segment in report.get("segments") or []:
        seg_idx = int(segment.get("segment_index"))
        start_s = safe_float(segment.get("start_s")) or 0.0
        end_s = safe_float(segment.get("end_s")) or start_s
        files = evidence_files_for_segment(segment)
        shift_count = int(segment.get("shift_sample_count") or 0)
        max_change = safe_float(segment.get("max_full_change"))
        created = end_s
        tasks.append(
            QueueTask(
                task_id=f"{capture_id}:{probe_run_id}:segment_boundary:{seg_idx:04d}",
                capture_id=capture_id,
                probe_run_id=probe_run_id,
                segment_index=seg_idx,
                stage="segment_boundary",
                status="candidate" if shift_count > 0 else "low_motion_context",
                created_at_timeline_s=created,
                deadline_at_timeline_s=created + segment_deadline_ms / 1000.0,
                estimated_cost_ms=None,
                evidence=files[:3],
                reason=f"shift_sample_count={shift_count}, max_full_change={max_change}",
            )
        )

        semantic_available: list[str] = []
        semantic_blocked: list[str] = []

        if has_audio:
            semantic_available.append("audio_stream_present_for_asr")
            tasks.append(
                QueueTask(
                    task_id=f"{capture_id}:{probe_run_id}:asr_async:{seg_idx:04d}",
                    capture_id=capture_id,
                    probe_run_id=probe_run_id,
                    segment_index=seg_idx,
                    stage="asr_async",
                    status="queued",
                    created_at_timeline_s=created,
                    deadline_at_timeline_s=created + microtask_deadline_s,
                    estimated_cost_ms=None,
                    evidence=[],
                    reason="audio stream is present; ASR can be scheduled outside visual fast path.",
                )
            )
        else:
            semantic_blocked.append("audio_stream_absent")
            tasks.append(
                QueueTask(
                    task_id=f"{capture_id}:{probe_run_id}:asr_async:{seg_idx:04d}",
                    capture_id=capture_id,
                    probe_run_id=probe_run_id,
                    segment_index=seg_idx,
                    stage="asr_async",
                    status="blocked_no_audio",
                    created_at_timeline_s=created,
                    deadline_at_timeline_s=None,
                    estimated_cost_ms=None,
                    evidence=[],
                    reason="raw stream has no audio track; ASR cannot provide semantic timeline for this segment.",
                )
            )

        if vlm_available:
            semantic_available.append("vlm_available")
            tasks.append(
                QueueTask(
                    task_id=f"{capture_id}:{probe_run_id}:vlm_async:{seg_idx:04d}",
                    capture_id=capture_id,
                    probe_run_id=probe_run_id,
                    segment_index=seg_idx,
                    stage="vlm_async",
                    status="queued",
                    created_at_timeline_s=created,
                    deadline_at_timeline_s=created + microtask_deadline_s,
                    estimated_cost_ms=None,
                    evidence=files[:3],
                    reason="VLM endpoint/model marked available; schedule visual semantic summary asynchronously.",
                )
            )
        else:
            semantic_blocked.append("vlm_not_configured")
            tasks.append(
                QueueTask(
                    task_id=f"{capture_id}:{probe_run_id}:vlm_async:{seg_idx:04d}",
                    capture_id=capture_id,
                    probe_run_id=probe_run_id,
                    segment_index=seg_idx,
                    stage="vlm_async",
                    status="blocked_no_model",
                    created_at_timeline_s=created,
                    deadline_at_timeline_s=None,
                    estimated_cost_ms=None,
                    evidence=files[:3],
                    reason="no local or remote VLM endpoint is configured for this probe.",
                )
            )

        if files:
            estimated_ocr_ms = len(files) * ocr_ms_per_frame
            tasks.append(
                QueueTask(
                    task_id=f"{capture_id}:{probe_run_id}:ocr_auxiliary:{seg_idx:04d}",
                    capture_id=capture_id,
                    probe_run_id=probe_run_id,
                    segment_index=seg_idx,
                    stage="ocr_auxiliary",
                    status="queued_auxiliary",
                    created_at_timeline_s=created,
                    deadline_at_timeline_s=None,
                    estimated_cost_ms=estimated_ocr_ms,
                    evidence=files[:3],
                    reason=(
                        "OCR is scheduled only as auxiliary evidence. It is deliberately outside the fast path "
                        "because previous benchmark showed OCR is too slow for real-time core understanding."
                    ),
                )
            )
        else:
            semantic_blocked.append("no_evidence_frames")

        semantic_schedulable = bool(semantic_available)
        allowed = False
        reasons = []
        if semantic_schedulable:
            status = "pending_semantic_evidence"
            reasons.extend(
                [
                    "awaiting_async_result",
                    "ASR/VLM is schedulable, but capability or queue admission is not completed semantic evidence.",
                ]
            )
        else:
            status = "blocked_insufficient_semantic_evidence"
            reasons.append("no ASR/VLM semantic evidence source is available; do not generate interest task from visual signal alone.")
        if source_kind == "local_replay":
            reasons.append("this is local replay validation, not current live RTSP proof.")

        gates.append(
            GateDecision(
                capture_id=capture_id,
                probe_run_id=probe_run_id,
                segment_index=seg_idx,
                timeline_range_s=f"{start_s:.3f}-{end_s:.3f}",
                status=status,
                allowed_to_generate_microtask=allowed,
                reasons=reasons,
                available_evidence=semantic_available,
                blocked_evidence=semantic_blocked,
            )
        )

    task_ids = [task.task_id for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise TimelineValidationError(
            [
                {
                    "code": "task_ids_not_unique",
                    "message": "validated input produced duplicate task IDs.",
                }
            ]
        )
    return tasks, gates


def json_text(value: Any, *, indent: int | None = 2) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=indent,
        allow_nan=False,
    )


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def report_metadata(
    *,
    probe_run_id: str,
    generated_at: str,
    timeline_path: Path,
    timeline_sha256: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "probe_run_id": probe_run_id,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "rule_version": RULE_VERSION,
        "timeline_report": str(timeline_path),
        "input_timeline": {
            "path": str(timeline_path),
            "sha256": timeline_sha256,
        },
    }


def write_input_error(
    *,
    out_dir: Path,
    metadata: dict[str, Any],
    errors: list[dict[str, Any]],
    capture_id: Any = None,
) -> dict[str, Any]:
    report = {
        **metadata,
        "status": "input_error",
        "execution_status": "input_error",
        "capture_id": capture_id,
        "errors": errors,
        "task_summary": {
            "task_count": 0,
            "stage_counts": {},
            "status_counts": {},
            "task_ids_unique": True,
        },
        "gate_summary": {
            "segments_total": 0,
            "microtask_allowed_segments": 0,
            "microtask_pending_segments": 0,
            "microtask_blocked_segments": 0,
            "pending_reason_counts": {},
        },
        "tasks": [],
        "gate_decisions": [],
    }
    atomic_write_text(out_dir / "queue_probe_report.json", json_text(report) + "\n")
    atomic_write_text(out_dir / "queue_tasks.jsonl", "")
    (out_dir / "queue_probe_report.md").unlink(missing_ok=True)
    print(json_text(report), file=sys.stderr)
    return report


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    perf = report.get("performance") or {}
    gates = report.get("gate_summary") or {}
    lines = [
        "# Realtime Queue Probe",
        "",
        "## Boundary",
        "",
        "- This validates queue discipline and evidence gates, not full semantic understanding.",
        "- Visual signal stays on the fast path. OCR/ASR/VLM are asynchronous stages.",
        "- Microtasks are blocked when semantic evidence is missing.",
        "",
        "## Performance",
        "",
        f"- visual_sample_p95_ms: `{perf.get('visual_sample_p95_ms')}`",
        f"- visual_sample_max_ms: `{perf.get('visual_sample_max_ms')}`",
        f"- visual_fast_path_budget_ms: `{report.get('targets', {}).get('visual_fast_path_budget_ms')}`",
        f"- visual_budget_p95_pass: `{perf.get('visual_budget_p95_pass')}`",
        f"- visual_budget_max_pass: `{perf.get('visual_budget_max_pass')}`",
        "",
        "## Semantic Gate",
        "",
        f"- segments_total: `{gates.get('segments_total')}`",
        f"- microtask_allowed_segments: `{gates.get('microtask_allowed_segments')}`",
        f"- microtask_pending_segments: `{gates.get('microtask_pending_segments')}`",
        f"- microtask_blocked_segments: `{gates.get('microtask_blocked_segments')}`",
        f"- pending_reason_counts: `{gates.get('pending_reason_counts')}`",
        f"- audio_present: `{report.get('source_audio_present')}`",
        f"- vlm_available: `{report.get('vlm_available')}`",
        "",
        "## Decisions",
        "",
    ]
    for item in report.get("gate_decisions", []):
        lines.append(
            f"- segment {item['segment_index']} ({item['timeline_range_s']}s): "
            f"{item['status']} | allowed={item['allowed_to_generate_microtask']}"
        )
    atomic_write_text(path, "\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate non-blocking realtime queue and microtask evidence gates.")
    parser.add_argument("--timeline-report", required=True)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--visual-fast-path-budget-ms", type=float, default=50.0)
    parser.add_argument("--segment-decision-budget-ms", type=float, default=1000.0)
    parser.add_argument("--microtask-deadline-s", type=float, default=5.0)
    parser.add_argument("--ocr-ms-per-frame", type=float, default=1800.0)
    parser.add_argument("--vlm-available", action="store_true")
    args = parser.parse_args(argv)

    t0 = time.perf_counter()
    timeline_path = Path(args.timeline_report).resolve()
    out_dir = (
        Path(args.out_dir).resolve()
        if args.out_dir
        else timeline_path.parent / "queue_probe"
    )
    probe_run_id = f"qpr_{uuid.uuid4().hex}"
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    timeline_sha256: str | None = None
    metadata = report_metadata(
        probe_run_id=probe_run_id,
        generated_at=generated_at,
        timeline_path=timeline_path,
        timeline_sha256=timeline_sha256,
    )
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(
            json_text(
                {
                    **metadata,
                    "status": "input_error",
                    "execution_status": "input_error",
                    "errors": [
                        {
                            "code": "output_directory_unwritable",
                            "message": str(exc),
                        }
                    ],
                }
            ),
            file=sys.stderr,
        )
        return 2

    try:
        timeline_bytes = timeline_path.read_bytes()
    except OSError as exc:
        write_input_error(
            out_dir=out_dir,
            metadata=metadata,
            errors=[
                {
                    "code": "timeline_file_unreadable",
                    "message": str(exc),
                }
            ],
        )
        return 2

    timeline_sha256 = hashlib.sha256(timeline_bytes).hexdigest()
    metadata = report_metadata(
        probe_run_id=probe_run_id,
        generated_at=generated_at,
        timeline_path=timeline_path,
        timeline_sha256=timeline_sha256,
    )
    try:
        timeline = json.loads(timeline_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        write_input_error(
            out_dir=out_dir,
            metadata=metadata,
            errors=[
                {
                    "code": "timeline_json_invalid",
                    "message": str(exc),
                }
            ],
        )
        return 2
    if not isinstance(timeline, dict):
        write_input_error(
            out_dir=out_dir,
            metadata=metadata,
            errors=[
                {
                    "code": "timeline_top_level_object_required",
                    "message": "timeline JSON top level must be an object.",
                }
            ],
        )
        return 2

    numeric_parameters = {
        "visual_fast_path_budget_ms": args.visual_fast_path_budget_ms,
        "segment_decision_budget_ms": args.segment_decision_budget_ms,
        "microtask_deadline_s": args.microtask_deadline_s,
        "ocr_ms_per_frame": args.ocr_ms_per_frame,
    }
    invalid_parameters = [
        name
        for name, value in numeric_parameters.items()
        if not math.isfinite(value) or value <= 0
    ]
    if invalid_parameters:
        write_input_error(
            out_dir=out_dir,
            metadata=metadata,
            capture_id=timeline.get("capture_id"),
            errors=[
                {
                    "code": "numeric_parameter_invalid",
                    "fields": invalid_parameters,
                    "message": "numeric parameters must be positive finite numbers.",
                }
            ],
        )
        return 2

    try:
        tasks, gates = build_tasks(
            report=timeline,
            ocr_ms_per_frame=args.ocr_ms_per_frame,
            visual_deadline_ms=args.visual_fast_path_budget_ms,
            segment_deadline_ms=args.segment_decision_budget_ms,
            microtask_deadline_s=args.microtask_deadline_s,
            vlm_available=args.vlm_available,
            probe_run_id=probe_run_id,
        )
    except TimelineValidationError as exc:
        write_input_error(
            out_dir=out_dir,
            metadata=metadata,
            capture_id=timeline.get("capture_id"),
            errors=exc.errors,
        )
        return 2

    visual_costs = [
        task.estimated_cost_ms
        for task in tasks
        if task.stage == "visual_signal_fast_path" and task.estimated_cost_ms is not None
    ]
    visual_summary = summarize(visual_costs)
    pending = [gate for gate in gates if gate.status == "pending_semantic_evidence"]
    blocked = [gate for gate in gates if gate.status == "blocked_insufficient_semantic_evidence"]
    allowed = [gate for gate in gates if gate.allowed_to_generate_microtask]
    pending_reason_counts: dict[str, int] = {}
    for gate in pending:
        for reason in gate.reasons:
            if reason == "awaiting_async_result":
                pending_reason_counts[reason] = pending_reason_counts.get(reason, 0) + 1
    stage_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for task in tasks:
        stage_counts[task.stage] = stage_counts.get(task.stage, 0) + 1
        status_counts[task.status] = status_counts.get(task.status, 0) + 1

    visual_quality_pass = bool(
        visual_summary["p95"] is not None
        and visual_summary["p95"] <= args.visual_fast_path_budget_ms
        and visual_summary["max"] is not None
        and visual_summary["max"] <= args.visual_fast_path_budget_ms
    )
    execution_status = "success" if visual_quality_pass else "quality_gate_failed"

    report: dict[str, Any] = {
        **metadata,
        "status": execution_status,
        "execution_status": execution_status,
        "capture_id": timeline.get("capture_id"),
        "source": timeline.get("source"),
        "source_kind": timeline.get("source_kind"),
        "source_audio_present": stream_has_audio(timeline),
        "vlm_available": args.vlm_available,
        "targets": {
            "visual_fast_path_budget_ms": args.visual_fast_path_budget_ms,
            "segment_decision_budget_ms": args.segment_decision_budget_ms,
            "microtask_deadline_s": args.microtask_deadline_s,
            "ocr_ms_per_frame_assumption": args.ocr_ms_per_frame,
        },
        "performance": {
            "visual_sample_ms": visual_summary,
            "visual_sample_p95_ms": visual_summary["p95"],
            "visual_sample_max_ms": visual_summary["max"],
            "visual_budget_p95_pass": (
                visual_summary["p95"] is not None
                and visual_summary["p95"] <= args.visual_fast_path_budget_ms
            ),
            "visual_budget_max_pass": (
                visual_summary["max"] is not None
                and visual_summary["max"] <= args.visual_fast_path_budget_ms
            ),
            "probe_wall_s": time.perf_counter() - t0,
        },
        "task_summary": {
            "task_count": len(tasks),
            "stage_counts": stage_counts,
            "status_counts": status_counts,
            "task_ids_unique": len(tasks) == len({task.task_id for task in tasks}),
        },
        "gate_summary": {
            "segments_total": len(gates),
            "microtask_allowed_segments": len(allowed),
            "microtask_pending_segments": len(pending),
            "microtask_blocked_segments": len(blocked),
            "pending_reason_counts": pending_reason_counts,
        },
        "tasks": [asdict(task) for task in tasks],
        "gate_decisions": [asdict(gate) for gate in gates],
        "notes": [
            "A blocked microtask gate is a correct outcome when ASR/VLM evidence is missing.",
            "A queued ASR/VLM task remains pending until a completed semantic result is evaluated by the final semantic evidence gate.",
            "OCR is treated as auxiliary because previous local benchmark showed it cannot be the real-time main path.",
            "This probe should be rerun on live RTSP once port 8554 is available again.",
        ],
    }

    atomic_write_text(out_dir / "queue_probe_report.json", json_text(report) + "\n")
    task_lines = "".join(json_text(task, indent=None) + "\n" for task in report["tasks"])
    atomic_write_text(out_dir / "queue_tasks.jsonl", task_lines)
    write_markdown(out_dir / "queue_probe_report.md", report)
    print(json_text({
        "out_dir": str(out_dir),
        "execution_status": execution_status,
        "probe_run_id": probe_run_id,
        "task_count": len(tasks),
        "segments_total": len(gates),
        "visual_sample_p95_ms": report["performance"]["visual_sample_p95_ms"],
        "visual_budget_p95_pass": report["performance"]["visual_budget_p95_pass"],
        "visual_budget_max_pass": report["performance"]["visual_budget_max_pass"],
        "microtask_allowed_segments": len(allowed),
        "microtask_pending_segments": len(pending),
        "microtask_blocked_segments": len(blocked),
        "audio_present": report["source_audio_present"],
        "vlm_available": report["vlm_available"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
