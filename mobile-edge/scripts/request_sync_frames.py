"""Request bounded IDR cadence from an already-authorized Android RTSP stream.

This is a shell-protected transport measurement adapter. It neither starts
MediaProjection nor receives media; the phone-side ContentProvider accepts it
only from callers holding ``android.permission.DUMP``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


URI = "content://cn.zhixingzhixue.mobile.clockprobe/snapshot"
METHOD = "request_sync_frame"


def request_once(*, adb: str, serial: str) -> dict[str, object]:
    started_ns = time.monotonic_ns()
    completed = subprocess.run(
        [adb, "-s", serial, "shell", "content", "call", "--uri", URI, "--method", METHOD],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "event_type": "SyncFrameRequested",
        "pc_requested_monotonic_ns": started_ns,
        "pc_completed_monotonic_ns": time.monotonic_ns(),
        "return_code": completed.returncode,
        "accepted": completed.returncode == 0 and "requested=true" in completed.stdout,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--duration-seconds", type=float, default=0.0)
    args = parser.parse_args()
    if args.interval_seconds <= 0 or args.duration_seconds < 0:
        raise SystemExit("sync_frame_timing_invalid")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        while True:
            event = request_once(adb=args.adb, serial=args.serial)
            output.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            output.flush()
            if not bool(event["accepted"]):
                return 2
            if args.duration_seconds and time.monotonic() - started >= args.duration_seconds:
                return 0
            time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
