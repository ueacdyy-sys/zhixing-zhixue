from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VIDEO_EXTS = {".mkv", ".mp4", ".webm", ".mov", ".m4v"}


def ffprobe_file(ffprobe: str, path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size if path.exists() else None,
            "error": proc.stderr.strip() or proc.stdout.strip() or f"ffprobe_exit_{proc.returncode}",
        }
    data = json.loads(proc.stdout)
    streams = data.get("streams") or []
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    video = [s for s in streams if s.get("codec_type") == "video"]
    fmt = data.get("format") or {}
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "duration_s": safe_float(fmt.get("duration")),
        "format_bit_rate": safe_float(fmt.get("bit_rate")),
        "stream_count": len(streams),
        "video_stream_count": len(video),
        "audio_stream_count": len(audio),
        "audio_codecs": sorted({str(s.get("codec_name")) for s in audio if s.get("codec_name")}),
        "video_codecs": sorted({str(s.get("codec_name")) for s in video if s.get("codec_name")}),
        "audio_streams": audio,
        "video_streams": video,
        "error": None,
    }


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Media Audio Inventory",
        "",
        "## Summary",
        "",
        f"- scanned_files: `{report['summary']['scanned_files']}`",
        f"- files_with_audio: `{report['summary']['files_with_audio']}`",
        f"- files_without_audio: `{report['summary']['files_without_audio']}`",
        f"- probe_errors: `{report['summary']['probe_errors']}`",
        "",
        "## Files With Audio",
        "",
    ]
    with_audio = [item for item in report["files"] if item.get("audio_stream_count", 0) > 0]
    if not with_audio:
        lines.append("- None.")
    for item in with_audio:
        lines.append(
            f"- `{item['path']}` | audio={item.get('audio_codecs')} | "
            f"video={item.get('video_codecs')} | duration={item.get('duration_s')}"
        )
    lines.extend(["", "## Files Without Audio", ""])
    for item in [x for x in report["files"] if not x.get("error") and x.get("audio_stream_count", 0) == 0]:
        lines.append(
            f"- `{item['path']}` | video={item.get('video_codecs')} | duration={item.get('duration_s')}"
        )
    errors = [x for x in report["files"] if x.get("error")]
    if errors:
        lines.extend(["", "## Probe Errors", ""])
        for item in errors:
            lines.append(f"- `{item['path']}` | {item.get('error')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory audio streams in captured video files.")
    parser.add_argument("--root", default=str(ROOT / "captures"))
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()

    scan_root = Path(args.root)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "captures" / f"media_audio_inventory_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        [p for p in scan_root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS],
        key=lambda p: str(p).lower(),
    )
    results = [ffprobe_file(args.ffprobe, path) for path in files]
    summary = {
        "scan_root": str(scan_root),
        "scanned_files": len(results),
        "files_with_audio": sum(1 for item in results if item.get("audio_stream_count", 0) > 0),
        "files_without_audio": sum(1 for item in results if not item.get("error") and item.get("audio_stream_count", 0) == 0),
        "probe_errors": sum(1 for item in results if item.get("error")),
    }
    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "files": results,
        "notes": [
            "Audio presence is determined by ffprobe stream metadata.",
            "A file without audio cannot support ASR unless another synchronized audio source exists.",
        ],
    }
    (out_dir / "media_audio_inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(out_dir / "media_audio_inventory.md", report)
    print(json.dumps({"out_dir": str(out_dir), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
