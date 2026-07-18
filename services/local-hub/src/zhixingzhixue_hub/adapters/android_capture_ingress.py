"""用户显式授权后，Android 媒体文件进入本地证据目录的入站适配器。"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


class AndroidCaptureIngressError(ValueError):
    """Raised when a proposed Android media capture is not complete or authorized."""


def _timezone_timestamp(value: str, field: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as error:
        raise AndroidCaptureIngressError(f"{field}_must_be_iso8601") from error
    if timestamp.tzinfo is None:
        raise AndroidCaptureIngressError(f"{field}_must_include_timezone")
    return timestamp


def _existing_nonempty_file(path: Path, field: str) -> Path:
    if not path.is_file() or path.stat().st_size == 0:
        raise AndroidCaptureIngressError(f"{field}_file_required")
    return path.resolve()


def _digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_authorized_capture(
    *,
    capture_root: Path,
    session_id: str,
    capture_id: str,
    media_path: Path,
    audio_path: Path,
    start_ts: str,
    end_ts: str,
    consent_granted: bool,
) -> dict[str, Any]:
    """Register existing video and same-capture audio without starting a capture service.

    The caller must invoke this only after the student explicitly authorizes the
    capture. Files remain local; this adapter emits references and integrity hashes.
    """
    if not consent_granted:
        raise AndroidCaptureIngressError("explicit_consent_required")
    if not isinstance(session_id, str) or not session_id.strip():
        raise AndroidCaptureIngressError("session_id_required")
    if not isinstance(capture_id, str) or not capture_id.strip():
        raise AndroidCaptureIngressError("capture_id_required")
    start = _timezone_timestamp(start_ts, "start_ts")
    end = _timezone_timestamp(end_ts, "end_ts")
    if end < start:
        raise AndroidCaptureIngressError("end_ts_must_not_precede_start_ts")

    root = capture_root.resolve()
    media = _existing_nonempty_file(media_path, "media")
    audio = _existing_nonempty_file(audio_path, "audio")
    for path in (media, audio):
        try:
            path.relative_to(root)
        except ValueError as error:
            raise AndroidCaptureIngressError("capture_file_must_stay_within_capture_root") from error

    return {
        "session_id": session_id,
        "capture_id": capture_id,
        "source": "phone",
        "media_uri": f"local://captures/{capture_id}/{media.name}",
        "audio_uri": f"local://captures/{capture_id}/{audio.name}",
        "start_ts": start_ts,
        "end_ts": end_ts,
        "media_sha256": _digest(media),
        "audio_sha256": _digest(audio),
        "consent_scope": "android_media_capture",
    }
