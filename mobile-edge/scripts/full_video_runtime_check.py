#!/usr/bin/env python3
"""Check the local runtime needed by the full-video positive loop.

This script is deliberately diagnostic only. It does not claim that a demo is
working; it reports whether CUDA, video decoding, ASR, and VLM dependencies are
actually importable and whether declared model caches look usable.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_VLM_MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"
DEFAULT_ASR_MODEL_ID = "Systran/faster-whisper-large-v3-turbo"


def _module_present(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _module_report(module_name: str) -> dict[str, Any]:
    present = _module_present(module_name)
    version = None
    if present:
        try:
            module = __import__(module_name)
            version = getattr(module, "__version__", None)
        except Exception as exc:  # pragma: no cover - defensive diagnostics
            return {
                "module": module_name,
                "present": True,
                "import_error": f"{type(exc).__name__}: {exc}",
            }
    return {
        "module": module_name,
        "present": present,
        "version": version,
    }


def _torch_report() -> dict[str, Any]:
    report = _module_report("torch")
    if not report["present"] or report.get("import_error"):
        report.update(
            {
                "cuda_available": False,
                "device_count": 0,
                "devices": [],
            }
        )
        return report
    import torch

    cuda_available = bool(torch.cuda.is_available())
    devices = []
    if cuda_available:
        for index in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(index)
            devices.append(
                {
                    "index": index,
                    "name": torch.cuda.get_device_name(index),
                    "total_memory_bytes": int(props.total_memory),
                }
            )
    report.update(
        {
            "cuda_available": cuda_available,
            "device_count": int(torch.cuda.device_count()) if cuda_available else 0,
            "devices": devices,
            "cuda_version": getattr(torch.version, "cuda", None),
        }
    )
    return report


def _ffmpeg_report(binary: str) -> dict[str, Any]:
    completed = subprocess.run(
        [binary, "-version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    return {
        "binary": binary,
        "available": completed.returncode == 0,
        "returncode": completed.returncode,
        "version_line": first_line,
        "stderr": completed.stderr.strip(),
    }


def _hf_cache_path(model_id: str) -> Path | None:
    model_path = Path(model_id).expanduser()
    if model_path.exists():
        return model_path.resolve()
    if "/" not in model_id:
        return None
    cache_root = Path(
        os.environ.get(
            "HF_HUB_CACHE",
            Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
            / "hub",
        )
    )
    return cache_root / f"models--{model_id.replace('/', '--')}"


def _snapshot_files(snapshot: Path) -> set[str]:
    try:
        return {item.name for item in snapshot.iterdir() if item.is_file()}
    except OSError:
        return set()


def _model_cache_report(model_id: str, required_any: list[str]) -> dict[str, Any]:
    cache_path = _hf_cache_path(model_id)
    snapshots = []
    complete_snapshots = []
    if cache_path and cache_path.is_dir():
        snapshot_root = cache_path / "snapshots"
        candidates = (
            [path for path in snapshot_root.iterdir() if path.is_dir()]
            if snapshot_root.is_dir()
            else [cache_path]
        )
        for candidate in candidates:
            names = _snapshot_files(candidate)
            snapshots.append(candidate.name)
            if all(any(name.endswith(suffix) for name in names) for suffix in required_any):
                complete_snapshots.append(candidate.name)
    return {
        "model_id": model_id,
        "cache_path": str(cache_path) if cache_path else None,
        "cache_directory_present": bool(cache_path and cache_path.is_dir()),
        "snapshot_ids": sorted(snapshots),
        "complete_snapshot_ids": sorted(complete_snapshots),
        "cache_complete": bool(complete_snapshots),
        "required_file_suffixes": required_any,
    }


def build_runtime_report(
    *,
    vlm_model_id: str = DEFAULT_VLM_MODEL_ID,
    asr_model_id: str = DEFAULT_ASR_MODEL_ID,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> dict[str, Any]:
    modules = {
        name: _module_report(name)
        for name in [
            "transformers",
            "accelerate",
            "qwen_vl_utils",
            "av",
            "PIL",
            "faster_whisper",
        ]
    }
    torch_report = _torch_report()
    vlm_cache = _model_cache_report(
        vlm_model_id,
        required_any=["config.json", "model.safetensors.index.json"],
    )
    asr_cache = _model_cache_report(
        asr_model_id,
        required_any=["config.json", "model.bin"],
    )
    blockers = []
    if not torch_report.get("present"):
        blockers.append("torch_missing")
    elif not torch_report.get("cuda_available"):
        blockers.append("cuda_unavailable")
    for name, module in modules.items():
        if not module.get("present"):
            blockers.append(f"{name}_missing")
        if module.get("import_error"):
            blockers.append(f"{name}_import_error")
    ffmpeg_report = _ffmpeg_report(ffmpeg)
    ffprobe_report = _ffmpeg_report(ffprobe)
    if not ffmpeg_report["available"]:
        blockers.append("ffmpeg_unavailable")
    if not ffprobe_report["available"]:
        blockers.append("ffprobe_unavailable")
    if not vlm_cache["cache_complete"]:
        blockers.append("vlm_model_cache_incomplete")
    if not asr_cache["cache_complete"]:
        blockers.append("asr_model_cache_incomplete")
    return {
        "schema_version": "full_video_runtime_check.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": sys.executable,
        "python_version": sys.version,
        "torch": torch_report,
        "modules": modules,
        "ffmpeg": ffmpeg_report,
        "ffprobe": ffprobe_report,
        "models": {
            "vlm": vlm_cache,
            "asr": asr_cache,
        },
        "status": "ready" if not blockers else "not_ready",
        "blockers": blockers,
        "truth_label": "已实测" if not blockers else "未满足",
        "interpretation_note": (
            "ready only means local dependencies and model cache checks passed; it does "
            "not prove semantic accuracy or demo readiness."
        ),
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check full-video model runtime readiness.")
    parser.add_argument("--vlm-model-id", default=DEFAULT_VLM_MODEL_ID)
    parser.add_argument("--asr-model-id", default=DEFAULT_ASR_MODEL_ID)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_runtime_report(
        vlm_model_id=args.vlm_model_id,
        asr_model_id=args.asr_model_id,
        ffmpeg=args.ffmpeg,
        ffprobe=args.ffprobe,
    )
    if args.output:
        _atomic_write_json(Path(args.output), report)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["status"] == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
