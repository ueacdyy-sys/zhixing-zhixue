"""Android ADB 的只读身份与连接状态适配器。"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


class AndroidAdbProbeError(RuntimeError):
    """Raised when an Android device is not ADB-authorized or cannot be probed."""


@dataclass(frozen=True)
class AndroidAdbProbe:
    serial: str
    model: str
    android_version: str
    screen_stream_service_available: bool
    clock_offset_ms: int


def build_phone_connection(
    *,
    session_id: str,
    serial: str,
    transport: str,
    model: str,
    android_version: str,
    screen_stream_service_available: bool,
    clock_offset_ms: int,
) -> dict[str, object]:
    """Map an authorized ADB probe to the device connection contract.

    This is connection metadata only. It neither starts streaming nor reads the
    foreground screen, media bytes, application package list, or device content.
    """
    capabilities = ["adb_authorized", f"android_{android_version}", f"model_{model}"]
    if screen_stream_service_available:
        capabilities.append("screen_stream_service_available")
    return {
        "connection_id": f"adb:{serial}",
        "session_id": session_id,
        "device_id": f"android:{serial}",
        "device_type": "phone",
        "transport": transport,
        "data_route": "local_only",
        "status": "connected",
        "capabilities": capabilities,
        "clock_offset_ms": clock_offset_ms,
        "quality": "usable",
    }


def _run(adb_path: Path, serial: str, *args: str) -> str:
    completed = subprocess.run(
        [str(adb_path), "-s", serial, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        raise AndroidAdbProbeError(completed.stderr.strip() or "adb_command_failed")
    return completed.stdout.strip()


def probe_authorized_android(adb_path: Path, serial: str) -> AndroidAdbProbe:
    """Perform the minimum non-invasive ADB probe for an already-authorized device."""
    devices = subprocess.run(
        [str(adb_path), "devices"], check=False, capture_output=True, text=True, timeout=10
    )
    if devices.returncode != 0 or f"{serial}\tdevice" not in devices.stdout:
        raise AndroidAdbProbeError("adb_device_not_authorized")

    model = _run(adb_path, serial, "shell", "getprop", "ro.product.model")
    android_version = _run(adb_path, serial, "shell", "getprop", "ro.build.version.release")
    package_path = _run(adb_path, serial, "shell", "pm", "path", "info.dvkr.screenstream.dev")
    host_before = time.time_ns() // 1_000_000
    device_time = _run(adb_path, serial, "shell", "date", "+%s%3N")
    host_after = time.time_ns() // 1_000_000
    try:
        device_time_ms = int(device_time)
    except ValueError as error:
        raise AndroidAdbProbeError("android_clock_probe_failed") from error
    return AndroidAdbProbe(
        serial=serial,
        model=model,
        android_version=android_version,
        screen_stream_service_available=bool(package_path),
        clock_offset_ms=device_time_ms - ((host_before + host_after) // 2),
    )
