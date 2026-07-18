#!/usr/bin/env python3
"""Run and validate the full-video semantic understanding contract.

The semantic main path accepts a canonical continuous video file only. Fast-path
artifacts such as screenshots, keyframes, OCR text, or sampled-frame folders are
not accepted as substitutes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


DEFAULT_MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"
IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".gif",
    ".tif",
    ".tiff",
}
VIDEO_SUFFIXES = {".mkv", ".mp4", ".mov", ".webm", ".avi", ".m4v"}
FRAME_DIR_NAMES = {"keyframes", "frames", "evidence_frames", "sampled_frames"}


class FullVideoInputError(ValueError):
    """Raised when the requested input would violate the full-video contract."""

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
        raise FullVideoInputError("json_object_required", f"expected object JSON: {path}")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
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


def _same_path(left: Path, right: Path) -> bool:
    try:
        if left.exists() and right.exists() and left.samefile(right):
            return True
    except OSError:
        pass
    return left.resolve(strict=False) == right.resolve(strict=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_full_video_path(video_path: Path) -> Path:
    if video_path.is_dir():
        raise FullVideoInputError(
            "full_video_file_required",
            "semantic main input must be one canonical video file, not a directory",
        )
    if video_path.suffix.lower() in IMAGE_SUFFIXES:
        raise FullVideoInputError(
            "sampled_frame_input_forbidden",
            "image files cannot be used as the semantic main input",
        )
    if any(part.lower() in FRAME_DIR_NAMES for part in video_path.parts):
        raise FullVideoInputError(
            "fast_path_frame_artifact_forbidden",
            "keyframe or evidence-frame artifacts cannot be used as the semantic main input",
        )
    if video_path.suffix.lower() not in VIDEO_SUFFIXES:
        raise FullVideoInputError(
            "video_extension_required",
            f"expected a video file extension, got {video_path.suffix or '<none>'}",
        )
    if not video_path.is_file():
        raise FullVideoInputError("video_file_missing", f"video file missing: {video_path}")
    if video_path.stat().st_size <= 0:
        raise FullVideoInputError("video_file_empty", f"video file is empty: {video_path}")
    return video_path.resolve()


def _ffprobe(media_path: Path, *, ffprobe: str) -> dict[str, Any]:
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
        raise FullVideoInputError(
            "ffprobe_failed",
            f"ffprobe failed ({completed.returncode}): {evidence}",
        )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise FullVideoInputError("ffprobe_json_invalid", "ffprobe did not return an object")
    return payload


def summarize_media(
    media_path: Path,
    *,
    ffprobe: str = "ffprobe",
    ffprobe_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = ffprobe_payload if ffprobe_payload is not None else _ffprobe(media_path, ffprobe=ffprobe)
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise FullVideoInputError("ffprobe_streams_missing", "ffprobe streams array missing")
    video_streams = [item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"]
    audio_streams = [item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"]
    if not video_streams:
        raise FullVideoInputError("video_track_missing", "canonical media has no video track")
    if not audio_streams:
        raise FullVideoInputError("audio_track_missing", "positive demo requires same-source audio")
    format_data = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    duration = format_data.get("duration") or video_streams[0].get("duration")
    duration_s = float(duration) if duration is not None else None
    if duration_s is None or not math.isfinite(duration_s) or duration_s <= 0:
        raise FullVideoInputError("media_duration_invalid", "media duration must be positive")
    return {
        "duration_s": duration_s,
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "video_stream": video_streams[0],
        "audio_stream": audio_streams[0],
        "format": format_data,
    }


def _canonical_file_from_manifest(manifest: dict[str, Any]) -> str | None:
    raw = manifest.get("raw_recording")
    if isinstance(raw, dict):
        value = raw.get("canonical_file")
        if isinstance(value, str) and value.strip():
            return value
    return None


def _canonical_file_from_timeline(timeline: dict[str, Any]) -> str | None:
    raw = timeline.get("raw_recording")
    if isinstance(raw, dict):
        for key in ["canonical_file", "file"]:
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def validate_canonical_binding(
    *,
    video_path: Path,
    timeline: dict[str, Any],
    manifest: dict[str, Any],
    media_sha256: str,
) -> str:
    capture_id = timeline.get("capture_id")
    if not isinstance(capture_id, str) or not capture_id.strip():
        raise FullVideoInputError("capture_id_missing", "timeline capture_id is required")
    if manifest.get("capture_id") != capture_id:
        raise FullVideoInputError("capture_id_mismatch", "manifest and timeline capture_id differ")
    if manifest.get("source_kind") != "live_rtsp" or timeline.get("source_kind") != "live_rtsp":
        raise FullVideoInputError(
            "live_rtsp_source_required",
            "production positive loop requires a live_rtsp canonical capture",
        )
    manifest_file = _canonical_file_from_manifest(manifest)
    timeline_file = _canonical_file_from_timeline(timeline)
    if manifest_file is None or timeline_file is None:
        raise FullVideoInputError("canonical_file_missing", "canonical media path missing in manifest/timeline")
    if not _same_path(video_path, Path(manifest_file)) or not _same_path(video_path, Path(timeline_file)):
        raise FullVideoInputError(
            "canonical_video_path_mismatch",
            "video path must match manifest and timeline canonical file",
        )
    raw_manifest = manifest.get("raw_recording")
    raw_timeline = timeline.get("raw_recording")
    manifest_sha = raw_manifest.get("sha256") if isinstance(raw_manifest, dict) else None
    timeline_sha = raw_timeline.get("sha256") if isinstance(raw_timeline, dict) else None
    if manifest_sha != media_sha256 or timeline_sha != media_sha256:
        raise FullVideoInputError("canonical_sha256_mismatch", "computed video SHA does not match manifest/timeline")
    return capture_id


def _timeline_segments(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    segments = timeline.get("segments")
    if not isinstance(segments, list) or not segments:
        raise FullVideoInputError("timeline_segments_missing", "timeline.segments is required")
    clean = []
    for position, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise FullVideoInputError("timeline_segment_invalid", "timeline segment must be an object")
        start_s = segment.get("start_s")
        end_s = segment.get("end_s")
        if (
            not _is_number(start_s)
            or not _is_number(end_s)
            or float(start_s) < 0
            or float(end_s) <= float(start_s)
        ):
            raise FullVideoInputError("timeline_segment_time_invalid", "timeline segment times must be valid")
        segment_index = segment.get("segment_index")
        if segment_index != position:
            raise FullVideoInputError("timeline_segment_index_invalid", "timeline segment indices must be 1-based and contiguous")
        clean.append(segment)
    return clean


def validate_asr_report(
    *,
    asr_report: dict[str, Any],
    capture_id: str,
    media_sha256: str,
    duration_s: float,
) -> list[dict[str, Any]]:
    if asr_report.get("capture_id") != capture_id:
        raise FullVideoInputError("asr_capture_id_mismatch", "ASR report is not bound to the capture_id")
    if asr_report.get("source_media_sha256") != media_sha256:
        raise FullVideoInputError("asr_media_sha256_mismatch", "ASR report is not bound to the media SHA")
    if asr_report.get("quality_status") != "pass":
        raise FullVideoInputError("asr_quality_not_pass", "positive demo requires high-quality ASR")
    results = asr_report.get("results")
    if not isinstance(results, list) or not results:
        raise FullVideoInputError("asr_results_missing", "ASR report requires aligned results")
    clean = []
    for result in results:
        if not isinstance(result, dict):
            raise FullVideoInputError("asr_result_invalid", "ASR result must be an object")
        if result.get("status") != "success":
            raise FullVideoInputError("asr_result_not_success", "all production ASR results must be success")
        start_s = result.get("start_s")
        end_s = result.get("end_s")
        if (
            not _is_number(start_s)
            or not _is_number(end_s)
            or float(start_s) < 0
            or float(end_s) <= float(start_s)
            or float(end_s) > duration_s + 0.25
        ):
            raise FullVideoInputError("asr_result_time_invalid", "ASR result time is outside media bounds")
        if not isinstance(result.get("text"), str) or not result["text"].strip():
            raise FullVideoInputError("asr_text_missing", "ASR result text is required")
        clean.append(result)
    return clean


def _asr_context(asr_results: list[dict[str, Any]], max_chars: int = 4000) -> str:
    lines = []
    for result in asr_results:
        lines.append(
            f"[segment {result.get('segment_index')} {float(result['start_s']):.2f}-{float(result['end_s']):.2f}s] "
            f"{str(result.get('text') or '').strip()}"
        )
    return "\n".join(lines)[:max_chars]


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise FullVideoInputError("vlm_json_object_required", "VLM output must be a JSON object")
    return payload


def run_qwen_full_video(
    *,
    video_path: Path,
    asr_context: str,
    model_id: str,
    fps: float,
    max_pixels: int | None,
    max_new_tokens: int,
) -> dict[str, Any]:
    from qwen_vl_utils import process_vision_info
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    started = time.perf_counter()
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype="auto",
        device_map="auto",
    )
    processor = AutoProcessor.from_pretrained(model_id)
    video_content: dict[str, Any] = {
        "type": "video",
        "video": str(video_path),
        "fps": fps,
    }
    if max_pixels is not None:
        video_content["max_pixels"] = max_pixels
    prompt = (
        "你是学习过程证据分析器。只基于输入的完整连续手机屏幕视频和同源ASR文本，"
        "输出严格JSON，不要Markdown。识别片段级事件、人物/对象、概念、表达、现象、"
        "不确定性和证据时间范围。禁止出题。JSON格式："
        "{\"events\":[{\"segment_index\":1,\"start_s\":0.0,\"end_s\":1.0,"
        "\"summary\":\"...\",\"concepts\":[\"...\"],\"expressions\":[\"...\"],"
        "\"uncertainty\":\"low|medium|high\",\"evidence_refs\":[\"video:0.0-1.0\","
        "\"asr:segment-1\"]}],\"global_concepts\":[\"...\"]}。"
        f"\n\nASR时间文本：\n{asr_context}"
    )
    messages = [
        {
            "role": "user",
            "content": [
                video_content,
                {"type": "text", "text": prompt},
            ],
        }
    ]
    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )
    inputs = inputs.to(model.device)
    generated_ids = model.generate(**inputs, max_new_tokens=max_new_tokens)
    generated_ids_trimmed = [
        output_ids[len(input_ids) :]
        for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
    ]
    output_text = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]
    return {
        "status": "success",
        "raw_text": output_text,
        "parsed_json": _extract_json_object(output_text),
        "wall_s": time.perf_counter() - started,
    }


def _segment_index_for_range(
    event: dict[str, Any],
    timeline_segments: list[dict[str, Any]],
) -> int | None:
    explicit = event.get("segment_index")
    if isinstance(explicit, int) and not isinstance(explicit, bool):
        return explicit
    start_s = event.get("start_s")
    end_s = event.get("end_s")
    if not _is_number(start_s) or not _is_number(end_s):
        return None
    midpoint = (float(start_s) + float(end_s)) / 2
    for segment in timeline_segments:
        if float(segment["start_s"]) <= midpoint <= float(segment["end_s"]):
            return int(segment["segment_index"])
    return None


def normalize_vlm_events(
    *,
    vlm_payload: dict[str, Any],
    capture_id: str,
    media_sha256: str,
    timeline_segments: list[dict[str, Any]],
    duration_s: float,
    model_id: str,
) -> list[dict[str, Any]]:
    events = vlm_payload.get("events")
    if not isinstance(events, list) or not events:
        raise FullVideoInputError("vlm_events_missing", "VLM output must contain events")
    normalized = []
    for position, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise FullVideoInputError("vlm_event_invalid", "VLM event must be an object")
        start_s = event.get("start_s")
        end_s = event.get("end_s")
        if (
            not _is_number(start_s)
            or not _is_number(end_s)
            or float(start_s) < 0
            or float(end_s) <= float(start_s)
            or float(end_s) > duration_s + 0.25
        ):
            raise FullVideoInputError("vlm_event_time_invalid", "VLM event time must be inside media duration")
        summary = str(event.get("summary") or event.get("text") or "").strip()
        if not summary:
            raise FullVideoInputError("vlm_event_summary_missing", "VLM event summary is required")
        segment_index = _segment_index_for_range(event, timeline_segments)
        if segment_index is None:
            raise FullVideoInputError("vlm_event_segment_missing", "VLM event must map to a timeline segment")
        refs = event.get("evidence_refs")
        if not isinstance(refs, list):
            refs = []
        refs = [str(ref).strip() for ref in refs if str(ref).strip()]
        if not refs:
            refs = [
                f"video:{float(start_s):.2f}-{float(end_s):.2f}",
                f"vlm_event:{position}",
            ]
        normalized.append(
            {
                "status": "success",
                "capture_id": capture_id,
                "source_media_sha256": media_sha256,
                "segment_index": segment_index,
                "start_s": float(start_s),
                "end_s": float(end_s),
                "summary": summary,
                "text": summary,
                "concepts": [
                    str(item).strip()
                    for item in event.get("concepts", [])
                    if str(item).strip()
                ]
                if isinstance(event.get("concepts"), list)
                else [],
                "expressions": [
                    str(item).strip()
                    for item in event.get("expressions", [])
                    if str(item).strip()
                ]
                if isinstance(event.get("expressions"), list)
                else [],
                "uncertainty": str(event.get("uncertainty") or "unknown"),
                "evidence_refs": refs,
                "model_id": model_id,
            }
        )
    return normalized


def _blocked_report(
    *,
    code: str,
    message: str,
    output_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = {
        "schema_version": "full_video_understanding_report.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "blocked",
        "production_ready": False,
        "blockers": [code],
        "errors": [{"code": code, "message": message}],
        "truth_label": "未满足",
        "results": [],
    }
    if output_context:
        report.update(output_context)
    return report


def build_understanding_report(
    *,
    video_path: Path,
    timeline_path: Path,
    manifest_path: Path,
    asr_report_path: Path,
    model_id: str = DEFAULT_MODEL_ID,
    ffprobe: str = "ffprobe",
    ffprobe_payload: dict[str, Any] | None = None,
    model_output_json: Path | None = None,
    run_model: Callable[..., dict[str, Any]] = run_qwen_full_video,
    fps: float = 1.0,
    max_pixels: int | None = None,
    max_new_tokens: int = 800,
) -> dict[str, Any]:
    video_path = validate_full_video_path(video_path)
    timeline = _read_json(timeline_path)
    manifest = _read_json(manifest_path)
    asr_report = _read_json(asr_report_path)
    media_sha256 = sha256_file(video_path)
    media_summary = summarize_media(video_path, ffprobe=ffprobe, ffprobe_payload=ffprobe_payload)
    capture_id = validate_canonical_binding(
        video_path=video_path,
        timeline=timeline,
        manifest=manifest,
        media_sha256=media_sha256,
    )
    timeline_segments = _timeline_segments(timeline)
    asr_results = validate_asr_report(
        asr_report=asr_report,
        capture_id=capture_id,
        media_sha256=media_sha256,
        duration_s=float(media_summary["duration_s"]),
    )

    context = {
        "capture_id": capture_id,
        "source_media_sha256": media_sha256,
        "media_sha256": media_sha256,
        "input_media_path": str(video_path),
        "input_mode": "canonical_full_video",
        "manifest_path": str(manifest_path.resolve()),
        "timeline_path": str(timeline_path.resolve()),
        "asr_report_path": str(asr_report_path.resolve()),
        "model_id": model_id,
        "media": media_summary,
        "asr_quality_status": asr_report.get("quality_status"),
        "processing_disclosure": {
            "engineering_input": "single canonical continuous video file",
            "forbidden_substitutes": [
                "image_list",
                "sampled_frames",
                "keyframes",
                "ocr_only",
            ],
            "model_internal_video_sampling_fps": fps,
            "max_pixels": max_pixels,
            "max_new_tokens": max_new_tokens,
            "claim_limit": "model may sample internally; this is not a claim of lossless frame-by-frame understanding",
        },
    }

    try:
        if model_output_json is not None:
            vlm_raw = _read_json(model_output_json)
            model_run = {
                "status": "success",
                "raw_text": model_output_json.read_text(encoding="utf-8"),
                "parsed_json": vlm_raw,
                "wall_s": None,
                "source": "external_model_output_json",
            }
        else:
            model_run = run_model(
                video_path=video_path,
                asr_context=_asr_context(asr_results),
                model_id=model_id,
                fps=fps,
                max_pixels=max_pixels,
                max_new_tokens=max_new_tokens,
            )
        vlm_payload = model_run.get("parsed_json")
        if not isinstance(vlm_payload, dict):
            raise FullVideoInputError("vlm_parsed_json_missing", "model did not return parsed JSON")
        results = normalize_vlm_events(
            vlm_payload=vlm_payload,
            capture_id=capture_id,
            media_sha256=media_sha256,
            timeline_segments=timeline_segments,
            duration_s=float(media_summary["duration_s"]),
            model_id=model_id,
        )
    except FullVideoInputError:
        raise
    except Exception as exc:
        return _blocked_report(
            code="vlm_runtime_failed",
            message=f"{type(exc).__name__}: {exc}",
            output_context=context,
        )

    return {
        **context,
        "schema_version": "full_video_understanding_report.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "production_ready",
        "production_ready": True,
        "truth_label": "已实测",
        "blockers": [],
        "vlm": {
            "status": "success",
            "model_id": model_id,
            "wall_s": model_run.get("wall_s"),
            "source": model_run.get("source", "local_qwen_full_video"),
            "raw_text": model_run.get("raw_text"),
        },
        "global_concepts": vlm_payload.get("global_concepts", []),
        "results": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate canonical full video and run full-video VLM understanding."
    )
    parser.add_argument("--video", required=True)
    parser.add_argument("--timeline-report", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--asr-report", required=True)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--model-output-json")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--max-pixels", type=int)
    parser.add_argument("--max-new-tokens", type=int, default=800)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)
    try:
        report = build_understanding_report(
            video_path=Path(args.video),
            timeline_path=Path(args.timeline_report),
            manifest_path=Path(args.manifest),
            asr_report_path=Path(args.asr_report),
            model_id=args.model_id,
            model_output_json=Path(args.model_output_json) if args.model_output_json else None,
            ffprobe=args.ffprobe,
            fps=args.fps,
            max_pixels=args.max_pixels,
            max_new_tokens=args.max_new_tokens,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, FullVideoInputError) as exc:
        code = exc.code if isinstance(exc, FullVideoInputError) else "input_error"
        report = _blocked_report(code=code, message=str(exc))
    try:
        _atomic_write_json(output, report)
    except OSError as exc:
        print(f"output error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report.get("production_ready") else 4


if __name__ == "__main__":
    raise SystemExit(main())
