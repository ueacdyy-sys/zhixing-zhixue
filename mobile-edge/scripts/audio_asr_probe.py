"""Probe captured media audio and align ASR evidence to visual timeline segments."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import wave
from array import array
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


DEFAULT_MIN_TEXT_COVERAGE_RATIO = 0.8
DEFAULT_MIN_MEAN_AVG_LOGPROB = -0.6
DEFAULT_MAX_NO_SPEECH_PROB = 0.6


class AsrCheckpointValidationError(ValueError):
    def __init__(self, field_name: str, *, segment_id: int | str | None = None):
        super().__init__(f"invalid ASR checkpoint field: {field_name}")
        self.field_name = field_name
        self.segment_id = segment_id


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_quality_thresholds(
    *,
    min_text_coverage_ratio: float,
    min_mean_avg_logprob: float,
    max_no_speech_prob: float,
) -> None:
    if not _is_finite_number(min_text_coverage_ratio) or not (
        0.0 <= min_text_coverage_ratio <= 1.0
    ):
        raise ValueError("min_text_coverage_ratio must be finite and between 0 and 1")
    if not _is_finite_number(min_mean_avg_logprob) or min_mean_avg_logprob > 0.0:
        raise ValueError("min_mean_avg_logprob must be finite and <= 0")
    if not _is_finite_number(max_no_speech_prob) or not (
        0.0 <= max_no_speech_prob <= 1.0
    ):
        raise ValueError("max_no_speech_prob must be finite and between 0 and 1")


def _quality_values(segment: Any) -> tuple[float, float] | None:
    if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
        return None
    avg_logprob = segment.get("avg_logprob")
    no_speech_prob = segment.get("no_speech_prob")
    if not _is_finite_number(avg_logprob) or float(avg_logprob) > 0.0:
        return None
    if not _is_finite_number(no_speech_prob) or not (
        0.0 <= float(no_speech_prob) <= 1.0
    ):
        return None
    return float(avg_logprob), float(no_speech_prob)


def _effective_max_end_s(
    *,
    max_end_s: float | None,
    audio_duration_s: float | None,
    time_tolerance_s: float,
) -> float | None:
    if not _is_finite_number(time_tolerance_s) or time_tolerance_s < 0.0:
        raise ValueError("time_tolerance_s must be finite and >= 0")
    bounds = []
    for field_name, value in (
        ("max_end_s", max_end_s),
        ("audio_duration_s", audio_duration_s),
    ):
        if value is None:
            continue
        if not _is_finite_number(value) or float(value) < 0.0:
            raise ValueError(f"{field_name} must be finite and >= 0")
        bounds.append(float(value))
    return min(bounds) if bounds else None


def _raw_segment_time_is_valid(
    segment: Any,
    *,
    effective_max_end_s: float | None,
    time_tolerance_s: float,
) -> bool:
    if not isinstance(segment, dict):
        return False
    start_s = segment.get("start_s")
    end_s = segment.get("end_s")
    if not _is_finite_number(start_s) or not _is_finite_number(end_s):
        return False
    start_s = float(start_s)
    end_s = float(end_s)
    if start_s < 0.0 or start_s >= end_s:
        return False
    return effective_max_end_s is None or end_s <= effective_max_end_s + time_tolerance_s


def _segment_identity(segment: Any, fallback_index: int) -> int | str:
    if isinstance(segment, dict):
        segment_id = segment.get("segment_id")
        if isinstance(segment_id, (int, str)) and not isinstance(segment_id, bool):
            return segment_id
    return fallback_index


def _validated_timeline_segments(timeline: Any) -> list[dict[str, Any]]:
    if not isinstance(timeline, dict):
        raise ValueError("timeline must be an object")
    segments = timeline.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("timeline.segments must be a non-empty array")
    previous_end = 0.0
    for position, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise ValueError("each timeline segment must be an object")
        segment_index = segment.get("segment_index")
        if (
            not isinstance(segment_index, int)
            or isinstance(segment_index, bool)
            or segment_index != position
        ):
            raise ValueError("timeline segment_index must be contiguous and 1-based")
        start_s = segment.get("start_s")
        end_s = segment.get("end_s")
        if not _is_finite_number(start_s) or not _is_finite_number(end_s):
            raise ValueError("timeline segment times must be finite numbers")
        start_s = float(start_s)
        end_s = float(end_s)
        if start_s < 0.0 or start_s >= end_s:
            raise ValueError("timeline segments require 0 <= start_s < end_s")
        if position > 1 and start_s < previous_end:
            raise ValueError("timeline segments must be ordered and non-overlapping")
        previous_end = end_s
    return segments


def _validate_asr_checkpoint_payload(asr: dict[str, Any]) -> None:
    if not isinstance(asr, dict):
        raise AsrCheckpointValidationError("asr")
    for field_name in ("status", "model_id", "device", "compute_type", "text"):
        if not isinstance(asr.get(field_name), str):
            raise AsrCheckpointValidationError(field_name)
    language = asr.get("language")
    if language is not None and not isinstance(language, str):
        raise AsrCheckpointValidationError("language")

    language_probability = asr.get("language_probability")
    if not _is_finite_number(language_probability) or not (
        0.0 <= float(language_probability) <= 1.0
    ):
        raise AsrCheckpointValidationError("language_probability")
    for field_name in ("audio_duration_s", "total_wall_s"):
        value = asr.get(field_name)
        if not _is_finite_number(value) or float(value) < 0.0:
            raise AsrCheckpointValidationError(field_name)
    realtime_factor = asr.get("realtime_factor")
    if realtime_factor is not None and (
        not _is_finite_number(realtime_factor) or float(realtime_factor) < 0.0
    ):
        raise AsrCheckpointValidationError("realtime_factor")

    raw_segments = asr.get("raw_asr_segments")
    if not isinstance(raw_segments, list):
        raise AsrCheckpointValidationError("raw_asr_segments")
    for fallback_index, segment in enumerate(raw_segments):
        segment_id = _segment_identity(segment, fallback_index)
        if not isinstance(segment, dict):
            raise AsrCheckpointValidationError(
                "raw_asr_segment", segment_id=segment_id
            )
        for field_name in ("text", "model_id", "source_media_sha256"):
            if not isinstance(segment.get(field_name), str):
                raise AsrCheckpointValidationError(
                    field_name, segment_id=segment_id
                )
        for field_name in ("start_s", "end_s", "avg_logprob", "no_speech_prob", "compression_ratio"):
            if not _is_finite_number(segment.get(field_name)):
                raise AsrCheckpointValidationError(
                    field_name, segment_id=segment_id
                )
        start_s = float(segment["start_s"])
        end_s = float(segment["end_s"])
        if start_s < 0.0 or start_s >= end_s:
            raise AsrCheckpointValidationError("start_s", segment_id=segment_id)
        if float(segment["avg_logprob"]) > 0.0:
            raise AsrCheckpointValidationError(
                "avg_logprob", segment_id=segment_id
            )
        no_speech_prob = float(segment["no_speech_prob"])
        if not 0.0 <= no_speech_prob <= 1.0:
            raise AsrCheckpointValidationError(
                "no_speech_prob", segment_id=segment_id
            )
        evidence_refs = segment.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not all(
            isinstance(ref, str) for ref in evidence_refs
        ):
            raise AsrCheckpointValidationError(
                "evidence_refs", segment_id=segment_id
            )


def probe_audio_stream(media_path: Path, *, ffprobe: str = "ffprobe") -> dict[str, Any]:
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        evidence = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"ffprobe failed ({completed.returncode}): {evidence}")
    payload = json.loads(completed.stdout)
    audio_streams = [
        stream
        for stream in payload.get("streams", [])
        if stream.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise RuntimeError("media contains no audio stream")
    stream = audio_streams[0]
    format_data = payload.get("format") or {}
    duration = format_data.get("duration") or stream.get("duration")
    return {
        "stream_index": int(stream["index"]),
        "codec_name": str(stream.get("codec_name") or ""),
        "sample_rate_hz": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "channel_layout": str(stream.get("channel_layout") or ""),
        "duration_s": float(duration or 0.0),
        "ffprobe_audio_stream": stream,
        "ffprobe_format": format_data,
    }


def extract_wav_16k_mono(
    media_path: Path, wav_path: Path, *, ffmpeg: str = "ffmpeg"
) -> Path:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media_path),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(wav_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0 or not wav_path.is_file() or wav_path.stat().st_size == 0:
        evidence = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"ffmpeg audio extraction failed ({completed.returncode}): {evidence}")
    return wav_path


def _dbfs(linear: float) -> float | None:
    return 20.0 * math.log10(linear) if linear > 0 else None


def analyze_wav_signal(
    wav_path: Path, *, silence_threshold_dbfs: float = -40.0, frame_ms: int = 100
) -> dict[str, Any]:
    with wave.open(str(wav_path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        raw = wav_file.readframes(frame_count)
    if channels != 1 or sample_width != 2 or sample_rate != 16000:
        raise ValueError("expected PCM signed 16-bit, 16 kHz, mono WAV")
    samples = array("h")
    samples.frombytes(raw)
    if not samples:
        return {
            "sample_rate_hz": sample_rate,
            "channels": channels,
            "sample_count": 0,
            "duration_s": 0.0,
            "rms_linear": 0.0,
            "rms_dbfs": None,
            "peak_linear": 0.0,
            "peak_dbfs": None,
            "silence_threshold_dbfs": silence_threshold_dbfs,
            "silence_ratio": 1.0,
            "non_silent_frame_count": 0,
            "analysis_frame_count": 0,
            "has_non_silent_audio": False,
        }
    scale = 32768.0
    rms_linear = math.sqrt(sum(value * value for value in samples) / len(samples)) / scale
    peak_linear = max(abs(value) for value in samples) / scale
    frame_samples = max(1, int(sample_rate * frame_ms / 1000))
    frame_levels = []
    for offset in range(0, len(samples), frame_samples):
        frame = samples[offset : offset + frame_samples]
        frame_rms = math.sqrt(sum(value * value for value in frame) / len(frame)) / scale
        frame_levels.append(_dbfs(frame_rms))
    non_silent = sum(
        1
        for level in frame_levels
        if level is not None and level > silence_threshold_dbfs
    )
    return {
        "sample_rate_hz": sample_rate,
        "channels": channels,
        "sample_count": len(samples),
        "duration_s": len(samples) / sample_rate,
        "rms_linear": rms_linear,
        "rms_dbfs": _dbfs(rms_linear),
        "peak_linear": peak_linear,
        "peak_dbfs": _dbfs(peak_linear),
        "silence_threshold_dbfs": silence_threshold_dbfs,
        "silence_ratio": 1.0 - non_silent / len(frame_levels),
        "non_silent_frame_count": non_silent,
        "analysis_frame_count": len(frame_levels),
        "has_non_silent_audio": non_silent > 0,
    }


def summarize_asr_quality(
    raw_asr_segments: list[dict[str, Any]],
    *,
    min_text_coverage_ratio: float = DEFAULT_MIN_TEXT_COVERAGE_RATIO,
    min_mean_avg_logprob: float = DEFAULT_MIN_MEAN_AVG_LOGPROB,
    max_no_speech_prob: float = DEFAULT_MAX_NO_SPEECH_PROB,
    max_end_s: float | None = None,
    audio_duration_s: float | None = None,
    time_tolerance_s: float = 0.05,
) -> dict[str, Any]:
    """Recompute a JSON-serializable quality gate from stored raw ASR segments."""
    _validate_quality_thresholds(
        min_text_coverage_ratio=min_text_coverage_ratio,
        min_mean_avg_logprob=min_mean_avg_logprob,
        max_no_speech_prob=max_no_speech_prob,
    )
    if not isinstance(raw_asr_segments, list):
        raise ValueError("raw_asr_segments must be an array")
    effective_max_end_s = _effective_max_end_s(
        max_end_s=max_end_s,
        audio_duration_s=audio_duration_s,
        time_tolerance_s=time_tolerance_s,
    )

    valid_segments: list[tuple[dict[str, Any], float, float]] = []
    invalid_field_ids: list[int | str] = []
    invalid_time_ids: list[int | str] = []
    invalid_segment_ids: list[int | str] = []
    for fallback_index, segment in enumerate(raw_asr_segments):
        segment_id = _segment_identity(segment, fallback_index)
        quality_values = _quality_values(segment)
        if quality_values is None:
            invalid_field_ids.append(segment_id)
        time_is_valid = _raw_segment_time_is_valid(
            segment,
            effective_max_end_s=effective_max_end_s,
            time_tolerance_s=time_tolerance_s,
        )
        if not time_is_valid:
            invalid_time_ids.append(segment_id)
        if quality_values is None or not time_is_valid:
            invalid_segment_ids.append(segment_id)
            continue
        avg_logprob, no_speech_prob = quality_values
        valid_segments.append(
            (segment, avg_logprob, no_speech_prob)
        )

    avg_logprobs = [item[1] for item in valid_segments]
    no_speech_probs = [item[2] for item in valid_segments]
    speech_segments = [
        item for item in valid_segments if item[2] <= max_no_speech_prob
    ]
    transcribed_segments = [
        item for item in speech_segments if str(item[0].get("text") or "").strip()
    ]
    mean_avg_logprob = (
        sum(avg_logprobs) / len(avg_logprobs) if avg_logprobs else None
    )
    mean_no_speech_prob = (
        sum(no_speech_probs) / len(no_speech_probs) if no_speech_probs else None
    )
    maximum_no_speech_prob = max(no_speech_probs) if no_speech_probs else None
    nonempty_emitted_segment_ratio = (
        len(transcribed_segments) / len(speech_segments) if speech_segments else 0.0
    )

    reasons = []
    if invalid_field_ids:
        reasons.append("missing_required_quality_fields")
    if invalid_time_ids:
        reasons.append("raw_segment_time_out_of_bounds")
    if not speech_segments:
        reasons.append("no_valid_speech_segments")
    elif nonempty_emitted_segment_ratio < min_text_coverage_ratio:
        reasons.append("text_coverage_below_threshold")
    if mean_avg_logprob is not None and mean_avg_logprob < min_mean_avg_logprob:
        reasons.append("mean_avg_logprob_below_threshold")
    if (
        maximum_no_speech_prob is not None
        and maximum_no_speech_prob > max_no_speech_prob
    ):
        reasons.append("max_no_speech_prob_above_threshold")

    return {
        "quality_status": "fail" if reasons else "pass",
        "quality_reasons": reasons,
        "segment_count": len(raw_asr_segments),
        "valid_quality_segment_count": len(valid_segments),
        "speech_segment_count": len(speech_segments),
        "transcribed_segment_count": len(transcribed_segments),
        "mean_avg_logprob": mean_avg_logprob,
        "mean_no_speech_prob": mean_no_speech_prob,
        "max_no_speech_prob": maximum_no_speech_prob,
        "nonempty_emitted_segment_ratio": nonempty_emitted_segment_ratio,
        "text_coverage_ratio": nonempty_emitted_segment_ratio,
        "invalid_quality_segment_ids": invalid_segment_ids,
        "time_audit": {
            "effective_max_end_s": effective_max_end_s,
            "time_tolerance_s": time_tolerance_s,
            "out_of_bounds_segment_ids": invalid_time_ids,
        },
        "metric_semantics": {
            "mean_avg_logprob": (
                "unweighted_arithmetic_mean_over_valid_emitted_asr_segments;"
                "not_calibrated_confidence"
            ),
            "mean_no_speech_prob": (
                "unweighted_arithmetic_mean_over_valid_emitted_asr_segments"
            ),
            "max_no_speech_prob": "maximum_over_valid_emitted_asr_segments",
            "nonempty_emitted_segment_ratio": (
                "nonempty_text_emitted_segments_divided_by_emitted_segments_"
                "classified_as_speech;not_audio_time_coverage"
            ),
            "text_coverage_ratio": (
                "deprecated_alias_of_nonempty_emitted_segment_ratio"
            ),
        },
        "quality_thresholds": {
            "min_text_coverage_ratio": min_text_coverage_ratio,
            "min_mean_avg_logprob": min_mean_avg_logprob,
            "max_no_speech_prob": max_no_speech_prob,
        },
    }


def align_asr_to_timeline(
    raw_asr_segments: list[dict[str, Any]],
    timeline: dict[str, Any],
    *,
    model_id: str,
    source_media_sha256: str,
    min_text_coverage_ratio: float = DEFAULT_MIN_TEXT_COVERAGE_RATIO,
    min_mean_avg_logprob: float = DEFAULT_MIN_MEAN_AVG_LOGPROB,
    max_no_speech_prob: float = DEFAULT_MAX_NO_SPEECH_PROB,
    max_end_s: float | None = None,
    audio_duration_s: float | None = None,
    time_tolerance_s: float = 0.05,
) -> dict[str, Any]:
    timeline_segments = _validated_timeline_segments(timeline)
    effective_max_end_s = _effective_max_end_s(
        max_end_s=max_end_s,
        audio_duration_s=audio_duration_s,
        time_tolerance_s=time_tolerance_s,
    )
    capture_id = timeline.get("capture_id")
    if not isinstance(capture_id, str) or not capture_id.strip():
        capture_id = None
        provenance_status = "unbound_timeline_capture_id_missing"
    else:
        provenance_status = "bound_to_timeline_capture_id"
    overall_quality = summarize_asr_quality(
        raw_asr_segments,
        min_text_coverage_ratio=min_text_coverage_ratio,
        min_mean_avg_logprob=min_mean_avg_logprob,
        max_no_speech_prob=max_no_speech_prob,
        max_end_s=max_end_s,
        audio_duration_s=audio_duration_s,
        time_tolerance_s=time_tolerance_s,
    )
    assignments: dict[int, list[tuple[int, dict[str, Any], float, float]]] = {
        int(segment["segment_index"]): [] for segment in timeline_segments
    }
    unassigned_raw_segment_ids: list[int | str] = []
    for raw_index, raw in enumerate(raw_asr_segments):
        if not isinstance(raw, dict):
            raise ValueError("each raw ASR segment must be an object")
        raw_start = raw.get("start_s")
        raw_end = raw.get("end_s")
        if not _is_finite_number(raw_start) or not _is_finite_number(raw_end):
            raise ValueError("raw ASR segment times must be finite numbers")
        raw_start = float(raw_start)
        raw_end = float(raw_end)
        if raw_start < 0.0 or raw_start >= raw_end:
            raise ValueError("raw ASR segments require 0 <= start_s < end_s")
        if not _raw_segment_time_is_valid(
            raw,
            effective_max_end_s=effective_max_end_s,
            time_tolerance_s=time_tolerance_s,
        ):
            unassigned_raw_segment_ids.append(
                _segment_identity(raw, raw_index)
            )
            continue
        candidates = []
        for timeline_segment in timeline_segments:
            overlap_s = min(raw_end, float(timeline_segment["end_s"])) - max(
                raw_start, float(timeline_segment["start_s"])
            )
            if overlap_s > 0.0:
                candidates.append(
                    (overlap_s, int(timeline_segment["segment_index"]))
                )
        if candidates:
            _, selected_index = max(candidates, key=lambda item: (item[0], -item[1]))
            assignments[selected_index].append(
                (raw_index, raw, raw_start, raw_end)
            )
        else:
            unassigned_raw_segment_ids.append(
                _segment_identity(raw, raw_index)
            )

    results = []
    for timeline_segment in timeline_segments:
        segment_index = int(timeline_segment["segment_index"])
        segment_start = float(timeline_segment["start_s"])
        segment_end = float(timeline_segment["end_s"])
        overlapping = []
        assigned = assignments[segment_index]
        quality_overlapping = [item[1] for item in assigned]
        for raw_index, raw, raw_start, raw_end in assigned:
            quality_values = _quality_values(raw)
            text = raw["text"].strip() if quality_values is not None else ""
            if text:
                raw_refs = [
                    str(ref)
                    for ref in raw.get("evidence_refs") or []
                    if str(ref).strip()
                ]
                if not raw_refs:
                    raw_refs = [
                        f"raw_asr_segment:{raw.get('segment_id', raw_index)}"
                    ]
                overlapping.append((raw_index, raw_start, raw_end, text, raw_refs))
        evidence_refs = [
            f"source_media_sha256:{source_media_sha256}",
            *[
                f"timeline_evidence:{segment_index}:{evidence_file}"
                for evidence_file in timeline_segment.get("evidence_files") or []
                if str(evidence_file).strip()
            ],
            *[
                ref
                for _, _, _, _, raw_refs in overlapping
                for ref in raw_refs
            ],
        ]
        if overlapping:
            start_s = max(segment_start, min(item[1] for item in overlapping))
            end_s = min(segment_end, max(item[2] for item in overlapping))
            text = " ".join(item[3] for item in overlapping)
            status = "success"
        else:
            start_s = segment_start
            end_s = segment_end
            text = ""
            status = "no_speech"
        segment_quality = summarize_asr_quality(
            quality_overlapping,
            min_text_coverage_ratio=min_text_coverage_ratio,
            min_mean_avg_logprob=min_mean_avg_logprob,
            max_no_speech_prob=max_no_speech_prob,
            max_end_s=max_end_s,
            audio_duration_s=audio_duration_s,
            time_tolerance_s=time_tolerance_s,
        )
        results.append(
            {
                "capture_id": capture_id,
                "segment_index": segment_index,
                "status": status,
                "text": text,
                "start_s": start_s,
                "end_s": end_s,
                "model_id": model_id,
                "evidence_refs": evidence_refs,
                "source_media_sha256": source_media_sha256,
                "provenance_status": provenance_status,
                "quality_status": segment_quality["quality_status"],
                "quality_reasons": segment_quality["quality_reasons"],
                "quality_summary": segment_quality,
            }
        )
    if any(result["quality_status"] == "fail" for result in results):
        if "timeline_segment_quality_failed" not in overall_quality["quality_reasons"]:
            overall_quality["quality_reasons"].append(
                "timeline_segment_quality_failed"
            )
        overall_quality["quality_status"] = "fail"
    if unassigned_raw_segment_ids:
        if "raw_segments_unaligned_to_timeline" not in overall_quality["quality_reasons"]:
            overall_quality["quality_reasons"].append(
                "raw_segments_unaligned_to_timeline"
            )
        overall_quality["quality_status"] = "fail"
    alignment_summary = {
        "raw_segment_count": len(raw_asr_segments),
        "assigned_raw_segment_count": sum(len(items) for items in assignments.values()),
        "unassigned_raw_segment_ids": unassigned_raw_segment_ids,
    }
    return {
        "capture_id": capture_id,
        "provenance_status": provenance_status,
        "quality_status": overall_quality["quality_status"],
        "quality_reasons": overall_quality["quality_reasons"],
        "quality_summary": overall_quality,
        "alignment_summary": alignment_summary,
        "results": results,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def transcribe_with_faster_whisper(
    wav_path: Path,
    *,
    model_id: str,
    source_media_sha256: str,
    device: str = "cpu",
    compute_type: str = "int8",
    model_factory: Callable[..., Any] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    if model_factory is None:
        from faster_whisper import WhisperModel

        model_factory = WhisperModel
    started = clock()
    model = model_factory(model_id, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        str(wav_path),
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    raw_segments = []
    for fallback_index, segment in enumerate(segments):
        segment_id = int(getattr(segment, "id", fallback_index))
        raw_segments.append(
            {
                "segment_id": segment_id,
                "start_s": float(segment.start),
                "end_s": float(segment.end),
                "text": str(segment.text).strip(),
                "avg_logprob": float(segment.avg_logprob),
                "no_speech_prob": float(segment.no_speech_prob),
                "compression_ratio": float(segment.compression_ratio),
                "model_id": model_id,
                "evidence_refs": [f"raw_asr_segment:{segment_id}"],
                "source_media_sha256": source_media_sha256,
            }
        )
    total_wall_s = clock() - started
    audio_duration_s = float(getattr(info, "duration", 0.0) or 0.0)
    return {
        "status": "success",
        "model_id": model_id,
        "device": device,
        "compute_type": compute_type,
        "language": getattr(info, "language", None),
        "language_probability": float(
            getattr(info, "language_probability", 0.0) or 0.0
        ),
        "audio_duration_s": audio_duration_s,
        "total_wall_s": total_wall_s,
        "realtime_factor": total_wall_s / audio_duration_s
        if audio_duration_s > 0
        else None,
        "text": " ".join(
            segment["text"] for segment in raw_segments if segment["text"]
        ),
        "raw_asr_segments": raw_segments,
    }


def _cache_path_for_model(model_id: str) -> Path | None:
    model_path = Path(model_id).expanduser()
    if model_path.exists():
        return model_path.resolve()
    aliases = {
        "tiny": "Systran/faster-whisper-tiny",
        "base": "Systran/faster-whisper-base",
        "small": "Systran/faster-whisper-small",
        "medium": "Systran/faster-whisper-medium",
        "large-v3": "Systran/faster-whisper-large-v3",
    }
    repository = aliases.get(model_id, model_id)
    if "/" not in repository:
        return None
    cache_root = Path(
        os.environ.get(
            "HF_HUB_CACHE",
            Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
            / "hub",
        )
    )
    return cache_root / f"models--{repository.replace('/', '--')}"


def _model_cache_fact(
    model_id: str, *, cache_path: Path | None = None
) -> dict[str, Any]:
    cache_path = cache_path or _cache_path_for_model(model_id)
    directory_present = bool(cache_path and cache_path.is_dir())
    snapshots: list[str] = []
    complete_snapshots: list[str] = []
    if directory_present and cache_path is not None:
        snapshot_root = cache_path / "snapshots"
        candidates = (
            [path for path in snapshot_root.iterdir() if path.is_dir()]
            if snapshot_root.is_dir()
            else [cache_path]
        )
        for candidate in candidates:
            snapshots.append(candidate.name)
            if (candidate / "model.bin").is_file() and (candidate / "config.json").is_file():
                complete_snapshots.append(candidate.name)
    return {
        "model_id": model_id,
        "cache_path": str(cache_path) if cache_path else None,
        "cache_directory_present": directory_present,
        "cache_complete": bool(complete_snapshots),
        "snapshot_ids": sorted(snapshots),
        "complete_snapshot_ids": sorted(complete_snapshots),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    serialized = json.dumps(
        payload, ensure_ascii=False, indent=2, allow_nan=False
    ) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
        raise


def _write_failure_manifest(
    *,
    out_dir: Path,
    stage: str,
    exc: Exception,
    capture_id: str | None,
    source_media_sha256: str,
    audio_evidence_paths: list[Path],
    segment_id: int | str | None = None,
    field_name: str | None = None,
    checkpoint_file: str | None = None,
) -> None:
    _write_json(
        out_dir / "audio_asr_failure.json",
        {
            "schema_version": "audio_asr_failure.v1",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "stage": stage,
            "failed_stage": stage,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "segment_id": segment_id,
            "field_name": field_name,
            "capture_id": capture_id,
            "source_media_sha256": source_media_sha256,
            "audio_evidence_paths": [
                str(path.resolve()) for path in audio_evidence_paths if path.is_file()
            ],
            "checkpoint_file": checkpoint_file,
            "retry_requires_new_out_dir": True,
        },
    )


def run_probe(
    *,
    media_path: Path,
    timeline_path: Path,
    out_dir: Path,
    model_id: str,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    device: str = "cpu",
    compute_type: str = "int8",
    model_factory: Callable[..., Any] | None = None,
    min_text_coverage_ratio: float = DEFAULT_MIN_TEXT_COVERAGE_RATIO,
    min_mean_avg_logprob: float = DEFAULT_MIN_MEAN_AVG_LOGPROB,
    max_no_speech_prob: float = DEFAULT_MAX_NO_SPEECH_PROB,
) -> dict[str, Any]:
    started = time.perf_counter()
    if out_dir.exists():
        raise FileExistsError(f"output directory already exists: {out_dir}")
    _validate_quality_thresholds(
        min_text_coverage_ratio=min_text_coverage_ratio,
        min_mean_avg_logprob=min_mean_avg_logprob,
        max_no_speech_prob=max_no_speech_prob,
    )
    media_path = media_path.resolve()
    timeline_path = timeline_path.resolve()
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    _validated_timeline_segments(timeline)
    source_media_sha256 = sha256_file(media_path)
    out_dir.mkdir(parents=True, exist_ok=False)

    audio_probe = probe_audio_stream(media_path, ffprobe=ffprobe)
    _write_json(out_dir / "ffprobe_audio_stream.json", audio_probe)
    wav_path = extract_wav_16k_mono(
        media_path, out_dir / "audio_16k_mono.wav", ffmpeg=ffmpeg
    )
    audio_signal = analyze_wav_signal(wav_path)
    _write_json(out_dir / "audio_signal_stats.json", audio_signal)

    cache_before = _model_cache_fact(model_id)
    if audio_signal["has_non_silent_audio"]:
        try:
            asr = transcribe_with_faster_whisper(
                wav_path,
                model_id=model_id,
                source_media_sha256=source_media_sha256,
                device=device,
                compute_type=compute_type,
                model_factory=model_factory,
            )
        except Exception as exc:  # Preserve audio evidence even when model load/download fails.
            error_text = f"{type(exc).__name__}: {exc}"
            (out_dir / "asr_error.txt").write_text(error_text + "\n", encoding="utf-8")
            asr = {
                "status": "error",
                "model_id": model_id,
                "device": device,
                "compute_type": compute_type,
                "error": error_text,
                "language": None,
                "text": "",
                "total_wall_s": None,
                "realtime_factor": None,
                "raw_asr_segments": [],
            }
    else:
        asr = {
            "status": "skipped_no_non_silent_audio",
            "model_id": model_id,
            "device": device,
            "compute_type": compute_type,
            "language": None,
            "text": "",
            "total_wall_s": 0.0,
            "realtime_factor": None,
            "raw_asr_segments": [],
        }
    cache_after = _model_cache_fact(model_id)
    model_download = {
        "model_id": model_id,
        "cache_path": cache_after["cache_path"] or cache_before["cache_path"],
        "cache_directory_present_before": cache_before["cache_directory_present"],
        "cache_directory_present_after": cache_after["cache_directory_present"],
        "cache_complete_before": cache_before["cache_complete"],
        "cache_complete_after": cache_after["cache_complete"],
        "downloaded_during_run": (
            not cache_before["cache_complete"] and cache_after["cache_complete"]
        ),
        "snapshot_ids_before": cache_before["snapshot_ids"],
        "snapshot_ids_after": cache_after["snapshot_ids"],
        "complete_snapshot_ids_before": cache_before["complete_snapshot_ids"],
        "complete_snapshot_ids_after": cache_after["complete_snapshot_ids"],
    }

    raw_asr_segments = asr["raw_asr_segments"]
    checkpoint_path: Path | None = None
    manifest_capture_id = timeline.get("capture_id")
    if not isinstance(manifest_capture_id, str) or not manifest_capture_id.strip():
        manifest_capture_id = None
    audio_evidence_paths = [
        wav_path,
        out_dir / "ffprobe_audio_stream.json",
        out_dir / "audio_signal_stats.json",
    ]
    if asr["status"] == "success":
        checkpoint_path = out_dir / "raw_asr_report.json"
        try:
            _validate_asr_checkpoint_payload(asr)
        except AsrCheckpointValidationError as exc:
            _write_failure_manifest(
                out_dir=out_dir,
                stage="checkpoint_validation",
                exc=exc,
                capture_id=manifest_capture_id,
                source_media_sha256=source_media_sha256,
                audio_evidence_paths=audio_evidence_paths,
                segment_id=exc.segment_id,
                field_name=exc.field_name,
            )
            raise
        try:
            _write_json(
                checkpoint_path,
                {
                    "schema_version": "raw_asr_report.v1",
                    "created_at": datetime.now().astimezone().isoformat(
                        timespec="seconds"
                    ),
                    "source_media_sha256": source_media_sha256,
                    "model_id": model_id,
                    "asr": {
                        key: value
                        for key, value in asr.items()
                        if key != "raw_asr_segments"
                    },
                    "raw_asr_segments": raw_asr_segments,
                },
            )
        except Exception as exc:
            _write_failure_manifest(
                out_dir=out_dir,
                stage="checkpoint_serialization",
                exc=exc,
                capture_id=manifest_capture_id,
                source_media_sha256=source_media_sha256,
                audio_evidence_paths=audio_evidence_paths,
                field_name="checkpoint_payload",
            )
            raise
    try:
        alignment_audio_duration_s = (
            asr.get("audio_duration_s") if asr["status"] == "success" else None
        )
        aligned = align_asr_to_timeline(
            raw_asr_segments,
            timeline,
            model_id=model_id,
            source_media_sha256=source_media_sha256,
            min_text_coverage_ratio=min_text_coverage_ratio,
            min_mean_avg_logprob=min_mean_avg_logprob,
            max_no_speech_prob=max_no_speech_prob,
            audio_duration_s=alignment_audio_duration_s,
        )
    except Exception as exc:
        if checkpoint_path is not None:
            _write_failure_manifest(
                out_dir=out_dir,
                stage="alignment",
                exc=exc,
                capture_id=manifest_capture_id,
                source_media_sha256=source_media_sha256,
                audio_evidence_paths=audio_evidence_paths,
                checkpoint_file=checkpoint_path.name,
            )
        raise
    if asr["status"] != "success":
        result_status = (
            "asr_error"
            if asr["status"] == "error"
            else "invalid_audio_no_non_silent_signal"
        )
        for result in aligned["results"]:
            result["status"] = result_status
            result["text"] = ""
            if asr["status"] == "error":
                result["evidence_refs"].append("asr_error:asr_error.txt")

    report = {
        "schema_version": "audio_asr_probe.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "media_path": str(media_path),
        "timeline_path": str(timeline_path),
        "out_dir": str(out_dir.resolve()),
        "source_media_sha256": source_media_sha256,
        "audio_probe": audio_probe,
        "extracted_wav": str(wav_path.resolve()),
        "audio_signal": audio_signal,
        "model_download": model_download,
        "asr": {key: value for key, value in asr.items() if key != "raw_asr_segments"},
        "raw_asr_segments": raw_asr_segments,
        "capture_id": aligned["capture_id"],
        "provenance_status": aligned["provenance_status"],
        "quality_status": aligned["quality_status"],
        "quality_reasons": aligned["quality_reasons"],
        "quality_thresholds": aligned["quality_summary"]["quality_thresholds"],
        "quality_summary": aligned["quality_summary"],
        "alignment_summary": aligned["alignment_summary"],
        "results": aligned["results"],
        "total_wall_s": time.perf_counter() - started,
        "interpretation_note": (
            "ASR text is a model transcription result; this probe does not claim semantic "
            "understanding; provisional_conservative_threshold_needs_labeled_calibration."
        ),
    }
    _write_json(out_dir / "audio_asr_report.json", report)
    return report


def _unique_default_out_dir(root: Path) -> Path:
    stem = f"audio_asr_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    candidate = root / stem
    suffix = 1
    while candidate.exists():
        candidate = root / f"{stem}_{suffix:02d}"
        suffix += 1
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate captured audio, run faster-whisper, and align ASR evidence.",
        epilog="exit 3: ASR pipeline succeeded but the quality gate failed.",
    )
    parser.add_argument("--media", required=True)
    parser.add_argument("--timeline", required=True)
    parser.add_argument("--out-dir")
    parser.add_argument("--model-id", default="Systran/faster-whisper-tiny")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument(
        "--quality-min-text-coverage-ratio",
        type=float,
        default=DEFAULT_MIN_TEXT_COVERAGE_RATIO,
    )
    parser.add_argument(
        "--quality-min-mean-avg-logprob",
        type=float,
        default=DEFAULT_MIN_MEAN_AVG_LOGPROB,
        help=f"default: {DEFAULT_MIN_MEAN_AVG_LOGPROB} (provisional).",
    )
    parser.add_argument(
        "--quality-max-no-speech-prob",
        type=float,
        default=DEFAULT_MAX_NO_SPEECH_PROB,
    )
    args = parser.parse_args(argv)
    media_path = Path(args.media)
    timeline_path = Path(args.timeline)
    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else _unique_default_out_dir(media_path.resolve().parents[1])
    )
    try:
        _validate_quality_thresholds(
            min_text_coverage_ratio=args.quality_min_text_coverage_ratio,
            min_mean_avg_logprob=args.quality_min_mean_avg_logprob,
            max_no_speech_prob=args.quality_max_no_speech_prob,
        )
        report = run_probe(
            media_path=media_path,
            timeline_path=timeline_path,
            out_dir=out_dir,
            model_id=args.model_id,
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
            device=args.device,
            compute_type=args.compute_type,
            min_text_coverage_ratio=args.quality_min_text_coverage_ratio,
            min_mean_avg_logprob=args.quality_min_mean_avg_logprob,
            max_no_speech_prob=args.quality_max_no_speech_prob,
        )
    except (FileExistsError, FileNotFoundError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"audio_asr_probe input/pipeline error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "out_dir": report["out_dir"],
                "audio_has_non_silent": report["audio_signal"]["has_non_silent_audio"],
                "asr_status": report["asr"]["status"],
                "language": report["asr"].get("language"),
                "text": report["asr"].get("text"),
                "provenance_status": report["provenance_status"],
                "quality_status": report["quality_status"],
                "quality_reasons": report["quality_reasons"],
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )
    if report["asr"]["status"] != "success":
        return 4
    return 0 if report["quality_status"] == "pass" else 3


if __name__ == "__main__":
    raise SystemExit(main())
