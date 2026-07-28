"""Paired-PC gateway for the 知行智学 mobile application.

The gateway deliberately separates three boundaries: a paired-device control
plane, a durable analysis outbox, and the optional AI workspace.  The outbox
is SQLite-backed: delivery is at-least-once, ACK happens only after Android
has persisted a message, and invalid messages enter an auditable dead letter
state instead of silently disappearing.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


UTC = timezone.utc
MAX_PROMPT_CHARS = 12_000
MAX_CONTEXT_ITEMS = 12
MAX_OUTBOX_PAYLOAD_BYTES = 64 * 1024
MAX_OUTBOX_PER_DEVICE = 200
MAX_RESOURCE_BYTES = 32 * 1024 * 1024
MAX_GRAPH_EVENT_PAYLOAD_BYTES = 48 * 1024
MAX_GRAPH_EVENTS_PER_REQUEST = 50
DEFAULT_MESSAGE_TTL_SECONDS = 300
DELIVERY_LEASE_SECONDS = 30
# This is a user-approved, TLS-pinned device pairing credential rather than a
# browser login session.  An eight-hour expiry made a phone silently lose its
# automatic PC connection after an overnight pause and forced needless manual
# re-pairing.  Revocation remains immediate; planned annual renewal prevents a
# forgotten local credential from living forever.
PAIRING_CREDENTIAL_TTL_SECONDS = 365 * 24 * 60 * 60
PAIRING_ATTEMPT_WINDOW_SECONDS = 5 * 60
PAIRING_ATTEMPT_LIMIT = 5
NEARBY_PAIRING_WINDOW_SECONDS = 120


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def sha256(value: str | bytes) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class GatewaySettings:
    pairing_code: str
    ollama_base_url: str | None
    ollama_model: str | None
    artifact_dir: Path
    ingress_key: str = ""
    search_base_url: str | None = None
    database_path: Path | None = None
    document_python: Path | None = None
    ai_provider: Literal["auto", "local", "openai_compatible"] = "auto"
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    cloud_failure_fallback_to_local: bool = False
    # The externally reachable HTTPS origin of this PC on the LAN.  It is
    # intentionally explicit: a process bound to 0.0.0.0 cannot infer which
    # certificate SAN the Android client is allowed to trust.
    gateway_public_url: str | None = None
    gateway_spki_sha256: str | None = None
    gateway_ca_bundle: Path | None = None
    realtime_runner: Path | None = None
    realtime_output_dir: Path | None = None

    @classmethod
    def from_environment(cls) -> "GatewaySettings":
        pairing_code = os.environ.get("ZHIXING_PAIRING_CODE", "").strip()
        if not pairing_code:
            raise RuntimeError("ZHIXING_PAIRING_CODE is required")
        artifact_dir = Path(os.environ.get("ZHIXING_AGENT_ARTIFACT_DIR", "artifacts/local-agent-gateway"))
        database_path = Path(os.environ.get("ZHIXING_GATEWAY_DB", artifact_dir / "gateway.sqlite3"))
        ingress_key = os.environ.get("ZHIXING_ANALYSIS_INGRESS_KEY", "").strip()
        if not ingress_key:
            raise RuntimeError("ZHIXING_ANALYSIS_INGRESS_KEY is required")
        return cls(
            pairing_code=pairing_code,
            ollama_base_url=os.environ.get("ZHIXING_OLLAMA_BASE_URL", "").strip().rstrip("/") or None,
            ollama_model=os.environ.get("ZHIXING_OLLAMA_MODEL", "").strip() or None,
            artifact_dir=artifact_dir,
            ingress_key=ingress_key,
            search_base_url=os.environ.get("ZHIXING_SEARXNG_URL", "").strip().rstrip("/") or None,
            database_path=database_path,
            document_python=Path(os.environ.get("ZHIXING_DOCUMENT_PYTHON", r"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")),
            ai_provider=_provider_from_environment(),
            openai_base_url=os.environ.get("ZHIXING_OPENAI_BASE_URL", "").strip().rstrip("/") or None,
            openai_api_key=os.environ.get("ZHIXING_OPENAI_API_KEY", "").strip() or None,
            openai_model=os.environ.get("ZHIXING_OPENAI_MODEL", "").strip() or None,
            cloud_failure_fallback_to_local=os.environ.get("ZHIXING_AI_CLOUD_FAILURE_FALLBACK_LOCAL", "").strip().lower() in {"1", "true", "yes"},
            gateway_public_url=os.environ.get("ZHIXING_GATEWAY_PUBLIC_URL", "").strip().rstrip("/") or None,
            gateway_spki_sha256=os.environ.get("ZHIXING_GATEWAY_SPKI_SHA256", "").strip() or None,
            gateway_ca_bundle=Path(os.environ["ZHIXING_GATEWAY_CA_BUNDLE"]) if os.environ.get("ZHIXING_GATEWAY_CA_BUNDLE", "").strip() else None,
            realtime_runner=Path(os.environ["ZHIXING_REALTIME_RUNNER"]) if os.environ.get("ZHIXING_REALTIME_RUNNER", "").strip() else None,
            realtime_output_dir=Path(os.environ["ZHIXING_REALTIME_OUTPUT_DIR"]) if os.environ.get("ZHIXING_REALTIME_OUTPUT_DIR", "").strip() else None,
        )

    @property
    def agent_available(self) -> bool:
        return self.selected_provider is not None

    @property
    def local_available(self) -> bool:
        return self.ollama_base_url is not None and self.ollama_model is not None

    @property
    def cloud_available(self) -> bool:
        return self.openai_base_url is not None and self.openai_api_key is not None and self.openai_model is not None

    @property
    def selected_provider(self) -> str | None:
        if self.ai_provider == "local":
            return "ollama" if self.local_available else None
        if self.ai_provider == "openai_compatible":
            return "openai_compatible" if self.cloud_available else None
        if self.cloud_available:
            return "openai_compatible"
        return "ollama" if self.local_available else None

    @property
    def selected_model(self) -> str | None:
        if self.selected_provider == "openai_compatible":
            return self.openai_model
        return self.ollama_model if self.selected_provider == "ollama" else None

    @property
    def search_available(self) -> bool:
        return self.search_base_url is not None

    @property
    def resolved_database_path(self) -> Path:
        return self.database_path or self.artifact_dir / "gateway.sqlite3"

    @property
    def resolved_document_python(self) -> Path:
        return self.document_python or Path(sys.executable)

    @property
    def resolved_realtime_runner(self) -> Path:
        return self.realtime_runner or Path(__file__).with_name("run_realtime_e2e.py")

    @property
    def resolved_realtime_output_dir(self) -> Path:
        return self.realtime_output_dir or self.artifact_dir / "realtime-sessions"


def _provider_from_environment() -> Literal["auto", "local", "openai_compatible"]:
    value = os.environ.get("ZHIXING_AI_PROVIDER", "auto").strip().lower()
    aliases = {"ollama": "local", "openai": "openai_compatible", "openai-compatible": "openai_compatible"}
    value = aliases.get(value, value)
    if value not in {"auto", "local", "openai_compatible"}:
        raise RuntimeError("ZHIXING_AI_PROVIDER must be auto, local, or openai_compatible")
    return value  # type: ignore[return-value]


class PairingRateLimiter:
    """Small in-process protection for a LAN pairing code; never logs the code."""

    def __init__(self) -> None:
        self._attempts: dict[str, list[datetime]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        threshold = utc_now() - timedelta(seconds=PAIRING_ATTEMPT_WINDOW_SECONDS)
        with self._lock:
            attempts = [value for value in self._attempts.get(key, []) if value > threshold]
            self._attempts[key] = attempts
            return len(attempts) < PAIRING_ATTEMPT_LIMIT

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._attempts.setdefault(key, []).append(utc_now())

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


class NearbyPairingWindow:
    """A short PC-authorized pairing window, separate from the legacy code."""

    def __init__(self, seconds: int = NEARBY_PAIRING_WINDOW_SECONDS) -> None:
        self._token = secrets.token_urlsafe(32)
        self._expires_at = utc_now() + timedelta(seconds=seconds)

    def accepts(self, token: str) -> bool:
        return utc_now() < self._expires_at and hmac.compare_digest(token, self._token)

    def advertisement(self, base_url: str | None, spki_sha256: str | None, device_name: str) -> dict[str, str] | None:
        if not base_url or not spki_sha256 or utc_now() >= self._expires_at:
            return None
        return {
            "base_url": base_url,
            "spki_sha256": spki_sha256,
            "pairing_token": self._token,
            "expires_at": iso(self._expires_at),
            "device_name": device_name,
        }


class PairRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=160)
    pairing_token: str = Field(min_length=1, max_length=256)


class CaptureSessionStartRequest(BaseModel):
    """Phone asks its already-paired PC to pull the *current* local RTSP server.

    The phone never supplies a free-form URL.  The gateway derives the source
    host from the authenticated TLS peer so this endpoint cannot become an
    SSRF primitive.
    """

    session_id: str = Field(min_length=1, max_length=160)
    rtsp_port: int = Field(ge=1, le=65535)
    rtsp_path: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._~-]+$")
    source: Literal["PHONE_SCREEN"] = "PHONE_SCREEN"


@dataclass
class CaptureSession:
    session_id: str
    device_id: str
    rtsp_url: str
    output_dir: Path
    state: str
    started_at: str
    process: subprocess.Popen[str] | None = None
    stopped_at: str | None = None
    error: str | None = None

    def response(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "rtsp_url": self.rtsp_url,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "error": self.error,
        }


class LanCaptureSupervisor:
    """Owns one real-time analysis runner per paired phone capture session."""

    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings
        self._sessions: dict[tuple[str, str], CaptureSession] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _rtsp_url(peer_host: str, port: int, path: str) -> str:
        try:
            parsed = ipaddress.ip_address(peer_host)
        except ValueError as error:
            raise ValueError("capture_peer_address_invalid") from error
        # Link-local/loopback are allowed only when the PC itself initiated a
        # local test.  Public/multicast/unspecified destinations are rejected.
        if parsed.is_unspecified or parsed.is_multicast or not (parsed.is_private or parsed.is_loopback or parsed.is_link_local):
            raise ValueError("capture_peer_address_not_private")
        authority = f"[{peer_host}]" if parsed.version == 6 else peer_host
        return f"rtsp://{authority}:{port}/{path}"

    def start(self, device_id: str, peer_host: str, request: CaptureSessionStartRequest) -> CaptureSession:
        key = (device_id, request.session_id)
        with self._lock:
            existing = self._sessions.get(key)
            if existing is not None and existing.state in {"STARTING", "RUNNING", "STOPPING"}:
                return existing
            rtsp_url = self._rtsp_url(peer_host, request.rtsp_port, request.rtsp_path)
            now = utc_now()
            output_dir = self._settings.resolved_realtime_output_dir / f"{request.session_id}-{now.strftime('%Y%m%dT%H%M%SZ')}"
            session = CaptureSession(request.session_id, device_id, rtsp_url, output_dir, "STARTING", iso(now))
            self._sessions[key] = session
            if not self._settings.gateway_public_url:
                session.state = "FAILED_CONFIGURATION"
                session.error = "gateway_public_url_required_for_candidate_return"
                return session
            if not self._settings.resolved_realtime_runner.is_file():
                session.state = "FAILED_RUNTIME_NOT_READY"
                session.error = "realtime_runner_missing"
                return session
            try:
                command = [
                    sys.executable, str(self._settings.resolved_realtime_runner),
                    "--source", rtsp_url,
                    "--output-dir", str(output_dir),
                    "--clock-host", peer_host,
                    "--pc-outbox-gateway", self._settings.gateway_public_url,
                    "--pc-outbox-device-id", device_id,
                ]
                environment = os.environ.copy()
                if self._settings.gateway_ca_bundle is not None:
                    environment["REQUESTS_CA_BUNDLE"] = str(self._settings.gateway_ca_bundle)
                output_dir.parent.mkdir(parents=True, exist_ok=True)
                log = output_dir.parent / f"{output_dir.name}.supervisor.log"
                handle = log.open("w", encoding="utf-8", newline="\n")
                session.process = subprocess.Popen(command, cwd=self._settings.resolved_realtime_runner.parent.parent, env=environment, stdout=handle, stderr=subprocess.STDOUT, text=True)
                handle.close()
                threading.Thread(target=self._watch, args=(key,), daemon=True, name=f"capture-{request.session_id}").start()
            except OSError as error:
                session.state = "FAILED_RUNTIME_NOT_READY"
                session.error = f"runner_start_failed:{error.__class__.__name__}"
            return session

    def _watch(self, key: tuple[str, str]) -> None:
        with self._lock:
            session = self._sessions.get(key)
            process = session.process if session is not None else None
        if session is None or process is None:
            return
        # Popen success does not prove OCR/ASR/VLM readiness.  The runner's
        # actual contract is one receipt per lane; keep the API in STARTING
        # until all three receipts exist instead of advertising a worker after
        # an arbitrary two-second delay.
        ready_dir = session.output_dir / "artifacts"
        expected_receipts = tuple(ready_dir / f"{lane}-e2e.ready.json" for lane in ("ocr", "asr", "vlm"))
        readiness_deadline = time.monotonic() + 120.0
        workers_ready = False
        while process.poll() is None and time.monotonic() < readiness_deadline:
            if all(receipt.is_file() for receipt in expected_receipts):
                workers_ready = True
                with self._lock:
                    if session.state == "STARTING":
                        session.state = "RUNNING"
                break
            time.sleep(0.25)
        if not workers_ready:
            with self._lock:
                session.state = "FAILED_RUNTIME_NOT_READY"
                session.error = "worker_ready_timeout" if process.poll() is None else "worker_exited_before_ready"
            if process.poll() is None:
                process.terminate()
        code = process.wait()
        with self._lock:
            if session.state == "STOPPING":
                session.state = "STOPPED"
            elif session.state == "FAILED_RUNTIME_NOT_READY":
                pass
            elif code == 0:
                session.state = "COMPLETED"
            else:
                session.state = "FAILED"
                session.error = f"runner_exit_{code}"
            session.stopped_at = iso(utc_now())

    def stop(self, device_id: str, session_id: str) -> CaptureSession | None:
        with self._lock:
            session = self._sessions.get((device_id, session_id))
            if session is None:
                return None
            if session.state in {"RUNNING", "STARTING"}:
                # Phone stops its RTSP server first; the pipeline then closes
                # naturally and flushes its tail.  Do not kill a live runner
                # here, because that would discard its final evidence window.
                session.state = "STOPPING"
            return session

    def get(self, device_id: str, session_id: str) -> CaptureSession | None:
        with self._lock:
            return self._sessions.get((device_id, session_id))


class AgentContext(BaseModel):
    id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=4_000)
    source: Literal["PHONE_SCREEN", "GLASSES_FIRST_PERSON"]
    visit_id: str = Field(min_length=1, max_length=256)
    evidence_refs: list[str] = Field(min_length=1, max_length=32)


class AgentResource(BaseModel):
    id: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=512)
    mime_type: str | None = Field(default=None, max_length=160)
    state: Literal["LOCAL_QUEUED", "UPLOADING", "READY_FOR_AGENT", "FAILED"]


class AgentRunRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=256)
    conversation_id: str = Field(min_length=1, max_length=256)
    mode: Literal["ANSWER", "WEB_SEARCH", "EXPORT_MARKDOWN", "EXPORT_DOCX", "EXPORT_PPTX", "EXPORT_PDF"]
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    contexts: list[AgentContext] = Field(default_factory=list, max_length=MAX_CONTEXT_ITEMS)
    resources: list[AgentResource] = Field(default_factory=list, max_length=32)


class OutboxIngressRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=160)
    message_id: str = Field(min_length=1, max_length=256)
    payload: dict[str, object]
    expires_at: str | None = Field(default=None, max_length=64)


class AckRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=160)
    message_id: str = Field(min_length=1, max_length=256)
    delivery_token: str = Field(min_length=1, max_length=256)


class NackRequest(AckRequest):
    reason: str = Field(min_length=1, max_length=240)
    retryable: bool = False


class KnowledgeGraphEventRequest(BaseModel):
    """One immutable, optimistic-concurrency controlled graph mutation."""

    event_id: str = Field(min_length=1, max_length=256)
    entity_kind: Literal["NODE", "EDGE"]
    entity_id: str = Field(min_length=1, max_length=512)
    operation: Literal["SUGGEST", "CREATE", "REVIEW", "STUDENT_PATCH", "DELETE"]
    base_revision: int = Field(ge=0, le=2_000_000_000)
    occurred_at: str = Field(min_length=20, max_length=64)
    payload: dict[str, object]


class KnowledgeGraphEventBatch(BaseModel):
    events: list[KnowledgeGraphEventRequest] = Field(min_length=1, max_length=MAX_GRAPH_EVENTS_PER_REQUEST)


class KnowledgeGraphProposalRequest(KnowledgeGraphEventRequest):
    """PC analysis ingress. It targets one already paired phone graph."""

    device_id: str = Field(min_length=1, max_length=160)


@dataclass
class AgentRun:
    run_id: str
    device_id: str
    client_request_id: str
    mode: str
    state: str
    created_at: str
    answer: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    artifact_path: Path | None = None
    artifact_sha256: str | None = None
    artifact_mime_type: str | None = None


class GatewayStore:
    """SQLite adapter; all durable delivery state is scoped by device and ID."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.Lock()
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL,
                    token_expires_at TEXT NOT NULL,
                    paired_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    device_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    state TEXT NOT NULL,
                    lease_token TEXT,
                    lease_until TEXT,
                    delivery_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    acknowledged_at TEXT,
                    PRIMARY KEY(device_id, message_id)
                );
                CREATE INDEX IF NOT EXISTS outbox_delivery ON outbox(device_id, state, expires_at, lease_until, created_at);
                CREATE TABLE IF NOT EXISTS agent_resources (
                    device_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    mime_type TEXT,
                    sha256 TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    text_excerpt TEXT,
                    error_message TEXT,
                    uploaded_at TEXT NOT NULL,
                    PRIMARY KEY(device_id, resource_id)
                );
                CREATE TABLE IF NOT EXISTS knowledge_graph_events (
                    server_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    entity_kind TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    base_revision INTEGER NOT NULL,
                    resulting_revision INTEGER NOT NULL,
                    occurred_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    UNIQUE(device_id, event_id)
                );
                CREATE INDEX IF NOT EXISTS knowledge_graph_event_cursor
                    ON knowledge_graph_events(device_id, server_sequence);
                CREATE TABLE IF NOT EXISTS knowledge_graph_entities (
                    device_id TEXT NOT NULL,
                    entity_kind TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    deleted_at TEXT,
                    last_event_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(device_id, entity_kind, entity_id)
                );
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def pair(self, device_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = utc_now()
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO devices(device_id, token_hash, token_expires_at, paired_at, revoked_at)
                   VALUES(?, ?, ?, ?, NULL)
                   ON CONFLICT(device_id) DO UPDATE SET token_hash=excluded.token_hash,
                     token_expires_at=excluded.token_expires_at, paired_at=excluded.paired_at, revoked_at=NULL""",
                (device_id, sha256(token), iso(now + timedelta(seconds=PAIRING_CREDENTIAL_TTL_SECONDS)), iso(now)),
            )
        return token

    def paired_device(self, token: str) -> str | None:
        now_value = utc_now()
        now = iso(now_value)
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT device_id, token_hash, token_expires_at FROM devices WHERE revoked_at IS NULL"
            ).fetchall()
            for row in rows:
                if not hmac.compare_digest(row["token_hash"], sha256(token)):
                    continue
                # Upgrade valid historic short-lived pairings in place.  This
                # path is reachable only by possession of the existing secret
                # over the already pinned TLS channel; revoked devices never
                # enter this query.
                if parse_time(str(row["token_expires_at"])) <= now_value:
                    connection.execute(
                        "UPDATE devices SET token_expires_at=? WHERE device_id=? AND revoked_at IS NULL",
                        (iso(now_value + timedelta(seconds=PAIRING_CREDENTIAL_TTL_SECONDS)), row["device_id"]),
                    )
                return str(row["device_id"])
        return None

    def revoke(self, device_id: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE devices SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                (iso(utc_now()), device_id),
            )

    def enqueue(self, request: OutboxIngressRequest) -> str:
        payload_json = json.dumps(request.payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        if len(payload_json.encode("utf-8")) > MAX_OUTBOX_PAYLOAD_BYTES:
            raise ValueError("mobile_message_payload_too_large")
        now = utc_now()
        expires_at = parse_time(request.expires_at) if request.expires_at else now + timedelta(seconds=DEFAULT_MESSAGE_TTL_SECONDS)
        if expires_at <= now:
            raise ValueError("mobile_message_expired_at_ingress")
        with self._lock, self._connection() as connection:
            existing = connection.execute(
                "SELECT payload_sha256 FROM outbox WHERE device_id=? AND message_id=?", (request.device_id, request.message_id)
            ).fetchone()
            if existing is not None:
                if hmac.compare_digest(existing["payload_sha256"], sha256(payload_json)):
                    return "DUPLICATE"
                raise ValueError("mobile_message_id_payload_conflict")
            pending = connection.execute(
                "SELECT COUNT(*) FROM outbox WHERE device_id=? AND state IN ('PENDING','LEASED') AND expires_at > ?",
                (request.device_id, iso(now)),
            ).fetchone()[0]
            if pending >= MAX_OUTBOX_PER_DEVICE:
                raise ValueError("mobile_outbox_device_capacity_exceeded")
            connection.execute(
                """INSERT INTO outbox(device_id,message_id,payload_json,payload_sha256,created_at,expires_at,state)
                   VALUES(?,?,?,?,?,?, 'PENDING')""",
                (request.device_id, request.message_id, payload_json, sha256(payload_json), iso(now), iso(expires_at)),
            )
        return "QUEUED"

    def lease(self, device_id: str, limit: int) -> list[dict[str, object]]:
        now = utc_now()
        leased: list[dict[str, object]] = []
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE outbox SET state='EXPIRED', last_error='ttl_elapsed' WHERE device_id=? AND state IN ('PENDING','LEASED') AND expires_at <= ?",
                (device_id, iso(now)),
            )
            rows = connection.execute(
                """SELECT * FROM outbox WHERE device_id=? AND expires_at > ? AND
                   (state='PENDING' OR (state='LEASED' AND lease_until <= ?)) ORDER BY created_at LIMIT ?""",
                (device_id, iso(now), iso(now), limit),
            ).fetchall()
            for row in rows:
                delivery_token = secrets.token_urlsafe(24)
                connection.execute(
                    """UPDATE outbox SET state='LEASED', lease_token=?, lease_until=?, delivery_count=delivery_count+1
                       WHERE device_id=? AND message_id=?""",
                    (delivery_token, iso(now + timedelta(seconds=DELIVERY_LEASE_SECONDS)), device_id, row["message_id"]),
                )
                leased.append({
                    "message_id": row["message_id"], "payload": json.loads(row["payload_json"]),
                    "delivery_token": delivery_token, "expires_at": row["expires_at"],
                })
            connection.execute("COMMIT")
        return leased

    def acknowledge(self, device_id: str, message_id: str, delivery_token: str) -> bool:
        with self._lock, self._connection() as connection:
            updated = connection.execute(
                """UPDATE outbox SET state='ACKED', acknowledged_at=?, lease_token=NULL, lease_until=NULL
                   WHERE device_id=? AND message_id=? AND state='LEASED' AND lease_token=?""",
                (iso(utc_now()), device_id, message_id, delivery_token),
            ).rowcount
        return updated == 1

    def reject(self, device_id: str, message_id: str, delivery_token: str, reason: str, retryable: bool) -> bool:
        state = "PENDING" if retryable else "DEAD_LETTER"
        with self._lock, self._connection() as connection:
            updated = connection.execute(
                """UPDATE outbox SET state=?, last_error=?, lease_token=NULL, lease_until=NULL
                   WHERE device_id=? AND message_id=? AND state='LEASED' AND lease_token=?""",
                (state, reason, device_id, message_id, delivery_token),
            ).rowcount
        return updated == 1

    def append_graph_event(
        self,
        device_id: str,
        event: KnowledgeGraphEventRequest,
        actor: Literal["STUDENT", "PC_AI"],
    ) -> dict[str, object]:
        """Append one graph operation and atomically advance its entity revision.

        This intentionally stores mutations instead of accepting a client snapshot:
        an offline phone can retry safely and a stale write becomes an explicit
        conflict rather than silently replacing the learner's note.
        """
        parse_time(event.occurred_at)
        payload_json = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        if len(payload_json.encode("utf-8")) > MAX_GRAPH_EVENT_PAYLOAD_BYTES:
            raise ValueError("knowledge_graph_event_payload_too_large")
        if actor == "PC_AI":
            refs = event.payload.get("evidence_refs")
            if event.operation != "SUGGEST" or not isinstance(refs, list) or not refs:
                raise ValueError("pc_knowledge_suggestion_evidence_required")
        event_hash = sha256(
            json.dumps(
                {
                    "entity_kind": event.entity_kind,
                    "entity_id": event.entity_id,
                    "operation": event.operation,
                    "base_revision": event.base_revision,
                    "occurred_at": event.occurred_at,
                    "payload": event.payload,
                    "actor": actor,
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        now = iso(utc_now())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                duplicate = connection.execute(
                    "SELECT payload_sha256, server_sequence, resulting_revision FROM knowledge_graph_events WHERE device_id=? AND event_id=?",
                    (device_id, event.event_id),
                ).fetchone()
                if duplicate is not None:
                    if hmac.compare_digest(duplicate["payload_sha256"], event_hash):
                        connection.execute("COMMIT")
                        return {"event_id": event.event_id, "state": "DUPLICATE", "server_sequence": duplicate["server_sequence"], "revision": duplicate["resulting_revision"]}
                    raise ValueError("knowledge_graph_event_id_payload_conflict")
                entity = connection.execute(
                    "SELECT revision FROM knowledge_graph_entities WHERE device_id=? AND entity_kind=? AND entity_id=?",
                    (device_id, event.entity_kind, event.entity_id),
                ).fetchone()
                current_revision = 0 if entity is None else int(entity["revision"])
                if event.base_revision != current_revision:
                    connection.execute("COMMIT")
                    return {
                        "event_id": event.event_id,
                        "state": "CONFLICT",
                        "current_revision": current_revision,
                        "reason": "knowledge_graph_base_revision_conflict",
                    }
                next_revision = current_revision + 1
                cursor = connection.execute(
                    """INSERT INTO knowledge_graph_events(
                        device_id,event_id,entity_kind,entity_id,operation,actor,base_revision,resulting_revision,
                        occurred_at,received_at,payload_json,payload_sha256
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        device_id, event.event_id, event.entity_kind, event.entity_id, event.operation, actor,
                        event.base_revision, next_revision, event.occurred_at, now, payload_json, event_hash,
                    ),
                )
                deleted_at = now if event.operation == "DELETE" else None
                connection.execute(
                    """INSERT INTO knowledge_graph_entities(device_id,entity_kind,entity_id,revision,deleted_at,last_event_id,updated_at)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(device_id,entity_kind,entity_id) DO UPDATE SET revision=excluded.revision,
                       deleted_at=excluded.deleted_at,last_event_id=excluded.last_event_id,updated_at=excluded.updated_at""",
                    (device_id, event.entity_kind, event.entity_id, next_revision, deleted_at, event.event_id, now),
                )
                connection.execute("COMMIT")
                return {"event_id": event.event_id, "state": "ACKED", "server_sequence": cursor.lastrowid, "revision": next_revision}
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def list_graph_events(self, device_id: str, after: int, limit: int) -> dict[str, object]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT server_sequence,event_id,entity_kind,entity_id,operation,actor,base_revision,resulting_revision,
                   occurred_at,received_at,payload_json FROM knowledge_graph_events
                   WHERE device_id=? AND server_sequence>? ORDER BY server_sequence ASC LIMIT ?""",
                (device_id, after, limit),
            ).fetchall()
        events = [
            {
                "server_sequence": row["server_sequence"], "event_id": row["event_id"],
                "entity_kind": row["entity_kind"], "entity_id": row["entity_id"], "operation": row["operation"],
                "actor": row["actor"], "base_revision": row["base_revision"], "revision": row["resulting_revision"],
                "occurred_at": row["occurred_at"], "received_at": row["received_at"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]
        next_cursor = events[-1]["server_sequence"] if events else after
        return {"events": events, "next_cursor": next_cursor}

    def save_resource(
        self,
        device_id: str,
        resource_id: str,
        display_name: str,
        mime_type: str | None,
        expected_sha256: str,
        payload: bytes,
        document_python: Path,
    ) -> dict[str, object]:
        if len(payload) > MAX_RESOURCE_BYTES:
            raise ValueError("agent_resource_too_large")
        actual_sha256 = sha256(payload)
        if not hmac.compare_digest(actual_sha256, expected_sha256.lower()):
            raise ValueError("agent_resource_sha256_mismatch")
        suffix = Path(display_name).suffix.lower()
        resource_path = self._path.parent / "resources" / (actual_sha256 + suffix)
        resource_path.parent.mkdir(parents=True, exist_ok=True)
        resource_path.write_bytes(payload)
        excerpt, error = extract_resource_text(resource_path, display_name, mime_type, payload, document_python)
        state = "READY_FOR_AGENT" if excerpt else "FAILED"
        result = {
            "resource_id": resource_id, "display_name": display_name, "mime_type": mime_type,
            "sha256": actual_sha256, "byte_size": len(payload), "state": state,
            "error": error,
        }
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO agent_resources(device_id,resource_id,display_name,mime_type,sha256,byte_size,state,text_excerpt,error_message,uploaded_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(device_id,resource_id) DO UPDATE SET display_name=excluded.display_name,
                     mime_type=excluded.mime_type,sha256=excluded.sha256,byte_size=excluded.byte_size,state=excluded.state,
                     text_excerpt=excluded.text_excerpt,error_message=excluded.error_message,uploaded_at=excluded.uploaded_at""",
                (device_id, resource_id, display_name, mime_type, actual_sha256, len(payload), state, excerpt, error, iso(utc_now())),
            )
        return result

    def agent_resource_context(self, device_id: str, resource_ids: list[str]) -> str:
        if not resource_ids:
            return ""
        placeholders = ",".join("?" for _ in resource_ids)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT resource_id,display_name,text_excerpt,state FROM agent_resources WHERE device_id=? AND resource_id IN ({placeholders})",
                [device_id, *resource_ids],
            ).fetchall()
        by_id = {row["resource_id"]: row for row in rows}
        excerpts: list[str] = []
        for resource_id in resource_ids:
            row = by_id.get(resource_id)
            if row is None:
                excerpts.append(f"- {resource_id}: 未上传到已配对 PC，不能引用。")
            elif row["state"] != "READY_FOR_AGENT" or not row["text_excerpt"]:
                excerpts.append(f"- {row['display_name']}: 已上传但当前格式未完成可用解析，不能引用。")
            else:
                excerpts.append(f"[{row['display_name']}]\n{row['text_excerpt']}")
        return "\n\n".join(excerpts)


def build_app(settings: GatewaySettings) -> FastAPI:
    app = FastAPI(title="知行智学本地网关", version="1.1")
    store = GatewayStore(settings.resolved_database_path)
    capture_supervisor = LanCaptureSupervisor(settings)
    pairing_limiter = PairingRateLimiter()
    nearby_pairing = NearbyPairingWindow()
    # The launcher uses this narrowly-scoped supplier for UDP discovery.  It
    # exposes only a short-lived bootstrap token, never the static fallback
    # code or an authenticated device token.
    app.state.nearby_pairing = nearby_pairing
    app.state.gateway_settings = settings
    runs: dict[str, AgentRun] = {}
    client_requests: dict[tuple[str, str], str] = {}
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)

    def require_pairing(authorization: str | None = Header(default=None)) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, detail={"code": "mobile_auth_required"})
        device_id = store.paired_device(authorization.removeprefix("Bearer "))
        if device_id is None:
            raise HTTPException(401, detail={"code": "mobile_auth_invalid_or_expired"})
        return device_id

    def require_ingress_key(x_zhixing_ingress_key: str | None = Header(default=None)) -> None:
        if x_zhixing_ingress_key is None or not hmac.compare_digest(x_zhixing_ingress_key, settings.ingress_key):
            raise HTTPException(401, detail={"code": "pc_ingress_auth_invalid"})

    @app.post("/api/mobile-outbox/devices/pair")
    async def pair(request: PairRequest, http_request: Request) -> dict[str, object]:
        client_host = http_request.client.host if http_request.client is not None else "unknown"
        rate_key = f"{client_host}:{request.device_id}"
        if not pairing_limiter.allow(rate_key):
            raise HTTPException(429, detail={"code": "pairing_rate_limited"})
        if not (hmac.compare_digest(request.pairing_token, settings.pairing_code) or nearby_pairing.accepts(request.pairing_token)):
            pairing_limiter.record_failure(rate_key)
            raise HTTPException(403, detail={"code": "pairing_code_invalid"})
        pairing_limiter.clear(rate_key)
        token = store.pair(request.device_id)
        return {"device_id": request.device_id, "access_token": token, "expires_at": iso(utc_now() + timedelta(seconds=PAIRING_CREDENTIAL_TTL_SECONDS))}

    @app.delete("/api/mobile-outbox/devices/me", status_code=204)
    async def revoke_current_device(device_id: str = Depends(require_pairing)) -> Response:
        store.revoke(device_id)
        return Response(status_code=204)

    @app.post("/api/capture-sessions", status_code=202)
    async def start_capture_session(
        request: CaptureSessionStartRequest,
        http_request: Request,
        device_id: str = Depends(require_pairing),
    ) -> dict[str, object]:
        peer_host = http_request.client.host if http_request.client is not None else ""
        try:
            session = capture_supervisor.start(device_id, peer_host, request)
        except ValueError as error:
            raise HTTPException(422, detail={"code": str(error)}) from error
        return session.response()

    @app.get("/api/capture-sessions/{session_id}")
    async def capture_session_status(session_id: str, device_id: str = Depends(require_pairing)) -> dict[str, object]:
        session = capture_supervisor.get(device_id, session_id)
        if session is None:
            raise HTTPException(404, detail={"code": "capture_session_not_found"})
        return session.response()

    @app.post("/api/capture-sessions/{session_id}/stop", status_code=202)
    async def stop_capture_session(session_id: str, device_id: str = Depends(require_pairing)) -> dict[str, object]:
        session = capture_supervisor.stop(device_id, session_id)
        if session is None:
            raise HTTPException(404, detail={"code": "capture_session_not_found"})
        return session.response()

    @app.get("/api/mobile-outbox/messages")
    async def list_messages(device_id: str, limit: int = 20, paired_device: str = Depends(require_pairing)) -> dict[str, object]:
        if device_id != paired_device:
            raise HTTPException(403, detail={"code": "mobile_device_mismatch"})
        return {"messages": store.lease(device_id, min(max(limit, 1), 50))}

    @app.post("/api/mobile-outbox/messages", status_code=202)
    async def enqueue_message(request: OutboxIngressRequest, _: None = Depends(require_ingress_key)) -> dict[str, str]:
        payload = request.payload
        if payload.get("schema_version") != "mobile_result_message.v1":
            raise HTTPException(422, detail={"code": "mobile_message_schema_unsupported"})
        if payload.get("message_type") not in {"ANALYSIS_RESULT", "CANDIDATE_CARD"}:
            raise HTTPException(422, detail={"code": "mobile_message_type_unsupported"})
        try:
            return {"message_id": request.message_id, "state": store.enqueue(request)}
        except ValueError as error:
            raise HTTPException(422, detail={"code": str(error)}) from error

    @app.post("/api/mobile-outbox/messages/ack", status_code=204)
    async def acknowledge_message(request: AckRequest, paired_device: str = Depends(require_pairing)) -> Response:
        if request.device_id != paired_device:
            raise HTTPException(403, detail={"code": "mobile_device_mismatch"})
        if not store.acknowledge(request.device_id, request.message_id, request.delivery_token):
            raise HTTPException(409, detail={"code": "mobile_delivery_lease_invalid"})
        return Response(status_code=204)

    @app.post("/api/mobile-outbox/messages/nack", status_code=204)
    async def reject_message(request: NackRequest, paired_device: str = Depends(require_pairing)) -> Response:
        if request.device_id != paired_device:
            raise HTTPException(403, detail={"code": "mobile_device_mismatch"})
        if not store.reject(request.device_id, request.message_id, request.delivery_token, request.reason, request.retryable):
            raise HTTPException(409, detail={"code": "mobile_delivery_lease_invalid"})
        return Response(status_code=204)

    @app.post("/api/knowledge-graph/events")
    async def append_knowledge_graph_events(
        request: KnowledgeGraphEventBatch,
        device_id: str = Depends(require_pairing),
    ) -> dict[str, object]:
        results: list[dict[str, object]] = []
        for event in request.events:
            try:
                results.append(store.append_graph_event(device_id, event, "STUDENT"))
            except ValueError as error:
                results.append({"event_id": event.event_id, "state": "REJECTED", "reason": str(error)})
        return {"results": results}

    @app.post("/api/knowledge-graph/proposals", status_code=202)
    async def append_knowledge_graph_proposal(
        request: KnowledgeGraphProposalRequest,
        _: None = Depends(require_ingress_key),
    ) -> dict[str, object]:
        try:
            result = store.append_graph_event(request.device_id, request, "PC_AI")
        except ValueError as error:
            raise HTTPException(422, detail={"code": str(error)}) from error
        if result["state"] == "CONFLICT":
            raise HTTPException(409, detail={"code": result["reason"], "current_revision": result["current_revision"]})
        return result

    @app.get("/api/knowledge-graph/sync")
    async def sync_knowledge_graph(
        after: int = 0,
        limit: int = 200,
        device_id: str = Depends(require_pairing),
    ) -> dict[str, object]:
        if after < 0:
            raise HTTPException(422, detail={"code": "knowledge_graph_cursor_invalid"})
        return store.list_graph_events(device_id, after, min(max(limit, 1), 200))

    @app.put("/api/agent/resources/{resource_id}")
    async def upload_resource(
        resource_id: str,
        request: Request,
        device_id: str = Depends(require_pairing),
        x_resource_name: str | None = Header(default=None),
        x_resource_sha256: str | None = Header(default=None),
    ) -> dict[str, object]:
        if not x_resource_name or not x_resource_sha256 or len(x_resource_sha256) != 64:
            raise HTTPException(422, detail={"code": "agent_resource_metadata_invalid"})
        payload = await request.body()
        try:
            return store.save_resource(
                device_id=device_id, resource_id=resource_id, display_name=x_resource_name[:512],
                mime_type=request.headers.get("content-type", "").split(";", 1)[0] or None,
                expected_sha256=x_resource_sha256, payload=payload, document_python=settings.resolved_document_python,
            )
        except ValueError as error:
            raise HTTPException(422, detail={"code": str(error)}) from error

    @app.get("/api/agent/status")
    async def agent_status(_: str = Depends(require_pairing)) -> dict[str, object]:
        probe = await probe_selected_provider(settings)
        return {
            "state": probe["state"],
            "provider": settings.selected_provider,
            "model": settings.selected_model,
            "configured": settings.agent_available,
            "connectivity": probe["connectivity"],
            "error": probe["error"],
            "web_search": settings.search_available,
        }

    @app.post("/api/agent/runs")
    async def start_agent_run(request: AgentRunRequest, device_id: str = Depends(require_pairing)) -> dict[str, object]:
        existing_id = client_requests.get((device_id, request.client_request_id))
        if existing_id is not None:
            return serialize_run(runs[existing_id])
        run = AgentRun(uuid.uuid4().hex, device_id, request.client_request_id, request.mode, "RUNNING", iso(utc_now()))
        runs[run.run_id] = run
        client_requests[(device_id, request.client_request_id)] = run.run_id
        if request.mode == "WEB_SEARCH" and not settings.search_available:
            run.state, run.error_code, run.error_message = "FAILED", "search_provider_unconfigured", "PC 未配置合规的检索服务。"
            return serialize_run(run)
        if request.mode != "WEB_SEARCH" and not settings.agent_available:
            run.state, run.error_code, run.error_message = "FAILED", "agent_provider_unconfigured", "PC 未配置可用的模型服务。请在 PC 网关配置本地模型或 OpenAI 兼容服务。"
            return serialize_run(run)
        try:
            resource_text = store.agent_resource_context(device_id, [item.id for item in request.resources])
            run.answer = await search_searxng(settings, request.prompt) if request.mode == "WEB_SEARCH" else await ask_provider(settings, request, resource_text)
            if request.mode == "EXPORT_MARKDOWN":
                run.artifact_path, run.artifact_mime_type = write_markdown_artifact(settings, run, request), "text/markdown"
                run.artifact_sha256 = sha256_file(run.artifact_path)
            elif request.mode in {"EXPORT_DOCX", "EXPORT_PPTX", "EXPORT_PDF"}:
                run.artifact_path, run.artifact_mime_type = write_document_artifact(settings, run, request)
                run.artifact_sha256 = sha256_file(run.artifact_path)
            run.state = "SUCCEEDED"
        except AgentProviderError as error:
            run.state, run.error_code, run.error_message = "FAILED", error.code, error.public_message
        except (httpx.HTTPError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as error:
            run.state, run.error_code, run.error_message = "FAILED", "agent_provider_request_failed", safe_provider_error(error)
        return serialize_run(run)

    @app.get("/api/agent/runs/{run_id}")
    async def read_agent_run(run_id: str, device_id: str = Depends(require_pairing)) -> dict[str, object]:
        run = runs.get(run_id)
        if run is None or run.device_id != device_id:
            raise HTTPException(404, detail={"code": "agent_run_not_found"})
        return serialize_run(run)

    @app.get("/api/agent/artifacts/{run_id}/file")
    async def download_artifact(run_id: str, device_id: str = Depends(require_pairing)) -> FileResponse:
        run = runs.get(run_id)
        if run is None or run.device_id != device_id or run.artifact_path is None:
            raise HTTPException(404, detail={"code": "agent_artifact_not_found"})
        return FileResponse(run.artifact_path, media_type=run.artifact_mime_type or "application/octet-stream", filename=run.artifact_path.name)

    return app


class AgentProviderError(ValueError):
    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(code)
        self.code = code
        self.public_message = public_message


def provider_messages(request: AgentRunRequest, resource_text: str) -> list[dict[str, str]]:
    context_text = "\n\n".join(f"[{item.source} / {item.visit_id}] {item.title}\n{item.summary}\n证据引用：{', '.join(item.evidence_refs)}" for item in request.contexts)
    system = "你是知行智学的学习助手。仅基于用户明确提供的会话摘要和资料状态回答；不得把候选证据写成兴趣、能力、人格或医疗结论。若资料仍为 LOCAL_QUEUED，必须说明它尚未上传或解析。"
    user = f"用户任务：{request.prompt}\n\n发现会话：\n{context_text or '无'}\n\n已上传资料：\n{resource_text or '无'}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def ask_provider(settings: GatewaySettings, request: AgentRunRequest, resource_text: str) -> str:
    provider = settings.selected_provider
    if provider == "openai_compatible":
        try:
            return await ask_openai_compatible(settings, request, resource_text)
        except AgentProviderError:
            if settings.ai_provider != "auto" or not settings.cloud_failure_fallback_to_local or not settings.local_available:
                raise
            return await ask_ollama(settings, request, resource_text)
    if provider == "ollama":
        return await ask_ollama(settings, request, resource_text)
    raise AgentProviderError("agent_provider_unconfigured", "PC 未配置可用的模型服务。")


async def ask_ollama(settings: GatewaySettings, request: AgentRunRequest, resource_text: str) -> str:
    assert settings.ollama_base_url is not None and settings.ollama_model is not None
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(settings.ollama_base_url + "/api/chat", json={"model": settings.ollama_model, "stream": False, "messages": provider_messages(request, resource_text)})
            response.raise_for_status()
            content = response.json()["message"]["content"]
        except httpx.TimeoutException as error:
            raise AgentProviderError("agent_provider_timeout", "本地模型服务响应超时。") from error
        except httpx.HTTPStatusError as error:
            raise AgentProviderError("agent_provider_http_error", f"本地模型服务返回 HTTP {error.response.status_code}。") from error
        except (KeyError, TypeError, ValueError) as error:
            raise AgentProviderError("agent_provider_invalid_response", "本地模型服务返回了无法识别的响应。") from error
    if not isinstance(content, str) or not content.strip():
        raise AgentProviderError("agent_provider_empty_answer", "模型服务未返回可用文本。")
    return content.strip()


async def ask_openai_compatible(settings: GatewaySettings, request: AgentRunRequest, resource_text: str) -> str:
    assert settings.openai_base_url is not None and settings.openai_api_key is not None and settings.openai_model is not None
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                settings.openai_base_url + "/chat/completions",
                headers={"Authorization": "Bearer " + settings.openai_api_key},
                json={"model": settings.openai_model, "messages": provider_messages(request, resource_text), "temperature": 0.2},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException as error:
            raise AgentProviderError("agent_provider_timeout", "云端模型服务响应超时。") from error
        except httpx.HTTPStatusError as error:
            code = "agent_provider_unauthorized" if error.response.status_code in {401, 403} else "agent_provider_http_error"
            raise AgentProviderError(code, f"云端模型服务返回 HTTP {error.response.status_code}。") from error
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise AgentProviderError("agent_provider_invalid_response", "云端模型服务返回了无法识别的响应。") from error
    if isinstance(content, list):
        content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
    if not isinstance(content, str) or not content.strip():
        raise AgentProviderError("agent_provider_empty_answer", "云端模型服务未返回可用文本。")
    return content.strip()


async def search_searxng(settings: GatewaySettings, query: str) -> str:
    assert settings.search_base_url is not None
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        response = await client.get(settings.search_base_url + "/search", params={"q": query, "format": "json"})
        response.raise_for_status()
        results = response.json().get("results", [])
    if not isinstance(results, list):
        raise ValueError("search_provider_invalid_response")
    retrieved_at, evidence = iso(utc_now()), []
    for item in results[:5]:
        if not isinstance(item, dict):
            continue
        title, url, snippet = item.get("title"), item.get("url"), item.get("content")
        if all(isinstance(value, str) and value.strip() for value in (title, url, snippet)):
            evidence.append(f"- [{title.strip()}]({url.strip()})\n  {snippet.strip()}\n  检索时间：{retrieved_at}")
    if not evidence:
        raise ValueError("search_provider_no_results")
    return "\n".join(evidence)


async def probe_selected_provider(settings: GatewaySettings) -> dict[str, object]:
    provider = settings.selected_provider
    if provider is None:
        return {"state": "UNAVAILABLE", "connectivity": "UNCONFIGURED", "error": {"code": "agent_provider_unconfigured", "message": "PC 未配置可用的模型服务。"}}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if provider == "ollama":
                assert settings.ollama_base_url is not None
                response = await client.get(settings.ollama_base_url + "/api/tags")
            else:
                assert settings.openai_base_url is not None and settings.openai_api_key is not None
                response = await client.get(settings.openai_base_url + "/models", headers={"Authorization": "Bearer " + settings.openai_api_key})
            response.raise_for_status()
        return {"state": "READY", "connectivity": "REACHABLE", "error": None}
    except httpx.TimeoutException:
        return {"state": "UNAVAILABLE", "connectivity": "TIMEOUT", "error": {"code": "agent_provider_timeout", "message": "模型服务连接超时。"}}
    except httpx.HTTPStatusError as error:
        code = "agent_provider_unauthorized" if error.response.status_code in {401, 403} else "agent_provider_http_error"
        return {"state": "UNAVAILABLE", "connectivity": "HTTP_ERROR", "error": {"code": code, "message": f"模型服务返回 HTTP {error.response.status_code}。"}}
    except httpx.HTTPError:
        return {"state": "UNAVAILABLE", "connectivity": "UNREACHABLE", "error": {"code": "agent_provider_unreachable", "message": "无法连接模型服务。"}}


def safe_provider_error(error: Exception) -> str:
    """Never return provider URLs, API keys, or raw third-party response bodies to Android."""
    if isinstance(error, subprocess.TimeoutExpired):
        return "PC 文档生成任务超时。"
    if isinstance(error, subprocess.CalledProcessError):
        return "PC 文档生成任务失败。"
    return "模型服务或文档生成发生未预期错误。"


def write_markdown_artifact(settings: GatewaySettings, run: AgentRun, request: AgentRunRequest) -> Path:
    assert run.answer is not None
    path = settings.artifact_dir / f"zhixing-agent-{run.run_id}.md"
    path.write_text(f"# {request.prompt}\n\n{run.answer}\n", encoding="utf-8")
    return path


def write_document_artifact(settings: GatewaySettings, run: AgentRun, request: AgentRunRequest) -> tuple[Path, str]:
    assert run.answer is not None
    suffix, mime_type = {
        "EXPORT_DOCX": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "EXPORT_PPTX": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        "EXPORT_PDF": ("pdf", "application/pdf"),
    }[request.mode]
    worker = Path(__file__).with_name("document_worker.py")
    if not worker.is_file() or not settings.resolved_document_python.is_file():
        raise ValueError("agent_document_worker_unavailable")
    citations = [reference.title for reference in request.contexts]
    payload = {"title": request.prompt, "body": run.answer, "citations": citations}
    with tempfile.TemporaryDirectory(prefix="zhixing-agent-export-") as temp_dir:
        payload_path = Path(temp_dir) / "request.json"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        destination = settings.artifact_dir / f"zhixing-agent-{run.run_id}.{suffix}"
        completed = subprocess.run(
            [str(settings.resolved_document_python), str(worker), "export", "--format", suffix, "--input", str(payload_path), "--output", str(destination)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        if completed.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
            destination.unlink(missing_ok=True)
            raise ValueError("agent_document_generation_failed")
    return destination, mime_type


def extract_resource_text(
    source_path: Path,
    display_name: str,
    mime_type: str | None,
    payload: bytes,
    document_python: Path,
) -> tuple[str | None, str | None]:
    """Parse only formats we can genuinely cite; unsupported files remain non-citable."""
    normalized = display_name.lower()
    textual = (mime_type or "").startswith("text/") or normalized.endswith((".txt", ".md", ".csv", ".json"))
    if not textual and source_path.suffix.lower() not in {".pdf", ".docx", ".pptx"}:
        return None, "agent_resource_parser_unsupported"
    if source_path.suffix.lower() in {".pdf", ".docx", ".pptx"}:
        if not document_python.is_file():
            return None, "agent_document_worker_unavailable"
        with tempfile.TemporaryDirectory(prefix="zhixing-doc-") as temporary:
            output = Path(temporary) / "parse.json"
            result = subprocess.run(
                [str(document_python), str(Path(__file__).with_name("document_worker.py")), "parse", "--input", str(source_path), "--output", str(output)],
                capture_output=True, text=True, encoding="utf-8", timeout=90,
            )
            if result.returncode != 0 or not output.is_file():
                return None, "agent_document_parse_failed"
            report = json.loads(output.read_text(encoding="utf-8"))
            items = report.get("chunks", [])
            if not isinstance(items, list) or not items:
                return None, str(report.get("error") or "agent_resource_no_extractable_text")
            text = "\n\n".join(f"[{item.get('locator', '资料')}] {item.get('text', '')}" for item in items if isinstance(item, dict))
            return text[:40_000].strip() or None, None
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None, "agent_resource_utf8_required"
    compact = decoded.strip()
    if not compact:
        return None, "agent_resource_empty"
    return compact[:40_000], None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def serialize_run(run: AgentRun) -> dict[str, object]:
    payload: dict[str, object] = {"run_id": run.run_id, "state": run.state, "created_at": run.created_at, "answer": run.answer, "error": None if run.error_code is None else {"code": run.error_code, "message": run.error_message}}
    if run.artifact_path is not None:
        payload["artifact"] = {"run_id": run.run_id, "display_name": run.artifact_path.name, "mime_type": run.artifact_mime_type or "application/octet-stream", "sha256": run.artifact_sha256, "download_path": f"/api/agent/artifacts/{run.run_id}/file"}
    return payload


app = build_app(GatewaySettings.from_environment()) if os.environ.get("ZHIXING_PAIRING_CODE") else None
