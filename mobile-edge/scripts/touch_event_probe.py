from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ADB = ROOT / "tools" / "platform-tools" / "platform-tools" / "adb.exe"

EVENT_RE = re.compile(
    r"^\[\s*(?P<ts>\d+(?:\.\d+)?)\]\s+(?:(?P<dev>/dev/input/event\d+):\s+)?"
    r"(?P<etype>\S+)\s+(?P<code>\S+)\s+(?P<value>\S+)"
)

HEX_RE = re.compile(r"^[0-9a-fA-F]{8}$")


@dataclass
class TouchSample:
    t: float
    x: int | None
    y: int | None
    pressure: int | None
    tracking_id: int | None
    btn_touch: int | None


@dataclass
class TouchStroke:
    start_t: float
    end_t: float
    duration_s: float
    sample_count: int
    start_x: int | None
    start_y: int | None
    end_x: int | None
    end_y: int | None
    dx: int | None
    dy: int | None
    distance_px: float | None
    gesture: str


def adb_text(serial: str, *args: str, timeout_s: float = 8) -> str:
    proc = subprocess.run(
        [str(ADB), "-s", serial, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    return (proc.stdout or "") + (proc.stderr or "")


def parse_value(raw: str) -> int:
    raw = raw.strip()
    if raw == "ffffffff":
        return -1
    if HEX_RE.match(raw):
        value = int(raw, 16)
        if value & 0x80000000:
            value -= 0x100000000
        return value
    try:
        return int(raw, 0)
    except ValueError:
        return 0


def normalize_code(code: str) -> str:
    mapping = {
        "0035": "ABS_MT_POSITION_X",
        "0036": "ABS_MT_POSITION_Y",
        "003a": "ABS_MT_PRESSURE",
        "0039": "ABS_MT_TRACKING_ID",
        "0018": "ABS_PRESSURE",
        "014a": "BTN_TOUCH",
        "0000": "SYN_REPORT",
    }
    return mapping.get(code.lower(), code)


def parse_getevent_lines(lines: list[str]) -> dict[str, Any]:
    samples: list[TouchSample] = []
    strokes: list[list[TouchSample]] = []
    active: list[TouchSample] = []

    x: int | None = None
    y: int | None = None
    pressure: int | None = None
    tracking_id: int | None = None
    btn_touch: int | None = None
    saw_touch_state = False
    last_sample: TouchSample | None = None

    for line in lines:
        match = EVENT_RE.match(line.strip())
        if not match:
            continue
        ts = float(match.group("ts"))
        code = normalize_code(match.group("code"))
        value = parse_value(match.group("value"))

        if code in ("ABS_MT_POSITION_X", "ABS_X"):
            x = value
        elif code in ("ABS_MT_POSITION_Y", "ABS_Y"):
            y = value
        elif code in ("ABS_MT_PRESSURE", "ABS_PRESSURE"):
            pressure = value
        elif code == "ABS_MT_TRACKING_ID":
            tracking_id = value
            saw_touch_state = True
            if value >= 0 and not active:
                active = []
            elif value < 0 and active:
                strokes.append(active)
                active = []
        elif code == "BTN_TOUCH":
            btn_touch = value
            saw_touch_state = True
            if value == 0 and active:
                strokes.append(active)
                active = []
        elif code == "SYN_REPORT":
            if saw_touch_state or x is not None or y is not None:
                sample = TouchSample(
                    t=ts,
                    x=x,
                    y=y,
                    pressure=pressure,
                    tracking_id=tracking_id,
                    btn_touch=btn_touch,
                )
                if last_sample != sample:
                    samples.append(sample)
                    if tracking_id is None or tracking_id >= 0 or btn_touch == 1:
                        active.append(sample)
                    last_sample = sample
            saw_touch_state = False
    if active:
        strokes.append(active)

    stroke_summaries = [summarize_stroke(stroke) for stroke in strokes if stroke]
    return {
        "raw_line_count": len(lines),
        "sample_count": len(samples),
        "stroke_count": len(stroke_summaries),
        "samples": [asdict(sample) for sample in samples],
        "strokes": [asdict(stroke) for stroke in stroke_summaries],
    }


def summarize_stroke(samples: list[TouchSample]) -> TouchStroke:
    first = samples[0]
    last = samples[-1]
    start_x, start_y = first.x, first.y
    end_x, end_y = last.x, last.y
    dx = end_x - start_x if start_x is not None and end_x is not None else None
    dy = end_y - start_y if start_y is not None and end_y is not None else None
    distance = (dx * dx + dy * dy) ** 0.5 if dx is not None and dy is not None else None
    duration = max(0.0, last.t - first.t)
    gesture = classify_gesture(duration, dx, dy, distance)
    return TouchStroke(
        start_t=first.t,
        end_t=last.t,
        duration_s=duration,
        sample_count=len(samples),
        start_x=start_x,
        start_y=start_y,
        end_x=end_x,
        end_y=end_y,
        dx=dx,
        dy=dy,
        distance_px=distance,
        gesture=gesture,
    )


def classify_gesture(duration: float, dx: int | None, dy: int | None, distance: float | None) -> str:
    if distance is None or dx is None or dy is None:
        return "unknown"
    if distance < 30 and duration < 0.35:
        return "tap_candidate"
    if abs(dy) >= abs(dx) and abs(dy) >= 120:
        return "swipe_up_candidate" if dy < 0 else "swipe_down_candidate"
    if abs(dx) >= 120:
        return "swipe_left_candidate" if dx < 0 else "swipe_right_candidate"
    if duration >= 0.5 and distance < 80:
        return "long_press_candidate"
    return "drag_or_minor_motion_candidate"


def capture_getevent(serial: str, device: str, seconds: float) -> tuple[list[str], float]:
    cmd = [str(ADB), "-s", serial, "shell", "getevent", "-lt", device]
    start = time.perf_counter()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    lines: list[str] = []
    try:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            if proc.stdout is None:
                break
            line = proc.stdout.readline()
            if line:
                lines.append(line.rstrip("\n"))
            elif proc.poll() is not None:
                break
            else:
                time.sleep(0.01)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
    return lines, time.perf_counter() - start


def main() -> None:
    parser = argparse.ArgumentParser(description="Passive ADB getevent touch probe. Does not inject tap/swipe.")
    parser.add_argument("--serial", default="MYQUT20213006206")
    parser.add_argument("--device", default="/dev/input/event4")
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--tag", default="touch_event_probe")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "captures" / f"{args.tag}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    inventory = adb_text(args.serial, "shell", "getevent", "-lp", timeout_s=10)
    lines, wall_s = capture_getevent(args.serial, args.device, args.seconds)
    parsed = parse_getevent_lines(lines)

    (out_dir / "getevent_lp.txt").write_text(inventory, encoding="utf-8")
    (out_dir / "touch_getevent_raw.log").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    report = {
        "out_dir": str(out_dir),
        "mode": "passive_getevent_read_only",
        "serial": args.serial,
        "device": args.device,
        "target_seconds": args.seconds,
        "wall_s": wall_s,
        **parsed,
        "notes": [
            "This script only reads touch events; it never injects input.",
            "Gesture labels are candidates derived from coordinate deltas and must be checked against video timestamps.",
            "A zero-line or zero-stroke result means no touch was observed during the window, not that touch capture is impossible.",
        ],
    }
    (out_dir / "touch_event_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "out_dir": str(out_dir),
        "raw_line_count": parsed["raw_line_count"],
        "sample_count": parsed["sample_count"],
        "stroke_count": parsed["stroke_count"],
        "strokes": parsed["strokes"][:5],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
