from __future__ import annotations

import argparse
import json
import math
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import av
import numpy as np


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


def run_text(cmd: list[str], timeout_s: float | None = None) -> tuple[int, str, float]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), time.perf_counter() - t0


def adb_text(serial: str | None, *args: str, timeout_s: float = 8) -> str:
    if not serial:
        return "serial_not_set"
    cmd = [str(ADB)]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    try:
        _, text, _ = run_text(cmd, timeout_s=timeout_s)
        return text
    except Exception as exc:
        return f"adb_error: {exc!r}"


def ffprobe_json(video_path: Path) -> dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    rc, text, _ = run_text(cmd, timeout_s=60)
    if rc != 0:
        return {"error": "ffprobe_failed", "returncode": rc, "output": text}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        return {"error": "ffprobe_json_decode_failed", "exception": repr(exc), "output": text}


def summarize(values: list[float]) -> dict[str, float | None]:
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return {"min": None, "median": None, "max": None, "mean": None}
    arr = np.array(finite, dtype=np.float64)
    return {
        "min": float(np.min(arr)),
        "median": float(np.median(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
    }


def decode_stats(video_path: Path) -> dict[str, Any]:
    t0 = time.perf_counter()
    container = av.open(str(video_path))
    stream = container.streams.video[0]
    decoded = 0
    packet_count = 0
    packet_bytes = 0
    pts_times: list[float] = []
    keyframes = 0
    first_t: float | None = None
    last_t: float | None = None
    width: int | None = None
    height: int | None = None

    for packet in container.demux(stream):
        if packet.size:
            packet_count += 1
            packet_bytes += int(packet.size)
        for frame in packet.decode():
            decoded += 1
            keyframes += int(bool(frame.key_frame))
            width = frame.width
            height = frame.height
            if frame.pts is not None and frame.time_base is not None:
                vt = float(frame.pts * frame.time_base)
                pts_times.append(vt)
                first_t = vt if first_t is None else min(first_t, vt)
                last_t = vt if last_t is None else max(last_t, vt)
    container.close()

    decode_wall_s = time.perf_counter() - t0
    duration_s = None
    if first_t is not None and last_t is not None and last_t >= first_t:
        duration_s = last_t - first_t
    intervals = [b - a for a, b in zip(pts_times, pts_times[1:]) if b >= a]
    long_gaps = [v for v in intervals if v > 0.2]
    return {
        "decoded_frames": decoded,
        "packet_count": packet_count,
        "packet_bytes": packet_bytes,
        "width": width,
        "height": height,
        "keyframes": keyframes,
        "first_pts_s": first_t,
        "last_pts_s": last_t,
        "duration_s_from_pts": duration_s,
        "estimated_fps_from_pts": decoded / duration_s if duration_s and duration_s > 0 else None,
        "decode_wall_s": decode_wall_s,
        "offline_decode_fps": decoded / decode_wall_s if decode_wall_s > 0 else None,
        "frame_interval_s": summarize(intervals),
        "long_gap_count_gt_200ms": len(long_gaps),
        "max_gap_s": max(long_gaps) if long_gaps else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Save a live RTSP screen stream with stream copy and measure data volume.")
    parser.add_argument("--phone-ip", default="10.26.122.39")
    parser.add_argument("--rtsp-port", type=int, default=8554)
    parser.add_argument("--rtsp-path", default="/screen")
    parser.add_argument("--rtsp-url", default=None)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--serial", default="MYQUT20213006206")
    parser.add_argument("--tag", default="rtsp_raw_stream_probe")
    parser.add_argument("--wait-stream-seconds", type=float, default=8)
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "captures" / f"{args.tag}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    rtsp_url = args.rtsp_url or f"rtsp://{args.phone_ip}:{args.rtsp_port}{args.rtsp_path}"
    video_path = out_dir / "raw_rtsp_copy.mkv"

    write_text(out_dir / "adb_devices.txt", adb_text(None, "devices", "-l", timeout_s=8))
    write_text(out_dir / "phone_ip_wlan0.txt", adb_text(args.serial, "shell", "ip", "-f", "inet", "addr", "show", "wlan0", timeout_s=8))
    write_text(out_dir / "foreground_before.txt", adb_text(args.serial, "shell", "dumpsys", "window", "windows", timeout_s=8))

    host = args.phone_ip
    deadline = time.monotonic() + args.wait_stream_seconds
    while time.monotonic() < deadline:
        if port_open(host, args.rtsp_port):
            break
        time.sleep(0.25)
    else:
        report = {
            "out_dir": str(out_dir),
            "rtsp_url": rtsp_url,
            "error": "rtsp_port_not_open",
            "note": "No phone UI operation was attempted. Start/confirm the screen streaming app if this fails.",
        }
        write_text(out_dir / "raw_stream_report.json", json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-t",
        str(args.seconds),
        "-map",
        "0:v:0",
        "-c:v",
        "copy",
        "-an",
        "-y",
        str(video_path),
    ]
    rc, ffmpeg_log, ffmpeg_wall_s = run_text(cmd, timeout_s=args.seconds + 45)
    write_text(out_dir / "ffmpeg_command.txt", " ".join(cmd))
    write_text(out_dir / "ffmpeg_capture.log", ffmpeg_log)
    if rc != 0 or not video_path.exists() or video_path.stat().st_size <= 0:
        report = {
            "out_dir": str(out_dir),
            "rtsp_url": rtsp_url,
            "returncode": rc,
            "ffmpeg_wall_s": ffmpeg_wall_s,
            "video_exists": video_path.exists(),
            "video_size_bytes": video_path.stat().st_size if video_path.exists() else 0,
            "error": "ffmpeg_capture_failed_or_empty",
        }
        write_text(out_dir / "raw_stream_report.json", json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    probe = ffprobe_json(video_path)
    write_text(out_dir / "ffprobe.json", json.dumps(probe, ensure_ascii=False, indent=2))
    decoded = decode_stats(video_path)

    size_bytes = video_path.stat().st_size
    duration_for_rate = decoded.get("duration_s_from_pts") or args.seconds
    avg_bps = (size_bytes * 8 / duration_for_rate) if duration_for_rate and duration_for_rate > 0 else None
    packet_bps = (
        decoded["packet_bytes"] * 8 / decoded["duration_s_from_pts"]
        if decoded.get("duration_s_from_pts") and decoded.get("packet_bytes")
        else None
    )

    report: dict[str, Any] = {
        "out_dir": str(out_dir),
        "rtsp_url": rtsp_url,
        "mode": "passive_rtsp_stream_copy_then_offline_decode",
        "target_seconds": args.seconds,
        "ffmpeg_wall_s": ffmpeg_wall_s,
        "video_file": str(video_path),
        "video_size_bytes": size_bytes,
        "video_size_mb": size_bytes / 1024 / 1024,
        "avg_container_bitrate_mbps": avg_bps / 1_000_000 if avg_bps else None,
        "avg_video_packet_bitrate_mbps": packet_bps / 1_000_000 if packet_bps else None,
        "estimated_mb_per_minute": (size_bytes / 1024 / 1024) * (60 / duration_for_rate) if duration_for_rate else None,
        "estimated_mb_per_hour": (size_bytes / 1024 / 1024) * (3600 / duration_for_rate) if duration_for_rate else None,
        "decode": decoded,
        "ffprobe_streams": probe.get("streams") if isinstance(probe, dict) else None,
        "ffprobe_format": probe.get("format") if isinstance(probe, dict) else None,
        "notes": [
            "This is a passive screen-stream read. It does not tap, swipe, or change the phone UI.",
            "The MKV size is a practical lower-bound estimate for phone-to-PC video payload; RTSP/TCP overhead is not included.",
            "The script saves the continuous stream, not only keyframes. Semantic video understanding is still a separate downstream step.",
        ],
    }
    write_text(out_dir / "raw_stream_report.json", json.dumps(report, ensure_ascii=False, indent=2))

    md = [
        "# RTSP Raw Stream Probe",
        "",
        f"- mode: {report['mode']}",
        f"- target_seconds: {args.seconds}",
        f"- ffmpeg_wall_s: {ffmpeg_wall_s:.3f}",
        f"- video_size_mb: {report['video_size_mb']:.3f}",
        f"- avg_container_bitrate_mbps: {report['avg_container_bitrate_mbps']:.3f}" if report["avg_container_bitrate_mbps"] else "- avg_container_bitrate_mbps: n/a",
        f"- decoded_frames: {decoded['decoded_frames']}",
        f"- duration_s_from_pts: {decoded['duration_s_from_pts']:.3f}" if decoded["duration_s_from_pts"] else "- duration_s_from_pts: n/a",
        f"- estimated_fps_from_pts: {decoded['estimated_fps_from_pts']:.3f}" if decoded["estimated_fps_from_pts"] else "- estimated_fps_from_pts: n/a",
        f"- offline_decode_fps: {decoded['offline_decode_fps']:.3f}" if decoded["offline_decode_fps"] else "- offline_decode_fps: n/a",
        f"- estimated_mb_per_minute: {report['estimated_mb_per_minute']:.3f}" if report["estimated_mb_per_minute"] else "- estimated_mb_per_minute: n/a",
        f"- estimated_mb_per_hour: {report['estimated_mb_per_hour']:.3f}" if report["estimated_mb_per_hour"] else "- estimated_mb_per_hour: n/a",
        "",
        "## Interpretation",
        "",
        "- The saved file is the continuous RTSP video stream, not a keyframe-only sample.",
        "- OCR/visual understanding has not been run in this probe; this probe answers transport/storage feasibility.",
        "- If long_gap_count_gt_200ms is nonzero, inspect timestamps before using the segment as a real-time baseline.",
    ]
    write_text(out_dir / "raw_stream_report.md", "\n".join(md) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
