"""Build an immutable full-MP4 semantic window from sealed normalized fragments."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WindowMedia:
    path: Path
    sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def concat_manifest(paths: tuple[Path, ...]) -> str:
    if not paths or any(path.suffix.lower() != ".mp4" for path in paths):
        raise ValueError("normalized_mp4_fragments_required")
    return "".join(f"file '{path.resolve().as_posix().replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n" for path in paths)


def build_window_media(fragment_mp4s: tuple[Path, ...], *, output_path: Path, ffmpeg: str = "ffmpeg") -> WindowMedia:
    """Concatenate the exact physical fragments without re-encoding or frame sampling."""

    if any(not path.is_file() or path.stat().st_size <= 0 for path in fragment_mp4s):
        raise FileNotFoundError("normalized_fragment_missing")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = output_path.with_suffix(".concat.txt")
    partial_path = output_path.with_name(f"{output_path.stem}.partial{output_path.suffix}")
    manifest_path.write_text(concat_manifest(fragment_mp4s), encoding="utf-8", newline="\n")
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest_path),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(partial_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0 or not partial_path.is_file() or partial_path.stat().st_size <= 0:
            raise RuntimeError((completed.stderr or completed.stdout).strip()[-800:] or "window_media_concat_failed")
        os.replace(partial_path, output_path)
        return WindowMedia(output_path, _sha256(output_path))
    finally:
        manifest_path.unlink(missing_ok=True)
        partial_path.unlink(missing_ok=True)
