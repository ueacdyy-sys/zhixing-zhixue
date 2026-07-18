from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rtsp_frame_sampler import sample_video


ROOT = Path(__file__).resolve().parents[1]
ADB = ROOT / "tools" / "platform-tools" / "platform-tools" / "adb.exe"


def run(cmd: list[str], check: bool = False, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
        timeout=timeout,
    )


def run_adb(serial: str, *args: str, check: bool = False, timeout: float | None = None) -> str:
    proc = run([str(ADB), "-s", serial, *args], check=check, timeout=timeout)
    return (proc.stdout or "") + (proc.stderr or "")


def port_open(host: str, port: int, timeout_s: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def foreground_snapshot(serial: str) -> dict[str, str]:
    outputs: dict[str, str] = {}
    outputs["window"] = run_adb(
        serial,
        "shell",
        "dumpsys",
        "window",
        "windows",
        check=False,
        timeout=8,
    )
    outputs["activity"] = run_adb(
        serial,
        "shell",
        "dumpsys",
        "activity",
        "activities",
        check=False,
        timeout=8,
    )
    return outputs


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Passive RTSP capture for real phone browsing. It does not control the target app; "
            "it only starts/waits for ScreenStream when requested, then samples the live screen stream."
        )
    )
    parser.add_argument("--serial", default="10.26.122.39:5555")
    parser.add_argument("--phone-ip", default="10.26.122.39")
    parser.add_argument("--rtsp-port", type=int, default=8554)
    parser.add_argument("--capture-seconds", type=float, default=30)
    parser.add_argument("--target-interval-s", type=float, default=0.75)
    parser.add_argument("--dedup-hamming-threshold", type=int, default=4)
    parser.add_argument("--wait-stream-seconds", type=int, default=180)
    parser.add_argument("--switch-delay-seconds", type=int, default=20)
    parser.add_argument("--open-retries", type=int, default=8)
    parser.add_argument("--open-retry-delay-s", type=float, default=1.0)
    parser.add_argument("--no-start-screenstream", action="store_true")
    parser.add_argument("--tag", default="real_browsing")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "captures" / f"{args.tag}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rtsp_url = f"rtsp://{args.phone_ip}:{args.rtsp_port}/screen"

    device_list = run([str(ADB), "devices", "-l"], check=False).stdout
    write_text(out_dir / "adb_devices.txt", device_list)

    if not args.no_start_screenstream:
        start_output = run_adb(
            args.serial,
            "shell",
            "am",
            "start",
            "-n",
            "info.dvkr.screenstream.dev/info.dvkr.screenstream.SingleActivity",
            check=False,
            timeout=10,
        )
        write_text(out_dir / "screenstream_start.txt", start_output)

    print(f"[passive-capture] output: {out_dir}")
    print(f"[passive-capture] waiting for RTSP: {rtsp_url}")
    print("[passive-capture] if the phone asks for screen-recording permission, tap allow on the phone.")

    deadline = time.monotonic() + args.wait_stream_seconds
    while time.monotonic() < deadline:
        if port_open(args.phone_ip, args.rtsp_port):
            break
        time.sleep(1.0)
    else:
        print("[passive-capture] RTSP port did not open before timeout; no capture performed", file=sys.stderr)
        sys.exit(2)

    if args.switch_delay_seconds > 0:
        print(
            f"[passive-capture] RTSP is active. Switch to the real target app now; "
            f"capture starts in {args.switch_delay_seconds}s."
        )
        time.sleep(args.switch_delay_seconds)

    write_text(
        out_dir / "foreground_before_capture.json",
        json.dumps(foreground_snapshot(args.serial), ensure_ascii=False, indent=2),
    )

    t0 = time.perf_counter()
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
    end_wall_s = time.perf_counter() - t0

    write_text(
        out_dir / "foreground_after_capture.json",
        json.dumps(foreground_snapshot(args.serial), ensure_ascii=False, indent=2),
    )
    meta: dict[str, Any] = {
        "out_dir": str(out_dir),
        "rtsp_url": rtsp_url,
        "capture_seconds_target": args.capture_seconds,
        "capture_wall_s": end_wall_s,
        "target_interval_s": args.target_interval_s,
        "dedup_hamming_threshold": args.dedup_hamming_threshold,
        "decoded_frames": report.get("decoded_frames"),
        "kept_frames": report.get("kept_frames"),
        "video_duration_s_from_pts": report.get("video_duration_s_from_pts"),
        "estimated_source_fps_from_pts": report.get("estimated_source_fps_from_pts"),
        "decode_fps": report.get("offline_decode_fps"),
        "note": "This probe does not classify scenes or control the browsing app.",
    }
    write_text(out_dir / "passive_capture_meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
