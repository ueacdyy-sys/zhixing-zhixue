from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from rtsp_frame_sampler import sample_video


ROOT = Path(__file__).resolve().parents[1]
ADB = ROOT / "tools" / "platform-tools" / "platform-tools" / "adb.exe"


def run_adb(serial: str, *args: str, check: bool = True) -> str:
    cmd = [str(ADB), "-s", serial, *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError(f"adb failed: {' '.join(cmd)}\nSTDOUT={proc.stdout}\nSTDERR={proc.stderr}")
    return proc.stdout


def dump_ui(serial: str) -> str:
    run_adb(serial, "shell", "uiautomator", "dump", "/sdcard/window.xml", check=False)
    return run_adb(serial, "exec-out", "cat", "/sdcard/window.xml", check=False)


def tap(serial: str, x: int, y: int) -> None:
    run_adb(serial, "shell", "input", "tap", str(x), str(y))


def swipe(serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500) -> None:
    run_adb(
        serial,
        "shell",
        "input",
        "swipe",
        str(x1),
        str(y1),
        str(x2),
        str(y2),
        str(duration_ms),
        check=False,
    )


def port_open(host: str, port: int, timeout_s: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Start ScreenStream and run live RTSP keyframe sampler.")
    parser.add_argument("--serial", default="10.26.122.39:5555")
    parser.add_argument("--phone-ip", default="10.26.122.39")
    parser.add_argument("--rtsp-port", type=int, default=8554)
    parser.add_argument("--wait-seconds", type=int, default=180)
    parser.add_argument("--capture-seconds", type=float, default=10)
    parser.add_argument("--target-interval-s", type=float, default=0.75)
    parser.add_argument("--dedup-hamming-threshold", type=int, default=4)
    parser.add_argument("--dynamic-scroll-probe", action="store_true")
    parser.add_argument("--scroll-count", type=int, default=4)
    parser.add_argument("--stream-stabilize-s", type=float, default=3.0)
    parser.add_argument("--open-retries", type=int, default=8)
    parser.add_argument("--open-retry-delay-s", type=float, default=1.0)
    args = parser.parse_args()

    rtsp_url = f"rtsp://{args.phone_ip}:{args.rtsp_port}/screen"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "captures" / f"live_rtsp_sampler_probe_{stamp}"

    print("[live-rtsp] device check")
    print(subprocess.run([str(ADB), "devices", "-l"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout)

    print("[live-rtsp] start ScreenStream activity")
    run_adb(
        args.serial,
        "shell",
        "am",
        "start",
        "-n",
        "info.dvkr.screenstream.dev/info.dvkr.screenstream.SingleActivity",
        check=False,
    )
    time.sleep(2)

    xml = dump_ui(args.serial)
    if "开始流媒体" in xml:
        print("[live-rtsp] ScreenStream visible; tapping start")
        tap(args.serial, 540, 1974)
        time.sleep(2)
        xml = dump_ui(args.serial)

    if "是否允许" in xml and "ScreenStream" in xml:
        print("[live-rtsp] phone is waiting for MediaProjection permission; tap Allow on the phone")

    deadline = time.monotonic() + args.wait_seconds
    stream_started = False
    while time.monotonic() < deadline:
        time.sleep(2)
        xml = dump_ui(args.serial)
        if "停止流媒体" in xml or port_open(args.phone_ip, args.rtsp_port):
            stream_started = True
            break

    if not stream_started:
        print("[live-rtsp] stream did not start before timeout; no capture performed", file=sys.stderr)
        sys.exit(2)

    def scroll_worker() -> None:
        # Keep motion inside ScreenStream's own page so the probe does not enter private content.
        time.sleep(1.5)
        for i in range(args.scroll_count):
            if i % 2 == 0:
                print("[live-rtsp] dynamic probe: swipe up")
                swipe(args.serial, 540, 1800, 540, 650, 500)
            else:
                print("[live-rtsp] dynamic probe: swipe down")
                swipe(args.serial, 540, 650, 540, 1800, 500)
            time.sleep(2.0)

    if args.dynamic_scroll_probe:
        threading.Thread(target=scroll_worker, daemon=True).start()

    print(f"[live-rtsp] RTSP appears active: {rtsp_url}")
    if args.stream_stabilize_s > 0:
        print(f"[live-rtsp] waiting {args.stream_stabilize_s:.1f}s for RTSP stream stabilization")
        time.sleep(args.stream_stabilize_s)
    report = sample_video(
        source=rtsp_url,
        out_dir=out_dir,
        target_interval_s=args.target_interval_s,
        max_frames=None,
        max_duration_s=args.capture_seconds,
        dedup_hamming_threshold=args.dedup_hamming_threshold,
        resize_width=None,
        rtsp_transport="tcp",
        open_retries=args.open_retries,
        open_retry_delay_s=args.open_retry_delay_s,
    )
    print(json.dumps({
        "out_dir": str(out_dir),
        "decoded_frames": report["decoded_frames"],
        "kept_frames": report["kept_frames"],
        "video_duration_s_from_pts": report["video_duration_s_from_pts"],
        "estimated_source_fps_from_pts": report["estimated_source_fps_from_pts"],
        "offline_decode_fps": report["offline_decode_fps"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
