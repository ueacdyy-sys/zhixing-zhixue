from __future__ import annotations

import argparse
import json
import queue
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rtsp_frame_sampler import sample_video


ROOT = Path(__file__).resolve().parents[1]
ADB = ROOT / "tools" / "platform-tools" / "platform-tools" / "adb.exe"


def port_open(host: str, port: int, timeout_s: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def adb_text(serial: str, *args: str, timeout: float = 8) -> str:
    proc = subprocess.run(
        [str(ADB), "-s", serial, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return (proc.stdout or "") + (proc.stderr or "")


def getevent_worker(serial: str, out_path: Path, stop: threading.Event, count_q: queue.Queue[int]) -> None:
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
        count_q.put(count)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only RTSP screen stream + raw touch session capture.")
    parser.add_argument("--serial", default="10.26.122.39:5555")
    parser.add_argument("--phone-ip", default="10.26.122.39")
    parser.add_argument("--rtsp-port", type=int, default=8554)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--target-interval-s", type=float, default=0.5)
    parser.add_argument("--dedup-hamming-threshold", type=int, default=4)
    parser.add_argument("--wait-stream-seconds", type=int, default=20)
    parser.add_argument("--tag", default="bilibili_rtsp_real_browsing")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "captures" / f"{args.tag}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rtsp_url = f"rtsp://{args.phone_ip}:{args.rtsp_port}/screen"

    write_text(out_dir / "adb_devices.txt", adb_text(args.serial, "devices", "-l", timeout=5))
    write_text(out_dir / "foreground_before.txt", adb_text(args.serial, "shell", "dumpsys", "window", "windows", timeout=8))
    write_text(out_dir / "activity_before.txt", adb_text(args.serial, "shell", "dumpsys", "activity", "activities", timeout=8))

    deadline = time.monotonic() + args.wait_stream_seconds
    while time.monotonic() < deadline:
        if port_open(args.phone_ip, args.rtsp_port):
            break
        time.sleep(0.5)
    else:
        meta = {"out_dir": str(out_dir), "rtsp_url": rtsp_url, "error": "rtsp_port_not_open"}
        write_text(out_dir / "session_report.json", json.dumps(meta, ensure_ascii=False, indent=2))
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    stop = threading.Event()
    count_q: queue.Queue[int] = queue.Queue()
    touch_thread = threading.Thread(
        target=getevent_worker,
        args=(args.serial, out_dir / "touch_getevent_raw.log", stop, count_q),
        daemon=True,
    )
    touch_thread.start()

    t0 = time.perf_counter()
    error: str | None = None
    report: dict[str, Any] | None = None
    try:
        report = sample_video(
            source=rtsp_url,
            out_dir=out_dir,
            target_interval_s=args.target_interval_s,
            max_frames=None,
            max_duration_s=args.seconds,
            dedup_hamming_threshold=args.dedup_hamming_threshold,
            resize_width=None,
            rtsp_transport="tcp",
            open_retries=8,
            open_retry_delay_s=1.0,
        )
    except Exception as exc:
        error = repr(exc)
    finally:
        stop.set()
        touch_thread.join(timeout=4)

    touch_lines = 0
    try:
        touch_lines = count_q.get_nowait()
    except queue.Empty:
        pass

    write_text(out_dir / "foreground_after.txt", adb_text(args.serial, "shell", "dumpsys", "window", "windows", timeout=8))
    elapsed = time.perf_counter() - t0
    meta: dict[str, Any] = {
        "out_dir": str(out_dir),
        "rtsp_url": rtsp_url,
        "mode": "read_only_rtsp_plus_getevent",
        "target_seconds": args.seconds,
        "wall_s": elapsed,
        "target_interval_s": args.target_interval_s,
        "dedup_hamming_threshold": args.dedup_hamming_threshold,
        "touch_raw_line_count": touch_lines,
        "error": error,
    }
    if report:
        meta.update({
            "decoded_frames": report.get("decoded_frames"),
            "kept_frames": report.get("kept_frames"),
            "video_duration_s_from_pts": report.get("video_duration_s_from_pts"),
            "estimated_source_fps_from_pts": report.get("estimated_source_fps_from_pts"),
            "decode_fps": report.get("offline_decode_fps"),
            "kept_frame_interval_s": report.get("kept_frame_interval_s"),
            "video_frame_interval_s": report.get("video_frame_interval_s"),
        })
    write_text(out_dir / "session_report.json", json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    if error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
