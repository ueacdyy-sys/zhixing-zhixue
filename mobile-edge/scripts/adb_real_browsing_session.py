from __future__ import annotations

import argparse
import json
import queue
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import imagehash
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ADB = ROOT / "tools" / "platform-tools" / "platform-tools" / "adb.exe"


def run_adb(serial: str, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(ADB), "-s", serial, *args],
        capture_output=True,
        timeout=timeout,
    )


def run_adb_text(serial: str, *args: str, timeout: float | None = None) -> str:
    proc = run_adb(serial, *args, timeout=timeout)
    return (proc.stdout + proc.stderr).decode("utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def phash_file(path: Path) -> str | None:
    try:
        image = Image.open(path)
        return str(imagehash.phash(image))
    except Exception:
        return None


def image_delta(prev_path: Path | None, curr_path: Path) -> dict[str, float | None]:
    if prev_path is None:
        return {"mean_absdiff": None, "changed_ratio": None}
    prev = cv2.imread(str(prev_path), cv2.IMREAD_GRAYSCALE)
    curr = cv2.imread(str(curr_path), cv2.IMREAD_GRAYSCALE)
    if prev is None or curr is None:
        return {"mean_absdiff": None, "changed_ratio": None}
    if prev.shape != curr.shape:
        curr = cv2.resize(curr, (prev.shape[1], prev.shape[0]), interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(prev, curr)
    return {
        "mean_absdiff": float(np.mean(diff)),
        "changed_ratio": float(np.mean(diff > 20)),
    }


def getevent_worker(serial: str, out_path: Path, stop: threading.Event, line_count_q: queue.Queue[int]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [str(ADB), "-s", serial, "shell", "getevent", "-lt"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    count = 0
    try:
        with out_path.open("w", encoding="utf-8") as f:
            while not stop.is_set():
                if proc.stdout is None:
                    break
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.01)
                    continue
                count += 1
                f.write(line)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        line_count_q.put(count)


def parse_resolution(text: str) -> dict[str, int | None]:
    match = re.search(r"Physical size:\s*(\d+)x(\d+)", text)
    if not match:
        match = re.search(r"Override size:\s*(\d+)x(\d+)", text)
    if not match:
        return {"width": None, "height": None}
    return {"width": int(match.group(1)), "height": int(match.group(2))}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only real browsing capture: ADB screencap + raw touch events.")
    parser.add_argument("--serial", default="10.26.122.39:5555")
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--interval-s", type=float, default=0.65)
    parser.add_argument("--tag", default="bilibili_real_browsing")
    parser.add_argument("--foreground-every", type=int, default=5)
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "captures" / f"{args.tag}_{stamp}"
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    write_text(out_dir / "adb_devices.txt", run_adb_text(args.serial, "devices", "-l", timeout=5))
    wm_size = run_adb_text(args.serial, "shell", "wm", "size", timeout=5)
    write_text(out_dir / "wm_size.txt", wm_size)
    write_text(out_dir / "wm_density.txt", run_adb_text(args.serial, "shell", "wm", "density", timeout=5))

    stop = threading.Event()
    count_q: queue.Queue[int] = queue.Queue()
    touch_path = out_dir / "touch_getevent_raw.log"
    touch_thread = threading.Thread(target=getevent_worker, args=(args.serial, touch_path, stop, count_q), daemon=True)
    touch_thread.start()

    frames: list[dict[str, Any]] = []
    foreground: list[dict[str, Any]] = []
    prev_frame: Path | None = None
    start = time.perf_counter()
    next_capture = start
    frame_index = 0
    try:
        while True:
            now = time.perf_counter()
            elapsed = now - start
            if elapsed >= args.seconds:
                break
            if now < next_capture:
                time.sleep(min(0.03, next_capture - now))
                continue

            cap_start = time.perf_counter()
            proc = run_adb(args.serial, "exec-out", "screencap", "-p", timeout=8)
            cap_wall = time.perf_counter() - cap_start
            frame_index += 1
            frame_path = frames_dir / f"frame_{frame_index:04d}.png"
            ok = proc.returncode == 0 and proc.stdout.startswith(b"\x89PNG")
            if ok:
                frame_path.write_bytes(proc.stdout)
                p_hash = phash_file(frame_path)
                delta = image_delta(prev_frame, frame_path)
                prev_frame = frame_path
            else:
                p_hash = None
                delta = {"mean_absdiff": None, "changed_ratio": None}
                write_text(out_dir / f"screencap_error_{frame_index:04d}.txt", proc.stderr.decode("utf-8", errors="replace"))

            frames.append(
                {
                    "index": frame_index,
                    "file": str(frame_path.relative_to(out_dir)) if ok else None,
                    "elapsed_s": elapsed,
                    "capture_wall_s": cap_wall,
                    "ok": ok,
                    "png_bytes": len(proc.stdout or b""),
                    "phash": p_hash,
                    **delta,
                }
            )

            if frame_index == 1 or frame_index % max(1, args.foreground_every) == 0:
                fg_start = time.perf_counter()
                top = run_adb_text(args.serial, "shell", "dumpsys", "window", "windows", timeout=8)
                foreground.append(
                    {
                        "frame_index": frame_index,
                        "elapsed_s": time.perf_counter() - start,
                        "wall_s": time.perf_counter() - fg_start,
                        "window_excerpt": "\n".join(
                            line for line in top.splitlines()
                            if "mCurrentFocus" in line or "mFocusedApp" in line or "mObscuringWindow" in line
                        )[:4000],
                    }
                )
            next_capture += args.interval_s
    finally:
        stop.set()
        touch_thread.join(timeout=4)

    touch_lines = 0
    try:
        touch_lines = count_q.get_nowait()
    except queue.Empty:
        pass

    duration = time.perf_counter() - start
    good_frames = [f for f in frames if f["ok"]]
    capture_times = [float(f["capture_wall_s"]) for f in good_frames]
    intervals = [b["elapsed_s"] - a["elapsed_s"] for a, b in zip(good_frames, good_frames[1:])]
    meta = {
        "out_dir": str(out_dir),
        "mode": "read_only_adb_screencap_getevent",
        "started_at": stamp,
        "duration_wall_s": duration,
        "target_seconds": args.seconds,
        "target_interval_s": args.interval_s,
        "frame_count": len(frames),
        "good_frame_count": len(good_frames),
        "touch_raw_line_count": touch_lines,
        "resolution": parse_resolution(wm_size),
        "capture_wall_s": {
            "min": min(capture_times) if capture_times else None,
            "median": float(np.median(capture_times)) if capture_times else None,
            "max": max(capture_times) if capture_times else None,
            "mean": float(np.mean(capture_times)) if capture_times else None,
        },
        "actual_frame_interval_s": {
            "min": min(intervals) if intervals else None,
            "median": float(np.median(intervals)) if intervals else None,
            "max": max(intervals) if intervals else None,
            "mean": float(np.mean(intervals)) if intervals else None,
        },
        "frames": frames,
        "foreground": foreground,
        "notes": [
            "This script is read-only: no tap, swipe, app start, or UI navigation.",
            "Raw getevent is stored for interaction replay analysis; coordinate normalization is a later parsing step.",
            "ADB screencap is lower-FPS than RTSP/MediaProjection but avoids interrupting the current phone session.",
        ],
    }
    write_text(out_dir / "session_report.json", json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps({
        "out_dir": str(out_dir),
        "duration_wall_s": duration,
        "good_frame_count": len(good_frames),
        "touch_raw_line_count": touch_lines,
        "capture_wall_s": meta["capture_wall_s"],
        "actual_frame_interval_s": meta["actual_frame_interval_s"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
