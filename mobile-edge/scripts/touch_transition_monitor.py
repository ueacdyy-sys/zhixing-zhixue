"""Passive Android touch-to-visit transition adapter for an authorized ADB session."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path


EVENT_RE = re.compile(r"(?:ABS_MT_POSITION_(?P<axis>[XY])|ABS_MT_TRACKING_ID|BTN_TOUCH)\s+(?P<value>[0-9a-fA-F]+)")


def _value(raw: str) -> int:
    value = int(raw, 16)
    return -1 if value == 0xFFFFFFFF else value


class VerticalSwipeDetector:
    """Turns only finished, substantial vertical gestures into neutral facts."""

    def __init__(self, minimum_distance_px: int) -> None:
        self._minimum_distance_px = minimum_distance_px
        self._start_y: int | None = None
        self._last_y: int | None = None

    def consume(self, line: str, *, pc_monotonic_ns: int) -> dict[str, int | str] | None:
        match = EVENT_RE.search(line)
        if not match:
            return None
        token = match.group(0).split()[0]
        value = _value(match.group("value"))
        if token == "ABS_MT_POSITION_Y":
            self._last_y = value
            if self._start_y is None:
                self._start_y = value
            return None
        is_end = (token == "ABS_MT_TRACKING_ID" and value < 0) or (token == "BTN_TOUCH" and value == 0)
        if not is_end:
            return None
        start_y, end_y = self._start_y, self._last_y
        self._start_y = None
        self._last_y = None
        if start_y is None or end_y is None:
            return None
        delta_y = end_y - start_y
        if abs(delta_y) < self._minimum_distance_px:
            return None
        return {
            "event_type": "ContentTransitionCandidate",
            "pc_monotonic_ns": pc_monotonic_ns,
            "gesture": "VERTICAL_SWIPE",
            "delta_y_px": delta_y,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-distance-px", type=int, default=240)
    args = parser.parse_args()
    if args.minimum_distance_px <= 0:
        raise SystemExit("minimum distance must be positive")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [args.adb, "-s", args.serial, "shell", "getevent", "-lt", args.device]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1)
    detector = VerticalSwipeDetector(args.minimum_distance_px)
    try:
        assert process.stdout is not None
        with args.output.open("a", encoding="utf-8", newline="\n") as output:
            for line in process.stdout:
                event = detector.consume(line, pc_monotonic_ns=time.monotonic_ns())
                if event is not None:
                    output.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                    output.flush()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
    return process.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
