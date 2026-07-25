"""Narrow LAN discovery responder for a locally paired 知行智学 PC gateway.

This is deliberately discovery-only.  It never exposes the long-lived
pairing code and does not grant access by itself.  Android still pins TLS and
the user must explicitly trust the discovered PC during the short pairing
window opened on the PC.
"""

from __future__ import annotations

import json
import socket
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


DISCOVERY_PORT = 39271
DISCOVER_MESSAGE = "ZHIXING_GATEWAY_DISCOVER_V1"
UTC = timezone.utc


@dataclass(frozen=True)
class LanDiscoveryAdvertisement:
    base_url: str
    spki_sha256: str
    pairing_token: str
    expires_at: str
    device_name: str

    def wire(self) -> bytes:
        return (json.dumps({
            "type": "ZHIXING_GATEWAY_ADVERTISEMENT_V1",
            "base_url": self.base_url,
            "spki_sha256": self.spki_sha256,
            "pairing_token": self.pairing_token,
            "expires_at": self.expires_at,
            "device_name": self.device_name,
        }, separators=(",", ":")) + "\n").encode("utf-8")


class LanGatewayDiscoveryResponder:
    def __init__(self, advertisement_supplier, port: int = DISCOVERY_PORT) -> None:
        self._advertisement_supplier = advertisement_supplier
        self._port = port
        self._stop = threading.Event()
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", self._port))
        sock.settimeout(0.5)
        self._socket = sock
        self._thread = threading.Thread(target=self._serve, name="zhixing-lan-discovery", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._socket is not None:
            self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _serve(self) -> None:
        assert self._socket is not None
        while not self._stop.is_set():
            try:
                payload, address = self._socket.recvfrom(1024)
            except (TimeoutError, OSError):
                continue
            if payload.decode("utf-8", errors="ignore").strip() != DISCOVER_MESSAGE:
                continue
            advertisement = self._advertisement_supplier()
            if advertisement is None:
                continue
            try:
                self._socket.sendto(advertisement.wire(), address)
            except OSError:
                continue


def expires_after(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()
