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


ROOT = Path(__file__).resolve().parents[1]
ADB = ROOT / "tools" / "platform-tools" / "platform-tools" / "adb.exe"
DEBUG_APK = (
    ROOT
    / "downloads"
    / "apk"
    / "ScreenStream-4.4.1-FDroid-debug-adb-audio-control-20260709.apk"
)

PACKAGE = "info.dvkr.screenstream.dev"
ACTIVITY = "info.dvkr.screenstream.SingleActivity"
DEBUG_RECEIVER = "info.dvkr.screenstream.rtsp.RtspDebugControlReceiver"
ACTION_ENABLE_AUDIO = "info.dvkr.screenstream.dev.DEBUG_ENABLE_RTSP_AUDIO"
ACTION_RESTART_STREAM = "info.dvkr.screenstream.dev.DEBUG_RESTART_RTSP_STREAM"


def run_text(cmd: list[str], timeout_s: float = 30, check: bool = False) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed rc={proc.returncode}: {' '.join(cmd)}\n{text}")
    return proc.returncode, text


def adb_cmd(serial: str | None, *args: str, timeout_s: float = 30, check: bool = False) -> tuple[int, str]:
    cmd = [str(ADB)]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    return run_text(cmd, timeout_s=timeout_s, check=check)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def port_open(host: str, port: int, timeout_s: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def ffprobe_json(video_path: Path) -> dict[str, Any]:
    rc, text = run_text(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(video_path),
        ],
        timeout_s=60,
    )
    if rc != 0:
        return {"error": "ffprobe_failed", "returncode": rc, "output": text}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        return {"error": "ffprobe_json_decode_failed", "exception": repr(exc), "output": text}


def summarize_probe(probe: dict[str, Any], video_path: Path) -> dict[str, Any]:
    streams = probe.get("streams") if isinstance(probe, dict) else []
    if not isinstance(streams, list):
        streams = []
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    return {
        "file": str(video_path),
        "file_size_bytes": video_path.stat().st_size if video_path.exists() else 0,
        "stream_count": len(streams),
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "video_codecs": [s.get("codec_name") for s in video_streams],
        "audio_codecs": [s.get("codec_name") for s in audio_streams],
        "duration_s": (probe.get("format") or {}).get("duration") if isinstance(probe, dict) else None,
        "bit_rate": (probe.get("format") or {}).get("bit_rate") if isinstance(probe, dict) else None,
    }


def grant_audio_permissions(serial: str, out_dir: Path) -> None:
    commands = [
        ["shell", "pm", "grant", PACKAGE, "android.permission.RECORD_AUDIO"],
        ["shell", "appops", "set", PACKAGE, "RECORD_AUDIO", "allow"],
        ["shell", "appops", "set", PACKAGE, "PROJECT_MEDIA", "allow"],
        ["shell", "pm", "grant", PACKAGE, "android.permission.POST_NOTIFICATIONS"],
    ]
    logs: list[dict[str, Any]] = []
    for args in commands:
        rc, text = adb_cmd(serial, *args, timeout_s=20, check=False)
        logs.append({"cmd": "adb " + " ".join(args), "returncode": rc, "output": text})
    write_text(out_dir / "permission_grants.json", json.dumps(logs, ensure_ascii=False, indent=2))


def broadcast_enable_audio(serial: str, out_dir: Path) -> None:
    args = [
        "shell",
        "am",
        "broadcast",
        "-n",
        f"{PACKAGE}/{DEBUG_RECEIVER}",
        "-a",
        ACTION_ENABLE_AUDIO,
        "--ez",
        "enable_mic",
        "true",
        "--ez",
        "enable_device_audio",
        "true",
    ]
    rc, text = adb_cmd(serial, *args, timeout_s=20, check=False)
    write_text(out_dir / "broadcast_enable_audio.txt", f"returncode={rc}\n{text}")


def broadcast_restart(serial: str, out_dir: Path, delay_ms: int) -> None:
    args = [
        "shell",
        "am",
        "broadcast",
        "-n",
        f"{PACKAGE}/{DEBUG_RECEIVER}",
        "-a",
        ACTION_RESTART_STREAM,
        "--ez",
        "enable_mic",
        "true",
        "--ez",
        "enable_device_audio",
        "true",
        "--el",
        "restart_delay_ms",
        str(delay_ms),
    ]
    rc, text = adb_cmd(serial, *args, timeout_s=20, check=False)
    write_text(out_dir / "broadcast_restart_stream.txt", f"returncode={rc}\n{text}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Probe ScreenStream RTSP audio. The script does not tap or swipe. "
            "After installing a new APK, Android may still require a manual MediaProjection confirmation."
        )
    )
    parser.add_argument("--serial", default="MYQUT20213006206")
    parser.add_argument("--phone-ip", default="10.26.122.39")
    parser.add_argument("--rtsp-port", type=int, default=8554)
    parser.add_argument("--rtsp-path", default="/screen")
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--wait-stream-seconds", type=float, default=180)
    parser.add_argument("--install-debug-apk", action="store_true")
    parser.add_argument("--launch-screenstream", action="store_true")
    parser.add_argument("--restart-via-debug-broadcast", action="store_true")
    parser.add_argument("--restart-delay-ms", type=int, default=800)
    parser.add_argument("--tag", default="screenstream_audio_rtsp_probe")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "captures" / f"{args.tag}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    rc, devices_text = adb_cmd(None, "devices", "-l", timeout_s=10, check=False)
    write_text(out_dir / "adb_devices.txt", devices_text)
    if args.serial not in devices_text:
        report = {
            "out_dir": str(out_dir),
            "error": "device_not_online",
            "serial": args.serial,
            "adb_devices": devices_text,
        }
        write_text(out_dir / "probe_report.json", json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    if args.install_debug_apk:
        if not DEBUG_APK.exists():
            raise FileNotFoundError(DEBUG_APK)
        rc, text = adb_cmd(args.serial, "install", "-r", str(DEBUG_APK), timeout_s=180, check=False)
        write_text(out_dir / "install_debug_apk.txt", f"returncode={rc}\n{text}")
        if rc != 0:
            report = {"out_dir": str(out_dir), "error": "install_failed", "install_output": text}
            write_text(out_dir / "probe_report.json", json.dumps(report, ensure_ascii=False, indent=2))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            raise SystemExit(1)

    grant_audio_permissions(args.serial, out_dir)
    broadcast_enable_audio(args.serial, out_dir)

    if args.launch_screenstream:
        rc, text = adb_cmd(
            args.serial,
            "shell",
            "am",
            "start",
            "-n",
            f"{PACKAGE}/{ACTIVITY}",
            timeout_s=20,
            check=False,
        )
        write_text(out_dir / "launch_screenstream.txt", f"returncode={rc}\n{text}")

    if args.restart_via_debug_broadcast:
        broadcast_restart(args.serial, out_dir, args.restart_delay_ms)

    rtsp_url = f"rtsp://{args.phone_ip}:{args.rtsp_port}{args.rtsp_path}"
    deadline = time.monotonic() + args.wait_stream_seconds
    stream_seen = False
    while time.monotonic() < deadline:
        if port_open(args.phone_ip, args.rtsp_port, timeout_s=1.0):
            stream_seen = True
            break
        time.sleep(1.0)

    if not stream_seen:
        rc, logcat = adb_cmd(args.serial, "logcat", "-d", "-v", "time", "SSApp:D", "*:S", timeout_s=20, check=False)
        write_text(out_dir / "screenstream_logcat.txt", logcat)
        report = {
            "out_dir": str(out_dir),
            "rtsp_url": rtsp_url,
            "error": "rtsp_port_not_open",
            "note": (
                "If the debug APK was newly installed, open ScreenStream and approve screen capture once. "
                "ADB can grant audio permission, but it cannot silently create the MediaProjection consent intent."
            ),
        }
        write_text(out_dir / "probe_report.json", json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    video_path = out_dir / "rtsp_all_streams.mkv"
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-t",
        str(args.seconds),
        "-map",
        "0",
        "-c",
        "copy",
        "-y",
        str(video_path),
    ]
    t0 = time.perf_counter()
    rc, ffmpeg_log = run_text(ffmpeg_cmd, timeout_s=args.seconds + 60, check=False)
    ffmpeg_wall_s = time.perf_counter() - t0
    write_text(out_dir / "ffmpeg_command.txt", " ".join(ffmpeg_cmd))
    write_text(out_dir / "ffmpeg_capture.log", ffmpeg_log)

    probe = ffprobe_json(video_path) if video_path.exists() and video_path.stat().st_size > 0 else {"error": "missing_or_empty_video"}
    write_text(out_dir / "ffprobe.json", json.dumps(probe, ensure_ascii=False, indent=2))

    rc_log, logcat = adb_cmd(args.serial, "logcat", "-d", "-v", "time", "SSApp:D", "*:S", timeout_s=20, check=False)
    write_text(out_dir / "screenstream_logcat.txt", logcat)

    summary = summarize_probe(probe, video_path)
    report = {
        "out_dir": str(out_dir),
        "rtsp_url": rtsp_url,
        "ffmpeg_returncode": rc,
        "ffmpeg_wall_s": ffmpeg_wall_s,
        "summary": summary,
        "audio_present": summary["audio_stream_count"] > 0,
        "debug_apk": str(DEBUG_APK),
        "notes": [
            "This probe records all RTSP streams with -map 0; audio_stream_count>0 is the pass condition.",
            "The script does not perform touch injection. Launching ScreenStream is optional and explicit.",
            "If MediaProjection consent is missing, user confirmation is still required by Android.",
        ],
    }
    write_text(out_dir / "probe_report.json", json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if rc != 0 or not report["audio_present"]:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except subprocess.TimeoutExpired as exc:
        print(json.dumps({"error": "timeout", "cmd": exc.cmd}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise
