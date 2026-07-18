#!/usr/bin/env python3
"""Conservative, platform-neutral semantic evidence aggregation gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
from typing import Any


VALID_EXECUTION_SCOPES = {"production", "contract_test"}
VALID_AUDIO_STATES = {"present", "absent", "unknown"}
TIMELINE_START_EPSILON_S = 0.001
QUALITY_THRESHOLD_KEYS = {
    "min_text_coverage_ratio",
    "min_mean_avg_logprob",
    "max_no_speech_prob",
}
QUALITY_SUMMARY_NUMERIC_KEYS = {
    "segment_count",
    "valid_quality_segment_count",
    "speech_segment_count",
    "transcribed_segment_count",
    "mean_avg_logprob",
    "mean_no_speech_prob",
    "max_no_speech_prob",
}
ASR_QUALITY_POLICY = {
    "policy_id": "asr_quality_gate_v1",
    "min_text_coverage_ratio": 0.8,
    "min_mean_avg_logprob": -0.6,
    "max_no_speech_prob": 0.6,
}
ASR_QUALITY_POLICY_THRESHOLDS = {
    key: ASR_QUALITY_POLICY[key] for key in QUALITY_THRESHOLD_KEYS
}
QUALITY_COUNT_KEYS = (
    "segment_count",
    "valid_quality_segment_count",
    "speech_segment_count",
    "transcribed_segment_count",
)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _has_text(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(isinstance(item, str) and item.strip() for item in value)
    return False


def _evidence_refs(result: dict[str, Any]) -> list[str]:
    refs = result.get("evidence_refs")
    if not isinstance(refs, list):
        return []
    return _unique([ref.strip() for ref in refs if isinstance(ref, str) and ref.strip()])


def _path_key(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().replace("\\", "/").rstrip("/").casefold()


def _capture_id(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _sha256_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        return None
    return normalized


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audio_state(
    timeline_report: dict[str, Any], audio_inventory: dict[str, Any]
) -> str:
    raw_recording = timeline_report.get("raw_recording")
    raw_file = raw_recording.get("file") if isinstance(raw_recording, dict) else None
    target_key = _path_key(raw_file)
    timeline_capture_id = _capture_id(timeline_report.get("capture_id"))
    inventory_capture_id = _capture_id(audio_inventory.get("capture_id"))
    files = audio_inventory.get("files")
    if not isinstance(files, list):
        return "unknown"
    candidates = [item for item in files if isinstance(item, dict)]
    if target_key is None and timeline_capture_id is None:
        return "unknown"
    if (
        timeline_capture_id is not None
        and inventory_capture_id is not None
        and inventory_capture_id != timeline_capture_id
    ):
        return "unknown"

    matched_candidates: list[dict[str, Any]] = []
    for item in candidates:
        item_capture_id = _capture_id(item.get("capture_id"))
        if (
            timeline_capture_id is not None
            and item_capture_id is not None
            and item_capture_id != timeline_capture_id
        ):
            continue
        path_matches = (
            target_key is not None and _path_key(item.get("path")) == target_key
        )
        capture_matches = timeline_capture_id is not None and (
            item_capture_id == timeline_capture_id
            or (
                inventory_capture_id == timeline_capture_id
                and item_capture_id is None
            )
        )
        if path_matches or capture_matches:
            matched_candidates.append(item)
    candidates = matched_candidates
    if not candidates:
        return "unknown"
    if any(item.get("error") for item in candidates):
        return "unknown"
    stream_counts = [item.get("audio_stream_count") for item in candidates]
    if any(_is_number(count) and count > 0 for count in stream_counts):
        return "present"
    if stream_counts and all(_is_number(count) and count == 0 for count in stream_counts):
        return "absent"
    return "unknown"


def _segment_bounds(segment: dict[str, Any]) -> tuple[float, float] | None:
    start = segment.get("start_s")
    end = segment.get("end_s")
    if (
        not _is_number(start)
        or not _is_number(end)
        or float(start) < 0
        or float(end) <= float(start)
    ):
        return None
    return float(start), float(end)


def _result_aligned(result: dict[str, Any], segment: dict[str, Any]) -> bool:
    if result.get("segment_index") != segment.get("segment_index"):
        return False
    bounds = _segment_bounds(segment)
    result_start = result.get("start_s")
    result_end = result.get("end_s")
    if bounds is None or not _is_number(result_start) or not _is_number(result_end):
        return False
    start, end = bounds
    aligned_start = float(result_start)
    aligned_end = float(result_end)
    return (
        aligned_end > aligned_start
        and aligned_start >= start
        and aligned_end <= end
    )


def _valid_results(
    report: dict[str, Any] | None,
    segment: dict[str, Any],
    *,
    kind: str,
    capture_id: str | None,
    source_media_sha256: str | None,
) -> list[dict[str, Any]]:
    if not isinstance(report, dict) or not isinstance(report.get("results"), list):
        return []
    if kind in {"asr", "vlm"} and (
        capture_id is None
        or report.get("capture_id") != capture_id
        or source_media_sha256 is None
        or _sha256_value(report.get("source_media_sha256"))
        != source_media_sha256
    ):
        return []
    valid: list[dict[str, Any]] = []
    for result in report["results"]:
        if not isinstance(result, dict):
            continue
        if str(result.get("status", "")).casefold() != "success":
            continue
        if kind in {"asr", "vlm"} and (
            capture_id is None or result.get("capture_id") != capture_id
        ):
            continue
        if kind in {"asr", "vlm"} and (
            source_media_sha256 is None
            or _sha256_value(result.get("source_media_sha256"))
            != source_media_sha256
        ):
            continue
        content = result.get("text") if kind != "vlm" else result.get("summary", result.get("text"))
        if not _has_text(content) or not _result_aligned(result, segment):
            continue
        refs = _evidence_refs(result)
        if not refs:
            continue
        if kind in {"asr", "vlm"} and not _has_text(result.get("model_id")):
            continue
        valid.append(result)
    return valid


def _refs_from_results(results: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for result in results:
        refs.extend(_evidence_refs(result))
    return _unique(refs)


def _timeline_valid(timeline_report: dict[str, Any]) -> bool:
    segments = timeline_report.get("segments")
    timeline_duration = timeline_report.get("timeline_duration_s")
    capture_wall = timeline_report.get("capture_wall_s")
    if (
        timeline_report.get("error")
        or not _is_number(timeline_report.get("sampled_frames"))
        or timeline_report["sampled_frames"] <= 0
        or not _is_number(timeline_report.get("decoded_frames"))
        or timeline_report["decoded_frames"] <= 0
        or not _is_number(timeline_duration)
        or timeline_duration <= 0
        or not _is_number(capture_wall)
        or capture_wall <= 0
        or not isinstance(segments, list)
        or not segments
    ):
        return False

    indices: list[int] = []
    previous_end: float | None = None
    upper_bound = min(float(timeline_duration), float(capture_wall))
    for segment in segments:
        if not isinstance(segment, dict):
            return False
        index = segment.get("segment_index")
        if not isinstance(index, int) or isinstance(index, bool):
            return False
        indices.append(index)
        bounds = _segment_bounds(segment)
        if bounds is None or bounds[1] > upper_bound:
            return False
        if previous_end is None:
            if bounds[0] > TIMELINE_START_EPSILON_S:
                return False
        elif bounds[0] < previous_end:
            return False
        previous_end = bounds[1]
        evidence_files = segment.get("evidence_files")
        if not isinstance(evidence_files, list) or not any(
            isinstance(item, str) and item.strip() for item in evidence_files
        ):
            return False
    return (
        len(indices) == len(set(indices))
        and indices == list(range(1, len(indices) + 1))
        and previous_end is not None
        and previous_end <= float(timeline_duration)
    )


def _canonical_manifest_valid(timeline_report: dict[str, Any]) -> bool:
    capture_id = _capture_id(timeline_report.get("capture_id"))
    manifest_id = _capture_id(timeline_report.get("manifest_id"))
    manifest_file = timeline_report.get("manifest_file")
    raw_recording = timeline_report.get("raw_recording")
    if (
        capture_id is None
        or manifest_id is None
        or not isinstance(manifest_file, str)
        or not manifest_file.strip()
        or not isinstance(raw_recording, dict)
    ):
        return False
    raw_file = raw_recording.get("file")
    canonical_file = raw_recording.get("canonical_file")
    raw_sha256 = _sha256_value(raw_recording.get("sha256"))
    raw_size = raw_recording.get("size_bytes")
    if (
        not isinstance(raw_file, str)
        or not raw_file.strip()
        or not isinstance(canonical_file, str)
        or not canonical_file.strip()
        or raw_sha256 is None
        or not isinstance(raw_size, int)
        or isinstance(raw_size, bool)
        or raw_size <= 0
    ):
        return False
    try:
        raw_path = Path(raw_file)
        if (
            not raw_path.is_file()
            or raw_path.stat().st_size != raw_size
            or not _same_path(raw_path, Path(canonical_file))
        ):
            return False
        manifest = _read_json(manifest_file)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return False
    manifest_raw = manifest.get("raw_recording")
    artifact = (
        manifest.get("artifacts", {}).get("timeline_report")
        if isinstance(manifest.get("artifacts"), dict)
        else None
    )
    return bool(
        manifest.get("schema_version") == "1.0"
        and manifest.get("manifest_id") == manifest_id
        and _capture_id(manifest.get("capture_id")) == capture_id
        and manifest.get("source_kind") == "live_rtsp"
        and manifest.get("source") == timeline_report.get("source")
        and manifest.get("rtsp_url") == timeline_report.get("rtsp_url")
        and manifest.get("trust_level") == "content_hash_bound"
        and isinstance(manifest_raw, dict)
        and _sha256_value(manifest_raw.get("sha256")) == raw_sha256
        and manifest_raw.get("size_bytes") == raw_size
        and isinstance(manifest_raw.get("canonical_file"), str)
        and _same_path(Path(manifest_raw["canonical_file"]), raw_path)
        and isinstance(artifact, dict)
        and _path_key(artifact.get("file")) is not None
        and isinstance(artifact.get("size_bytes"), int)
        and not isinstance(artifact.get("size_bytes"), bool)
        and artifact["size_bytes"] > 0
        and _sha256_value(artifact.get("sha256")) is not None
    )


def _live_source_valid(timeline_report: dict[str, Any]) -> bool:
    source = timeline_report.get("source")
    rtsp_url = timeline_report.get("rtsp_url")
    common_live_contract = bool(
        timeline_report.get("source_kind") == "live_rtsp"
        and isinstance(source, str)
        and isinstance(rtsp_url, str)
        and source.strip().startswith("rtsp://")
        and source.strip() == rtsp_url.strip()
    )
    if not common_live_contract:
        return False
    mode = timeline_report.get("mode")
    canonical_fields = {
        "acquisition_source_kind",
        "analysis_source_kind",
        "analysis_wall_s",
        "trust_level",
        "production_usable",
        "manifest_id",
        "manifest_file",
    }
    if mode == "passive_rtsp_live_visual_timeline":
        return not canonical_fields.intersection(timeline_report)
    if mode != "deferred_canonical_raw_timeline":
        return False
    return bool(
        timeline_report.get("acquisition_source_kind") == "live_rtsp"
        and timeline_report.get("analysis_source_kind") == "canonical_raw_replay"
        and _is_number(timeline_report.get("capture_wall_s"))
        and float(timeline_report["capture_wall_s"]) > 0.0
        and _is_number(timeline_report.get("analysis_wall_s"))
        and float(timeline_report["analysis_wall_s"]) > 0.0
        and timeline_report.get("trust_level") == "content_hash_bound"
        and timeline_report.get("production_usable") is True
        and _canonical_manifest_valid(timeline_report)
    )


def _raw_recording_bound(
    timeline_report: dict[str, Any], capture_id: str | None
) -> bool:
    raw_recording = timeline_report.get("raw_recording")
    return bool(
        capture_id is not None
        and isinstance(raw_recording, dict)
        and _capture_id(raw_recording.get("capture_id")) == capture_id
        and _path_key(raw_recording.get("file")) is not None
    )


def _raw_content_binding(
    timeline_report: dict[str, Any], capture_id: str | None
) -> tuple[bool, str | None, list[str]]:
    raw_recording = timeline_report.get("raw_recording")
    gaps: list[str] = []
    if not _raw_recording_bound(timeline_report, capture_id):
        gaps.append("raw_recording_capture_binding_required_for_production")
    if not isinstance(raw_recording, dict):
        return False, None, gaps

    raw_file = raw_recording.get("file")
    raw_path = Path(raw_file) if isinstance(raw_file, str) and raw_file.strip() else None
    declared_sha256 = _sha256_value(raw_recording.get("sha256"))
    if declared_sha256 is None:
        gaps.append("raw_recording_sha256_required_for_production")
    if raw_path is None or not raw_path.is_file():
        gaps.append("raw_recording_file_missing_for_production")
        return False, None, _unique(gaps)

    try:
        computed_sha256 = _file_sha256(raw_path)
    except OSError:
        gaps.append("raw_recording_file_unreadable_for_production")
        return False, None, _unique(gaps)
    if declared_sha256 is not None and declared_sha256 != computed_sha256:
        gaps.append("raw_recording_sha256_mismatch")
    return not gaps, computed_sha256, _unique(gaps)


def _semantic_report_binding_gaps(
    report: dict[str, Any] | None,
    *,
    kind: str,
    capture_id: str | None,
    source_media_sha256: str | None,
) -> list[str]:
    if report is None:
        return []
    if not isinstance(report, dict):
        return [f"{kind}_report_invalid"]

    gaps: list[str] = []
    report_capture_id = _capture_id(report.get("capture_id"))
    if report_capture_id is None:
        gaps.append(f"{kind}_report_capture_id_missing")
    elif report_capture_id != capture_id:
        gaps.append(f"{kind}_report_capture_id_mismatch")

    report_sha256 = _sha256_value(report.get("source_media_sha256"))
    if report_sha256 is None:
        gaps.append(f"{kind}_report_source_media_sha256_missing")
    elif source_media_sha256 is None or report_sha256 != source_media_sha256:
        gaps.append(f"{kind}_report_source_media_sha256_mismatch")

    results = report.get("results")
    if isinstance(results, list):
        for result in [item for item in results if isinstance(item, dict)]:
            result_capture_id = _capture_id(result.get("capture_id"))
            if result_capture_id is None:
                gaps.append(f"{kind}_result_capture_id_missing")
            elif result_capture_id != capture_id:
                gaps.append(f"{kind}_result_capture_id_mismatch")
            result_sha256 = _sha256_value(result.get("source_media_sha256"))
            if result_sha256 is None:
                gaps.append(f"{kind}_result_source_media_sha256_missing")
            elif source_media_sha256 is None or result_sha256 != source_media_sha256:
                gaps.append(f"{kind}_result_source_media_sha256_mismatch")
    return _unique(gaps)


def _results_collection_gaps(
    report: dict[str, Any] | None,
    *,
    kind: str,
    expected_segment_indices: list[int],
) -> list[str]:
    if report is None:
        return []
    if not isinstance(report, dict):
        return [f"{kind}_results_collection_invalid"]
    results = report.get("results")
    if not isinstance(results, list) or not results:
        return [f"{kind}_results_collection_invalid"]
    if any(not isinstance(result, dict) for result in results):
        return [f"{kind}_results_collection_invalid"]
    indices = [result.get("segment_index") for result in results]
    if any(
        not isinstance(index, int) or isinstance(index, bool) for index in indices
    ):
        return [f"{kind}_results_collection_invalid"]
    if len(indices) != len(set(indices)) or set(indices) != set(
        expected_segment_indices
    ):
        return [f"{kind}_results_collection_invalid"]
    return []


def _quality_thresholds(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict) or not QUALITY_THRESHOLD_KEYS.issubset(value):
        return None
    if not all(_is_number(value[key]) for key in QUALITY_THRESHOLD_KEYS):
        return None
    thresholds = {key: float(value[key]) for key in sorted(QUALITY_THRESHOLD_KEYS)}
    if not 0.0 <= thresholds["min_text_coverage_ratio"] <= 1.0:
        return None
    if thresholds["min_mean_avg_logprob"] > 0.0:
        return None
    if not 0.0 <= thresholds["max_no_speech_prob"] <= 1.0:
        return None
    return thresholds


def _valid_quality_segment_id(value: Any) -> bool:
    return bool(
        (isinstance(value, int) and not isinstance(value, bool) and value >= 0)
        or (isinstance(value, str) and value.strip())
    )


def _evaluate_quality_node(
    node: Any,
    *,
    expected_claimed_thresholds: dict[str, float] | None,
    require_node_thresholds: bool,
) -> dict[str, Any]:
    """Validate claimed structure, then recompute against the gate-owned policy."""
    claimed_status = node.get("quality_status") if isinstance(node, dict) else None
    node_reasons = node.get("quality_reasons") if isinstance(node, dict) else None
    summary = node.get("quality_summary") if isinstance(node, dict) else None
    summary_reasons = summary.get("quality_reasons") if isinstance(summary, dict) else None
    node_thresholds_value = node.get("quality_thresholds") if isinstance(node, dict) else None
    summary_thresholds_value = (
        summary.get("quality_thresholds") if isinstance(summary, dict) else None
    )
    claimed_thresholds_value = (
        node_thresholds_value if require_node_thresholds else summary_thresholds_value
    )
    node_thresholds = _quality_thresholds(node_thresholds_value)
    summary_thresholds = _quality_thresholds(summary_thresholds_value)
    claimed_thresholds = _quality_thresholds(claimed_thresholds_value)
    claimed_reasons = _unique(
        [
            reason
            for reasons in (node_reasons, summary_reasons)
            if isinstance(reasons, list)
            for reason in reasons
            if isinstance(reason, str) and reason
        ]
    )
    if claimed_status == "fail" and not claimed_reasons:
        claimed_reasons.append("claimed_quality_status_failed")

    structurally_valid = bool(
        isinstance(node, dict)
        and claimed_status in {"pass", "fail"}
        and isinstance(node_reasons, list)
        and all(isinstance(reason, str) and reason for reason in node_reasons)
        and isinstance(summary, dict)
        and summary.get("quality_status") in {"pass", "fail"}
        and isinstance(summary_reasons, list)
        and all(isinstance(reason, str) and reason for reason in summary_reasons)
        and QUALITY_SUMMARY_NUMERIC_KEYS.issubset(summary)
        and all(_is_number(summary[key]) for key in QUALITY_SUMMARY_NUMERIC_KEYS)
    )
    if summary_thresholds is None:
        structurally_valid = False
    if require_node_thresholds and node_thresholds is None:
        structurally_valid = False
    if require_node_thresholds and node_thresholds != summary_thresholds:
        structurally_valid = False
    if (
        summary_thresholds is not None
        and expected_claimed_thresholds is not None
        and summary_thresholds != expected_claimed_thresholds
    ):
        structurally_valid = False

    counts: dict[str, int] | None = None
    coverage_key: str | None = None
    coverage: float | None = None
    if isinstance(summary, dict) and QUALITY_SUMMARY_NUMERIC_KEYS.issubset(summary):
        if all(
            isinstance(summary[key], int)
            and not isinstance(summary[key], bool)
            and summary[key] >= 0
            for key in QUALITY_COUNT_KEYS
        ):
            counts = {key: summary[key] for key in QUALITY_COUNT_KEYS}
            if not (
                counts["segment_count"]
                >= counts["valid_quality_segment_count"]
                >= counts["speech_segment_count"]
                >= counts["transcribed_segment_count"]
                >= 0
            ):
                structurally_valid = False
        else:
            structurally_valid = False

        invalid_ids = summary.get("invalid_quality_segment_ids")
        invalid_count = (
            counts["segment_count"] - counts["valid_quality_segment_count"]
            if counts is not None
            else None
        )
        if not isinstance(invalid_ids, list) or invalid_count is None:
            structurally_valid = False
        else:
            normalized_ids = [
                (type(segment_id).__name__, str(segment_id)) for segment_id in invalid_ids
            ]
            if (
                len(invalid_ids) != invalid_count
                or not all(_valid_quality_segment_id(segment_id) for segment_id in invalid_ids)
                or len(normalized_ids) != len(set(normalized_ids))
            ):
                structurally_valid = False

        has_preferred = "nonempty_emitted_segment_ratio" in summary
        has_legacy = "text_coverage_ratio" in summary
        if not has_preferred and not has_legacy:
            structurally_valid = False
        else:
            preferred = summary.get("nonempty_emitted_segment_ratio")
            legacy = summary.get("text_coverage_ratio")
            if has_preferred and not _is_number(preferred):
                structurally_valid = False
            if has_legacy and not _is_number(legacy):
                structurally_valid = False
            if has_preferred and has_legacy and _is_number(preferred) and _is_number(legacy):
                if float(preferred) != float(legacy):
                    structurally_valid = False
            selected = preferred if has_preferred else legacy
            coverage_key = (
                "nonempty_emitted_segment_ratio" if has_preferred else "text_coverage_ratio"
            )
            if _is_number(selected):
                coverage = float(selected)
                if not 0.0 <= coverage <= 1.0:
                    structurally_valid = False
                if counts is not None:
                    expected_coverage = (
                        counts["transcribed_segment_count"]
                        / counts["speech_segment_count"]
                        if counts["speech_segment_count"]
                        else 0.0
                    )
                    if coverage != expected_coverage:
                        structurally_valid = False

        if all(_is_number(summary.get(key)) for key in (
            "mean_avg_logprob", "mean_no_speech_prob", "max_no_speech_prob"
        )):
            if float(summary["mean_avg_logprob"]) > 0.0:
                structurally_valid = False
            mean_no_speech = float(summary["mean_no_speech_prob"])
            max_no_speech = float(summary["max_no_speech_prob"])
            if not (0.0 <= mean_no_speech <= max_no_speech <= 1.0):
                structurally_valid = False

    evaluated_metrics: dict[str, dict[str, Any]] = {}
    recomputed_reasons: list[str] = []
    if isinstance(summary, dict):
        mean_avg_logprob = summary.get("mean_avg_logprob")
        max_no_speech_prob = summary.get("max_no_speech_prob")
        if _is_number(mean_avg_logprob):
            actual = float(mean_avg_logprob)
            passed = actual >= ASR_QUALITY_POLICY_THRESHOLDS["min_mean_avg_logprob"]
            evaluated_metrics["mean_avg_logprob"] = {
                "actual": actual,
                "threshold": ASR_QUALITY_POLICY_THRESHOLDS["min_mean_avg_logprob"],
                "comparison": ">=",
                "passed": passed,
            }
            if not passed:
                recomputed_reasons.append("mean_avg_logprob_below_threshold")
        if _is_number(max_no_speech_prob):
            actual = float(max_no_speech_prob)
            passed = actual <= ASR_QUALITY_POLICY_THRESHOLDS["max_no_speech_prob"]
            evaluated_metrics["max_no_speech_prob"] = {
                "actual": actual,
                "threshold": ASR_QUALITY_POLICY_THRESHOLDS["max_no_speech_prob"],
                "comparison": "<=",
                "passed": passed,
            }
            if not passed:
                recomputed_reasons.append("max_no_speech_prob_above_threshold")
        if coverage is not None:
            passed = coverage >= ASR_QUALITY_POLICY_THRESHOLDS[
                "min_text_coverage_ratio"
            ]
            evaluated_metrics["nonempty_emitted_segment_ratio"] = {
                "actual": coverage,
                "source_field": coverage_key,
                "threshold": ASR_QUALITY_POLICY_THRESHOLDS[
                    "min_text_coverage_ratio"
                ],
                "comparison": ">=",
                "passed": passed,
            }
            if not passed:
                recomputed_reasons.append("text_coverage_below_threshold")
    recomputed_reasons = _unique(recomputed_reasons)
    claimed_failed = bool(claimed_status == "fail" or claimed_reasons)
    recomputed_failed = bool(recomputed_reasons)
    if not structurally_valid and not claimed_reasons and not recomputed_reasons:
        recomputed_reasons.append("quality_node_missing_or_invalid")

    return {
        "structurally_valid": structurally_valid,
        "claimed_failed": claimed_failed,
        "recomputed_failed": recomputed_failed,
        "counts": counts,
        "audit": {
            "quality_status": claimed_status,
            "quality_reasons": node_reasons,
            "claimed_quality_reasons": claimed_reasons,
            "recomputed_quality_reasons": recomputed_reasons,
            "claimed_quality_thresholds": claimed_thresholds_value,
            "evaluated_metrics": evaluated_metrics,
        },
    }


def _evaluate_alignment_summary(
    value: Any,
    *,
    report_counts: dict[str, int] | None,
    result_counts: list[dict[str, int] | None],
) -> tuple[bool, bool, dict[str, Any], list[str]]:
    audit = {
        "raw_segment_count": value.get("raw_segment_count")
        if isinstance(value, dict)
        else None,
        "assigned_raw_segment_count": value.get("assigned_raw_segment_count")
        if isinstance(value, dict)
        else None,
        "unassigned_raw_segment_ids": value.get("unassigned_raw_segment_ids")
        if isinstance(value, dict)
        else None,
        "recomputed_quality_reasons": [],
    }
    if not isinstance(value, dict):
        return False, False, audit, []
    raw_count = value.get("raw_segment_count")
    assigned_count = value.get("assigned_raw_segment_count")
    unassigned_ids = value.get("unassigned_raw_segment_ids")
    if not (
        isinstance(raw_count, int)
        and not isinstance(raw_count, bool)
        and raw_count >= 0
        and isinstance(assigned_count, int)
        and not isinstance(assigned_count, bool)
        and assigned_count >= 0
        and isinstance(unassigned_ids, list)
        and all(_valid_quality_segment_id(segment_id) for segment_id in unassigned_ids)
    ):
        return False, False, audit, []
    normalized_ids = [
        (type(segment_id).__name__, str(segment_id)) for segment_id in unassigned_ids
    ]
    result_segment_count = (
        sum(counts["segment_count"] for counts in result_counts if counts is not None)
        if all(counts is not None for counts in result_counts)
        else None
    )
    structurally_valid = bool(
        report_counts is not None
        and result_segment_count is not None
        and raw_count == report_counts["segment_count"]
        and assigned_count == result_segment_count
        and 0 <= assigned_count <= raw_count
        and len(unassigned_ids) == raw_count - assigned_count
        and len(normalized_ids) == len(set(normalized_ids))
    )
    reasons = (
        ["raw_segments_unaligned_to_timeline"]
        if structurally_valid and unassigned_ids
        else []
    )
    audit["recomputed_quality_reasons"] = reasons
    return structurally_valid, bool(reasons), audit, reasons


def _asr_quality_validation(
    report: dict[str, Any] | None,
) -> tuple[bool, list[str], dict[str, Any] | None, list[str]]:
    if report is None:
        return True, [], None, []
    if not isinstance(report, dict):
        return (
            False,
            ["asr_quality_missing_or_invalid"],
            {"report": None, "results": []},
            [],
        )

    report_thresholds = _quality_thresholds(report.get("quality_thresholds"))
    report_evaluation = _evaluate_quality_node(
        report,
        expected_claimed_thresholds=report_thresholds,
        require_node_thresholds=True,
    )
    audit: dict[str, Any] = {
        "quality_policy": dict(ASR_QUALITY_POLICY),
        "report": report_evaluation["audit"],
        "results": [],
    }
    evaluations = [report_evaluation]
    results = report.get("results")
    if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
        audit["claimed_quality_reasons"] = report_evaluation["audit"][
            "claimed_quality_reasons"
        ]
        audit["recomputed_quality_reasons"] = _unique(
            report_evaluation["audit"]["recomputed_quality_reasons"]
            + ["quality_node_missing_or_invalid"]
        )
        return (
            False,
            ["asr_quality_missing_or_invalid"],
            audit,
            _unique(
                audit["claimed_quality_reasons"]
                + audit["recomputed_quality_reasons"]
            ),
        )

    for result in results:
        evaluation = _evaluate_quality_node(
            result,
            expected_claimed_thresholds=report_thresholds,
            require_node_thresholds=False,
        )
        evaluation["audit"]["segment_index"] = result.get("segment_index")
        audit["results"].append(evaluation["audit"])
        evaluations.append(evaluation)

    report_counts = report_evaluation["counts"]
    result_counts = [evaluation["counts"] for evaluation in evaluations[1:]]
    (
        alignment_structurally_valid,
        alignment_failed,
        alignment_audit,
        alignment_reasons,
    ) = _evaluate_alignment_summary(
        report.get("alignment_summary"),
        report_counts=report_counts,
        result_counts=result_counts,
    )
    audit["alignment_summary"] = alignment_audit

    cross_level_valid = False
    if (
        alignment_structurally_valid
        and report_counts is not None
        and all(counts is not None for counts in result_counts)
    ):
        unassigned_count = len(alignment_audit["unassigned_raw_segment_ids"])
        cross_level_valid = all(
            sum(counts[key] for counts in result_counts if counts is not None)
            <= report_counts[key]
            <= sum(counts[key] for counts in result_counts if counts is not None)
            + unassigned_count
            for key in QUALITY_COUNT_KEYS[1:]
        )
    if not cross_level_valid:
        audit["report"]["recomputed_quality_reasons"] = _unique(
            audit["report"]["recomputed_quality_reasons"]
            + ["quality_count_totals_mismatch"]
        )

    claimed_reasons = _unique(
        [
            reason
            for evaluation in evaluations
            for reason in evaluation["audit"]["claimed_quality_reasons"]
        ]
    )
    recomputed_reasons = _unique(
        [
            reason
            for evaluation in evaluations
            for reason in evaluation["audit"]["recomputed_quality_reasons"]
        ]
        + alignment_reasons
    )
    audit["claimed_quality_reasons"] = claimed_reasons
    audit["recomputed_quality_reasons"] = recomputed_reasons

    gaps: list[str] = []
    if (
        any(not evaluation["structurally_valid"] for evaluation in evaluations)
        or not alignment_structurally_valid
        or not cross_level_valid
    ):
        gaps.append("asr_quality_missing_or_invalid")
    if any(
        evaluation["claimed_failed"] or evaluation["recomputed_failed"]
        for evaluation in evaluations
    ) or alignment_failed:
        gaps.append("asr_quality_failed")
    audit_reasons = _unique(claimed_reasons + recomputed_reasons)
    if gaps and not audit_reasons:
        audit_reasons = list(gaps)
    gaps = _unique(gaps)
    return not gaps, gaps, audit, audit_reasons


def evaluate_evidence(
    timeline_report: dict[str, Any],
    audio_inventory: dict[str, Any],
    *,
    asr_results: dict[str, Any] | None = None,
    vlm_results: dict[str, Any] | None = None,
    ocr_report: dict[str, Any] | None = None,
    execution_scope: str = "production",
    contract_test: bool = False,
    expected_capture_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate each timeline segment without claiming model capability."""
    if execution_scope not in VALID_EXECUTION_SCOPES:
        raise ValueError(f"invalid execution_scope: {execution_scope}")
    if not isinstance(timeline_report, dict):
        raise TypeError("timeline_report must be a JSON object")
    if not isinstance(audio_inventory, dict):
        raise TypeError("audio_inventory must be a JSON object")

    source_kind = timeline_report.get("source_kind") or "unknown"
    capture_id = _capture_id(timeline_report.get("capture_id"))
    trusted_capture_id = _capture_id(expected_capture_id)
    audio_state = _audio_state(timeline_report, audio_inventory)
    if audio_state not in VALID_AUDIO_STATES:  # defensive invariant
        audio_state = "unknown"
    timeline_ok = _timeline_valid(timeline_report)
    source_is_live = _live_source_valid(timeline_report)
    raw_recording_bound = _raw_recording_bound(timeline_report, capture_id)
    raw_recording = timeline_report.get("raw_recording")
    declared_media_sha256 = (
        _sha256_value(raw_recording.get("sha256"))
        if isinstance(raw_recording, dict)
        else None
    )
    if execution_scope == "production":
        raw_content_bound, source_media_sha256, raw_binding_gaps = (
            _raw_content_binding(timeline_report, capture_id)
        )
    else:
        raw_content_bound = False
        source_media_sha256 = declared_media_sha256
        raw_binding_gaps = []
    timeline_segments = timeline_report.get("segments")
    expected_segment_indices = (
        [
            segment.get("segment_index")
            for segment in timeline_segments
            if isinstance(segment, dict)
            and isinstance(segment.get("segment_index"), int)
            and not isinstance(segment.get("segment_index"), bool)
        ]
        if isinstance(timeline_segments, list)
        else []
    )
    asr_binding_gaps = _semantic_report_binding_gaps(
        asr_results,
        kind="asr",
        capture_id=capture_id,
        source_media_sha256=source_media_sha256,
    )
    vlm_binding_gaps = _semantic_report_binding_gaps(
        vlm_results,
        kind="vlm",
        capture_id=capture_id,
        source_media_sha256=source_media_sha256,
    )
    asr_collection_gaps = _results_collection_gaps(
        asr_results,
        kind="asr",
        expected_segment_indices=expected_segment_indices,
    )
    vlm_collection_gaps = _results_collection_gaps(
        vlm_results,
        kind="vlm",
        expected_segment_indices=expected_segment_indices,
    )
    (
        asr_quality_valid,
        asr_quality_gaps,
        asr_quality_audit,
        asr_quality_reasons,
    ) = _asr_quality_validation(asr_results)
    semantic_binding_gaps = _unique(
        asr_binding_gaps
        + vlm_binding_gaps
        + asr_collection_gaps
        + vlm_collection_gaps
        + asr_quality_gaps
    )
    semantic_reports_bound = not semantic_binding_gaps
    fixture_marker = timeline_report.get("fixture") is True
    fixture_contract = (
        source_kind == "fixture"
        and fixture_marker
        and execution_scope == "contract_test"
        and contract_test is True
    )
    segments = timeline_report.get("segments")
    if not isinstance(segments, list):
        segments = []

    segment_reports: list[dict[str, Any]] = []
    for segment in [item for item in segments if isinstance(item, dict)]:
        bound_asr = _valid_results(
            asr_results,
            segment,
            kind="asr",
            capture_id=capture_id,
            source_media_sha256=source_media_sha256,
        )
        asr_rejected_by_quality_gate = bool(
            bound_asr
            and not asr_binding_gaps
            and not asr_collection_gaps
            and "asr_quality_failed" in asr_quality_gaps
            and "asr_quality_missing_or_invalid" not in asr_quality_gaps
        )
        valid_asr = bound_asr
        if not asr_quality_valid:
            valid_asr = []
        if asr_collection_gaps:
            valid_asr = []
        valid_vlm = _valid_results(
            vlm_results,
            segment,
            kind="vlm",
            capture_id=capture_id,
            source_media_sha256=source_media_sha256,
        )
        if vlm_collection_gaps:
            valid_vlm = []
        valid_ocr = _valid_results(
            ocr_report,
            segment,
            kind="ocr",
            capture_id=capture_id,
            source_media_sha256=source_media_sha256,
        )
        usable_asr = valid_asr if audio_state == "present" else []
        usable_vlm = [] if asr_rejected_by_quality_gate else valid_vlm
        primary_refs = _unique(
            _refs_from_results(usable_asr) + _refs_from_results(usable_vlm)
        )
        auxiliary_refs = _refs_from_results(valid_ocr)

        reasons: list[str] = []
        gaps: list[str] = list(semantic_binding_gaps)
        if timeline_ok:
            reasons.append("timeline_report_valid")
        else:
            gaps.append("timeline_report_invalid")

        if audio_state == "present":
            reasons.append("audio_present_asr_schedulable")
        elif audio_state == "absent":
            gaps.append("audio_absent")
        else:
            gaps.append("audio_state_unknown")

        if usable_asr:
            reasons.append("valid_asr_primary_evidence")
        elif audio_state == "present":
            gaps.append(
                "asr_result_rejected_by_quality_gate"
                if asr_rejected_by_quality_gate
                else "asr_result_missing_or_invalid"
            )
        if usable_vlm:
            reasons.append("valid_vlm_primary_evidence")
        elif vlm_results is not None:
            gaps.append("vlm_result_missing_or_invalid")
        if valid_ocr:
            reasons.append("ocr_auxiliary_only")
        if not primary_refs:
            gaps.append("primary_semantic_evidence_missing")

        if execution_scope == "production" and contract_test is not False:
            gaps.append("contract_test_marker_forbidden_in_production")
        if execution_scope == "production" and fixture_marker:
            gaps.append("fixture_marker_forbidden_in_production")
        if execution_scope == "production" and capture_id is None:
            gaps.append("capture_id_required_for_production")
        if execution_scope == "production" and trusted_capture_id is None:
            gaps.append("expected_capture_id_required_for_production")
        elif execution_scope == "production" and trusted_capture_id != capture_id:
            gaps.append("expected_capture_id_mismatch")
        if execution_scope == "production":
            gaps.extend(raw_binding_gaps)

        if source_kind == "local_replay":
            reasons.append("local_replay_not_production_source")
            gaps.append("live_rtsp_source_required_for_production")
        elif source_kind == "fixture" and not fixture_contract:
            if not fixture_marker:
                gaps.append("fixture_marker_required_for_contract_test")
            gaps.append("fixture_requires_explicit_contract_test")
        elif source_kind != "fixture" and not source_is_live:
            gaps.append("live_rtsp_source_required_for_production")

        production_allowed = bool(
            execution_scope == "production"
            and source_is_live
            and not fixture_marker
            and contract_test is False
            and capture_id is not None
            and trusted_capture_id == capture_id
            and raw_recording_bound
            and raw_content_bound
            and semantic_reports_bound
            and timeline_ok
            and primary_refs
        )
        if production_allowed:
            decision = "production_pass"
            reasons.append("production_gate_requirements_met")
        elif fixture_contract and timeline_ok and primary_refs:
            decision = "contract_test_pass"
            reasons.append("contract_test_requirements_met")
        else:
            decision = "blocked"

        segment_reports.append(
            {
                "segment_index": segment.get("segment_index"),
                "start_s": segment.get("start_s"),
                "end_s": segment.get("end_s"),
                "decision": decision,
                "production_allowed": production_allowed,
                "reasons": _unique(reasons),
                "evidence_gaps": _unique(gaps),
                "primary_evidence_refs": primary_refs,
                "auxiliary_evidence_refs": auxiliary_refs,
                "source_kind": source_kind,
                "execution_scope": execution_scope,
                "audio_state": audio_state,
                "asr_quality_reasons": asr_quality_reasons,
            }
        )

    top_gaps = _unique(
        [gap for item in segment_reports for gap in item["evidence_gaps"]]
    )
    top_gaps = _unique(top_gaps + semantic_binding_gaps + raw_binding_gaps)
    if not timeline_ok and "timeline_report_invalid" not in top_gaps:
        top_gaps.append("timeline_report_invalid")
    if (
        execution_scope == "production"
        and contract_test is not False
        and "contract_test_marker_forbidden_in_production" not in top_gaps
    ):
        top_gaps.append("contract_test_marker_forbidden_in_production")
    if (
        execution_scope == "production"
        and fixture_marker
        and "fixture_marker_forbidden_in_production" not in top_gaps
    ):
        top_gaps.append("fixture_marker_forbidden_in_production")
    if (
        source_kind == "fixture"
        and not fixture_marker
        and "fixture_marker_required_for_contract_test" not in top_gaps
    ):
        top_gaps.append("fixture_marker_required_for_contract_test")
    if (
        execution_scope == "production"
        and capture_id is None
        and "capture_id_required_for_production" not in top_gaps
    ):
        top_gaps.append("capture_id_required_for_production")
    if (
        execution_scope == "production"
        and trusted_capture_id is None
        and "expected_capture_id_required_for_production" not in top_gaps
    ):
        top_gaps.append("expected_capture_id_required_for_production")
    elif (
        execution_scope == "production"
        and trusted_capture_id != capture_id
        and "expected_capture_id_mismatch" not in top_gaps
    ):
        top_gaps.append("expected_capture_id_mismatch")
    if (
        execution_scope == "production"
        and not source_is_live
        and "live_rtsp_source_required_for_production" not in top_gaps
    ):
        top_gaps.append("live_rtsp_source_required_for_production")
    top_reasons = _unique(
        [reason for item in segment_reports for reason in item["reasons"]]
    )
    production_allowed = bool(
        segment_reports
        and timeline_ok
        and all(item["production_allowed"] for item in segment_reports)
    )
    contract_pass = bool(
        segment_reports
        and fixture_contract
        and timeline_ok
        and all(item["decision"] == "contract_test_pass" for item in segment_reports)
    )
    decision = (
        "production_pass"
        if production_allowed
        else "contract_test_pass"
        if contract_pass
        else "blocked"
    )
    trust_level = (
        "content_hash_bound"
        if execution_scope == "production"
        and raw_content_bound
        and semantic_reports_bound
        and trusted_capture_id == capture_id
        else "insufficient"
    )
    return {
        "decision": decision,
        "production_allowed": production_allowed,
        "source_kind": source_kind,
        "execution_scope": execution_scope,
        "contract_test": contract_test,
        "capture_id": capture_id,
        "expected_capture_id": trusted_capture_id,
        "source_media_sha256": source_media_sha256,
        "trust_level": trust_level,
        "quality_policy": dict(ASR_QUALITY_POLICY),
        "asr_quality_audit": asr_quality_audit,
        "asr_quality_reasons": asr_quality_reasons,
        "claimed_quality_reasons": (
            asr_quality_audit.get("claimed_quality_reasons", [])
            if isinstance(asr_quality_audit, dict)
            else []
        ),
        "recomputed_quality_reasons": (
            asr_quality_audit.get("recomputed_quality_reasons", [])
            if isinstance(asr_quality_audit, dict)
            else []
        ),
        "audio_state": audio_state,
        "reasons": top_reasons,
        "evidence_gaps": top_gaps,
        "segments": segment_reports,
    }


def _read_json(path: str) -> dict[str, Any]:
    def reject_nonstandard_constant(constant: str) -> None:
        raise ValueError(f"non-standard JSON constant is forbidden: {constant}")

    value = json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=reject_nonstandard_constant,
    )
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _same_path(left: Path, right: Path) -> bool:
    try:
        if left.exists() and right.exists() and left.samefile(right):
            return True
    except OSError:
        pass
    return left.resolve(strict=False) == right.resolve(strict=False)


def _atomic_write_json(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            temporary_path = Path(handle.name)
        temporary_path.replace(output)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _input_error_report(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "input_error",
        "errors": [{"code": code, "message": message}],
    }


def _write_cli_input_error(
    output: Path, *, code: str, message: str
) -> int:
    report = _input_error_report(code, message)
    try:
        _atomic_write_json(output, report)
    except (OSError, TypeError, ValueError) as exc:
        print(f"input error: {message}; output error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate time-aligned semantic evidence with a conservative gate."
    )
    parser.add_argument("--timeline-report", required=True)
    parser.add_argument("--audio-inventory", required=True)
    parser.add_argument("--asr-results")
    parser.add_argument("--vlm-results")
    parser.add_argument("--ocr-report")
    parser.add_argument(
        "--execution-scope",
        choices=sorted(VALID_EXECUTION_SCOPES),
        default="production",
    )
    parser.add_argument("--contract-test", action="store_true")
    parser.add_argument("--expected-capture-id")
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)
    input_paths = [
        Path(value)
        for value in [
            args.timeline_report,
            args.audio_inventory,
            args.asr_results,
            args.vlm_results,
            args.ocr_report,
        ]
        if value
    ]
    if any(_same_path(output, input_path) for input_path in input_paths):
        print("input error: --output must not overwrite an input file", file=sys.stderr)
        return 2
    if (
        args.execution_scope == "production"
        and _capture_id(args.expected_capture_id) is None
    ):
        return _write_cli_input_error(
            output,
            code="expected_capture_id_required",
            message="--expected-capture-id is required for production",
        )

    try:
        report = evaluate_evidence(
            _read_json(args.timeline_report),
            _read_json(args.audio_inventory),
            asr_results=_read_json(args.asr_results) if args.asr_results else None,
            vlm_results=_read_json(args.vlm_results) if args.vlm_results else None,
            ocr_report=_read_json(args.ocr_report) if args.ocr_report else None,
            execution_scope=args.execution_scope,
            contract_test=args.contract_test,
            expected_capture_id=args.expected_capture_id,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return _write_cli_input_error(
            output,
            code="input_read_or_validation_error",
            message=str(exc),
        )

    try:
        _atomic_write_json(output, report)
    except (OSError, TypeError, ValueError) as exc:
        print(f"output error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["decision"] != "blocked" else 3


if __name__ == "__main__":
    raise SystemExit(main())
