"""Read-only RTSP clock sampler for phone-to-PC latency evidence.

The sampler opens a short RTSP ``GET_PARAMETER`` connection only.  It never
starts media capture, reads media payload, or changes the phone's state.
Each sample records both PC monotonic boundaries so the network round-trip is
explicit instead of being hidden behind a guessed clock offset.
"""

from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path


REQUIRED_HEADERS = (
    "x-zhixing-clock-session-epoch",
    "x-zhixing-clock-anchor-elapsed-ns",
    "x-zhixing-clock-latest-video-pts-us",
    "x-zhixing-clock-latest-audio-pts-us",
    "x-zhixing-clock-last-media-emit-elapsed-ns",
    "x-zhixing-clock-observed-elapsed-ns",
    "x-zhixing-clock-last-requested-keyframe-pts-us",
    "x-zhixing-clock-last-requested-keyframe-emit-elapsed-ns",
)


def read_clock(host: str, port: int, path: str, timeout_seconds: float) -> dict[str, object]:
    """Return one independently timestamped, read-only clock observation."""
    target = f"rtsp://{host}:{port}/{path.lstrip('/')}"
    request = b"\r\n".join(
        (
            f"GET_PARAMETER {target} RTSP/1.0".encode("ascii"),
            b"CSeq: 1",
            b"User-Agent: Zhixing-ClockSampler/1",
            b"",
            b"",
        )
    )
    before_ns = time.monotonic_ns()
    with socket.create_connection((host, port), timeout=timeout_seconds) as connection:
        connection.settimeout(timeout_seconds)
        connection.sendall(request)
        response = connection.recv(8192).decode("iso-8859-1", "replace")
    after_ns = time.monotonic_ns()

    lines = response.splitlines()
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    missing = [name for name in REQUIRED_HEADERS if not headers.get(name)]
    if not lines or not lines[0].startswith("RTSP/1.0 200") or missing:
        raise RuntimeError(
            f"clock_response_invalid status={lines[0] if lines else '<empty>'!r} missing={missing}"
        )
    return {
        "pc_before_monotonic_ns": before_ns,
        "pc_after_monotonic_ns": after_ns,
        "rtt_ns": after_ns - before_ns,
        "session_epoch_id": int(headers["x-zhixing-clock-session-epoch"]),
        "anchor_elapsed_realtime_ns": int(headers["x-zhixing-clock-anchor-elapsed-ns"]),
        "latest_video_pts_us": int(headers["x-zhixing-clock-latest-video-pts-us"]),
        "latest_audio_pts_us": int(headers["x-zhixing-clock-latest-audio-pts-us"]),
        "last_media_emit_elapsed_realtime_ns": int(headers["x-zhixing-clock-last-media-emit-elapsed-ns"]),
        "phone_observed_elapsed_realtime_ns": int(headers["x-zhixing-clock-observed-elapsed-ns"]),
        "last_requested_keyframe_pts_us": int(headers["x-zhixing-clock-last-requested-keyframe-pts-us"]),
        "last_requested_keyframe_emit_elapsed_realtime_ns": int(headers["x-zhixing-clock-last-requested-keyframe-emit-elapsed-ns"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample the read-only phone RTSP clock to JSONL.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=8554)
    parser.add_argument("--path", default="screen")
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--interval-seconds", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration_seconds < 0 or args.interval_seconds <= 0:
        raise SystemExit("duration must be non-negative and interval must be positive")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    deadline = None if args.duration_seconds == 0 else time.monotonic() + args.duration_seconds
    failures = 0
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        while deadline is None or time.monotonic() < deadline:
            scheduled = time.monotonic()
            try:
                record = read_clock(args.host, args.port, args.path, timeout_seconds=3.0)
                record["status"] = "OK"
            except (OSError, RuntimeError, ValueError) as exc:
                failures += 1
                record = {"status": "ERROR", "error": type(exc).__name__, "detail": str(exc), "pc_monotonic_ns": time.monotonic_ns()}
            output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            output.flush()
            wait_seconds = args.interval_seconds - (time.monotonic() - scheduled)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
