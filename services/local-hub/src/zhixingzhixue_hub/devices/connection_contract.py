"""设备连接状态的纯领域契约。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ConnectionContractError(ValueError):
    """Raised when an adapter cannot provide a complete device connection state."""


REQUIRED_FIELDS = (
    "connection_id",
    "session_id",
    "device_id",
    "device_type",
    "transport",
    "data_route",
    "status",
    "capabilities",
    "clock_offset_ms",
    "quality",
)
ALLOWED_DEVICE_TYPES = {"phone", "pc", "glasses", "wearable"}
ALLOWED_TRANSPORTS = {"bluetooth", "lan", "usb"}
ALLOWED_DATA_ROUTES = {"phone_relay", "pc_direct", "local_only"}
ALLOWED_STATUSES = {"discovered", "authorized", "connected", "disconnected"}
ALLOWED_QUALITIES = {"usable", "degraded", "unavailable"}


def _text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConnectionContractError(f"{field} is required")
    return value


def validate_connection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate adapter output before it joins the shared evidence timeline."""
    connection = dict(payload)
    for field in REQUIRED_FIELDS:
        if field not in connection:
            raise ConnectionContractError(f"{field} is required")

    for field in ("connection_id", "session_id", "device_id"):
        _text(connection, field)

    for field, allowed in (
        ("device_type", ALLOWED_DEVICE_TYPES),
        ("transport", ALLOWED_TRANSPORTS),
        ("data_route", ALLOWED_DATA_ROUTES),
        ("status", ALLOWED_STATUSES),
        ("quality", ALLOWED_QUALITIES),
    ):
        value = _text(connection, field)
        if value not in allowed:
            raise ConnectionContractError(f"{field} is not supported")

    capabilities = connection["capabilities"]
    if not isinstance(capabilities, list) or not capabilities or not all(
        isinstance(capability, str) and capability.strip() for capability in capabilities
    ):
        raise ConnectionContractError("capabilities must be a non-empty string list")

    clock_offset = connection["clock_offset_ms"]
    if isinstance(clock_offset, bool) or not isinstance(clock_offset, (int, float)):
        raise ConnectionContractError("clock_offset_ms must be numeric")
    return connection
