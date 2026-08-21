"""Paired-PC gateway for the 知行智学 mobile application.

The gateway deliberately separates three boundaries: a paired-device control
plane, a durable analysis outbox, and the optional AI workspace.  The outbox
is SQLite-backed: delivery is at-least-once, ACK happens only after Android
has persisted a message, and invalid messages enter an auditable dead letter
state instead of silently disappearing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import ctypes
from ctypes import wintypes
import secrets
import sqlite3
import subprocess
import sys
import threading
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

try:  # Support both ``python scripts/local_agent_gateway.py`` and package imports in tests.
    from .capture_session_policy import CaptureMode, CaptureOutputDecision, CaptureOutputState, CaptureSessionPolicy
    from .realtime_runtime.media_security import (
        MediaFragmentEnvelope,
        MediaFragmentHeader,
        MediaSecurityAuthority,
        MediaSecurityOpenRequest,
    )
    from .realtime_runtime.media_buffer import PcBufferResumeCursor, PcMediaBuffer
    from .realtime_runtime.v2_l0_media_processor import (
        V2L0MediaProcessor,
        V2L0MediaProcessorError,
        V2L0ProcessingDispatcher,
    )
except ImportError:  # pragma: no cover - exercised by the direct script entrypoint on Windows.
    from capture_session_policy import CaptureMode, CaptureOutputDecision, CaptureOutputState, CaptureSessionPolicy
    from realtime_runtime.media_security import (
        MediaFragmentEnvelope,
        MediaFragmentHeader,
        MediaSecurityAuthority,
        MediaSecurityOpenRequest,
    )
    from realtime_runtime.media_buffer import PcBufferResumeCursor, PcMediaBuffer
    from realtime_runtime.v2_l0_media_processor import (
        V2L0MediaProcessor,
        V2L0MediaProcessorError,
        V2L0ProcessingDispatcher,
    )


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
MAX_DELIVERY_RETRIES = 5
INITIAL_DELIVERY_RETRY_DELAY_SECONDS = 2
MAX_DELIVERY_RETRY_DELAY_SECONDS = 5 * 60
# This is a user-approved, TLS-pinned device pairing credential rather than a
# browser login session.  An eight-hour expiry made a phone silently lose its
# automatic PC connection after an overnight pause and forced needless manual
# re-pairing.  Revocation remains immediate; planned annual renewal prevents a
# forgotten local credential from living forever.
PAIRING_CREDENTIAL_TTL_SECONDS = 365 * 24 * 60 * 60
PAIRING_ATTEMPT_WINDOW_SECONDS = 5 * 60
PAIRING_ATTEMPT_LIMIT = 5
NEARBY_PAIRING_WINDOW_SECONDS = 120
V2_ACCESS_TOKEN_TTL_SECONDS = 15 * 60
V2_PROOF_CLOCK_SKEW_MS = 60 * 1000
V2_PROOF_NONCE_TTL_SECONDS = 5 * 60
V2_MEDIA_SECURITY_SESSION_TTL_MS = 10 * 60 * 1000


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


def build_v2_device_proof_payload(
    *,
    method: str,
    path: str,
    device_id: str,
    timestamp_ms: int,
    nonce: str,
    body_sha256: str | None,
) -> bytes:
    """Canonical bytes signed by the non-exportable Android credential.

    A proof always names its HTTP method and target path, so a valid refresh
    signature cannot be replayed as a capture, revoke, or media request.
    ``body_sha256`` is reserved for future signed v2 writes; the token refresh
    body is empty and therefore uses the canonical SHA-256 of empty bytes.
    """

    if (
        method.upper() != method
        or not path.startswith("/api/v2/")
        or not device_id
        or "\n" in device_id
        or type(timestamp_ms) is not int
        or timestamp_ms < 0
        or len(nonce) < 16
        or len(nonce) > 256
        or any(character in nonce for character in "\r\n")
    ):
        raise ValueError("v2_device_proof_payload_invalid")
    digest = body_sha256 or sha256(b"")
    if len(digest) != 64:
        raise ValueError("v2_device_proof_body_hash_invalid")
    return (
        "ZHIXING_DEVICE_PROOF.v2\n"
        f"{method}\n{path}\n{device_id}\n{timestamp_ms}\n{nonce}\n{digest}\n"
    ).encode("utf-8")


def _decode_v2_device_public_key(public_key_spki_b64: str) -> bytes:
    """Accept only an Android-compatible P-256 public key in SPKI DER form."""

    try:
        encoded = base64.b64decode(public_key_spki_b64, validate=True)
        key = serialization.load_der_public_key(encoded)
    except (TypeError, ValueError) as error:
        raise ValueError("v2_device_public_key_invalid") from error
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("v2_device_public_key_curve_unsupported")
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


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
    # The v2 Android egress posts encrypted codec frames directly to this
    # gateway.  The historical RTSP pull runner writes clear audio/video
    # working files and therefore must never be enabled by default.
    legacy_rtsp_ingress_enabled: bool = False

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
            legacy_rtsp_ingress_enabled=os.environ.get("ZHIXING_ENABLE_LEGACY_RTSP_INGRESS", "").strip().lower() in {"1", "true", "yes"},
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


class V2DeviceCredentialEnrollmentRequest(PairRequest):
    """Bootstrap only: pairing code plus the Android Keystore public key."""

    public_key_spki_b64: str = Field(min_length=32, max_length=2048)


class V2MediaSecurityOpenIngress(BaseModel):
    """Authenticated ECDH open request for the v2 media data plane."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=160)
    learner_id: str = Field(min_length=1, max_length=256)
    capture_session_id: str = Field(min_length=1, max_length=160)
    capture_consent_id: str = Field(min_length=1, max_length=160)
    consent_generation: int = Field(ge=1)
    route_lease_id: str = Field(min_length=1, max_length=160)
    route_epoch: int = Field(ge=1)
    capture_epoch: int = Field(default=1, ge=1)
    client_ephemeral_spki_b64: str = Field(min_length=32, max_length=2048)
    signature_b64: str = Field(min_length=8, max_length=1024)


class V2MediaFragmentHeaderIngress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_security_session_id: str = Field(min_length=24, max_length=128)
    learner_id: str = Field(min_length=1, max_length=256)
    capture_session_id: str = Field(min_length=1, max_length=160)
    capture_consent_id: str = Field(min_length=1, max_length=160)
    consent_generation: int = Field(ge=1)
    route_lease_id: str = Field(min_length=1, max_length=160)
    route_epoch: int = Field(ge=1)
    sequence: int = Field(ge=0)
    pts_start_us: int = Field(ge=0)
    pts_end_us: int = Field(ge=0)
    media_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    capture_epoch: int = Field(default=1, ge=1)


class V2MediaFragmentIngress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: V2MediaFragmentHeaderIngress
    nonce_b64: str = Field(min_length=16, max_length=32)
    ciphertext_b64: str = Field(min_length=24, max_length=16 * 1024 * 1024)
    # Kept at the envelope level so the durable PC buffer can fence a resumed
    # capture epoch.  Default 1 preserves the pre-buffer wire fixture; new
    # Android clients must send the real capture epoch.
    capture_epoch: int = Field(default=1, ge=1)


class V2MediaResumeCursorIngress(BaseModel):
    epoch: int = Field(ge=1)
    sequence: int = Field(ge=-1)
    range_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class V2MediaResumeIngress(BaseModel):
    learner_id: str = Field(min_length=1, max_length=256)
    capture_session_id: str = Field(min_length=1, max_length=160)
    capture_consent_id: str = Field(min_length=1, max_length=160)
    consent_generation: int = Field(ge=1)
    route_lease_id: str = Field(min_length=1, max_length=160)
    route_epoch: int = Field(ge=1)
    capture_epoch: int = Field(ge=1)
    owner_endpoint_id: str = Field(min_length=1, max_length=160)
    resume_attempt_id: str = Field(min_length=1, max_length=160)
    cursor: V2MediaResumeCursorIngress | None = None


class V2MediaAckIngress(BaseModel):
    learner_id: str = Field(min_length=1, max_length=256)
    capture_session_id: str = Field(min_length=1, max_length=160)
    capture_consent_id: str = Field(min_length=1, max_length=160)
    consent_generation: int = Field(ge=1)
    route_epoch: int = Field(ge=1)
    capture_epoch: int = Field(ge=1)
    sequence: int = Field(ge=0)


class CaptureSessionStartRequest(BaseModel):
    """Phone asks its already-paired PC to pull the *current* local RTSP server.

    The phone never supplies a free-form URL.  The gateway derives the source
    host from the authenticated TLS peer so this endpoint cannot become an
    SSRF primitive.
    """

    session_id: str = Field(min_length=1, max_length=160)
    # A mobile control-plan generation fences stale service work after the
    # foreground service has rebuilt a capture plan.  It is deliberately not
    # called a consent generation: this legacy capture route is not a v2
    # consent/media-security handshake.
    capture_generation: int = Field(ge=1)
    rtsp_port: int = Field(ge=1, le=65535)
    rtsp_path: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._~-]+$")
    source: Literal["PHONE_SCREEN"] = "PHONE_SCREEN"
    capture_mode: CaptureMode = CaptureMode.FULL_CONTINUOUS
    selected_packages: list[str] = Field(default_factory=list, max_length=32)
    # v2 binding is present only for a capture explicitly started from the
    # current Android consent snapshot. Legacy requests remain L0/RTSP-only.
    learner_id: str | None = Field(default=None, min_length=1, max_length=256)
    capture_consent_id: str | None = Field(default=None, min_length=1, max_length=160)
    consent_generation: int | None = Field(default=None, ge=1)
    capture_epoch: int | None = Field(default=None, ge=1)


class ForegroundAppObservationRequest(BaseModel):
    package_name: str | None = Field(default=None, min_length=1, max_length=240, pattern=r"^[A-Za-z0-9._-]+$")
    observation_source: Literal["ACCESSIBILITY", "USAGE_STATS", "LOCAL_UI"]


class AudioCapabilitySnapshotRequest(BaseModel):
    """Technical audio telemetry for one authenticated capture control plan.

    This stores what the handset observed.  It must not be treated as a v2
    media admission or as proof that playback audio is semantically complete.
    """

    snapshot_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._~-]+$")
    capture_generation: int = Field(ge=1)
    capture_path: Literal["NONE", "PLAYBACK", "MICROPHONE", "MIXED"]
    status: Literal["NOT_REQUESTED", "CAPTURE_ACTIVE_UNVERIFIED", "UNRESOLVED"]
    application_package_id: str | None = Field(default=None, min_length=1, max_length=240, pattern=r"^[A-Za-z0-9._-]+$")
    restriction: Literal[
        "NONE", "APPLICATION_DISALLOWED", "DRM_PROTECTED", "SYSTEM_POLICY",
        "PERMISSION_DENIED", "CAPTURE_FAILURE", "UNKNOWN",
    ]
    failure_code: str | None = Field(default=None, min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    video_pts_start_us: int = Field(ge=0)
    video_pts_end_us: int = Field(ge=0)
    audio_pts_start_us: int | None = Field(default=None, ge=0)
    audio_pts_end_us: int | None = Field(default=None, ge=0)
    session_epoch_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._~-]+$")
    clock_domain: Literal["ANDROID_ELAPSED_REALTIME_MONOTONIC"]
    anchor_elapsed_realtime_ns: int = Field(ge=0)
    sync_error_us: int | None = Field(default=None, ge=0)
    recovery_attempt: int = Field(ge=0, le=1_000_000)

    @model_validator(mode="after")
    def _validate_media_ranges(self) -> "AudioCapabilitySnapshotRequest":
        if self.video_pts_end_us < self.video_pts_start_us:
            raise ValueError("capture_audio_video_pts_range_invalid")
        if (self.audio_pts_start_us is None) != (self.audio_pts_end_us is None):
            raise ValueError("capture_audio_pts_range_incomplete")
        if self.audio_pts_start_us is not None and self.audio_pts_end_us is not None:
            if self.audio_pts_end_us < self.audio_pts_start_us:
                raise ValueError("capture_audio_pts_range_invalid")
        if self.capture_path == "NONE":
            if self.status != "NOT_REQUESTED" or self.audio_pts_start_us is not None or self.sync_error_us is not None:
                raise ValueError("capture_audio_none_state_invalid")
        elif self.status == "NOT_REQUESTED":
            raise ValueError("capture_audio_requested_state_invalid")
        elif self.status == "UNRESOLVED":
            if self.restriction == "NONE":
                raise ValueError("capture_audio_unresolved_requires_restriction")
            if not self.failure_code:
                raise ValueError("capture_audio_unresolved_requires_failure_code")
        elif self.restriction != "NONE" or self.failure_code is not None:
            raise ValueError("capture_audio_active_has_unresolved_claim")
        return self


@dataclass
class CaptureSession:
    session_id: str
    device_id: str
    rtsp_url: str
    output_dir: Path
    state: str
    started_at: str
    process: subprocess.Popen[str] | None = None
    stop_signal_file: Path | None = None
    stopped_at: str | None = None
    error: str | None = None
    policy: CaptureSessionPolicy = CaptureSessionPolicy.create(CaptureMode.FULL_CONTINUOUS, ())
    last_foreground_package: str | None = None
    capture_output_state: CaptureOutputState = CaptureOutputState.STREAMING_ALLOWED
    interruption_reason: str | None = None
    preserve_completed_evidence: bool = True
    capture_generation: int = 1
    media_route_lease_id: str | None = None
    media_route_epoch: int = 1
    learner_id: str | None = None
    capture_consent_id: str | None = None
    consent_generation: int | None = None
    # The media-security epoch belongs to the user's current capture consent.
    # It is intentionally independent of ``capture_generation``, which only
    # fences PC runner / RTSP recovery work.
    authorization_capture_epoch: int | None = None
    # True only for a session whose live data plane is the encrypted v2
    # callback egress, rather than the retired RTSP pull runner.
    direct_v2_egress: bool = False

    @property
    def audit_path(self) -> Path:
        return self.output_dir.parent / f"{self.output_dir.name}.capture-audit.jsonl"

    @property
    def audio_telemetry_journal_path(self) -> Path:
        """Append-only L0 telemetry adjacent to, never inside, runner output.

        The journal may arrive before the runner creates ``output_dir``.  It
        must therefore not create that directory and race the runner's unique
        output ownership check.
        """

        return self.output_dir.parent / f".{self.output_dir.name}.audio-l0.jsonl"

    def append_audit(self, event: dict[str, object]) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")

    def append_audio_telemetry(self, event: dict[str, object]) -> None:
        self.audio_telemetry_journal_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audio_telemetry_journal_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def response(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "rtsp_url": self.rtsp_url,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "error": self.error,
            "capture_mode": self.policy.mode.value,
            "selected_packages": list(self.policy.selected_packages),
            "media_route_lease_id": self.media_route_lease_id,
            "media_route_epoch": self.media_route_epoch,
            "capture_epoch": self.authorization_capture_epoch or self.capture_generation,
            "learner_id": self.learner_id,
            "capture_consent_id": self.capture_consent_id,
            "consent_generation": self.consent_generation,
            "foreground_package": self.last_foreground_package,
            "capture_output_state": self.capture_output_state.value,
            "interruption_reason": self.interruption_reason,
            "preserve_completed_evidence": self.preserve_completed_evidence,
            "capture_generation": self.capture_generation,
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

    def _owner_lock_file(self, device_id: str) -> Path:
        # This is a per-paired-device ownership lease, intentionally outside a
        # unique session output directory.  A replacement gateway must see an
        # older runner that is still settling the same phone's RTSP source.
        digest = hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:24]
        return self._settings.resolved_realtime_output_dir / ".capture-owners" / f"{digest}.json"

    @staticmethod
    def _process_is_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return ctypes.get_last_error() == 5
            try:
                exit_code = wintypes.DWORD()
                return bool(
                    kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                    and exit_code.value == 259
                )
            finally:
                kernel32.CloseHandle(handle)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _owner_is_active(self, device_id: str) -> bool:
        lock_file = self._owner_lock_file(device_id)
        try:
            payload = json.loads(lock_file.read_text(encoding="utf-8"))
            pid = int(payload["pid"])
        except (FileNotFoundError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            lock_file.unlink(missing_ok=True)
            return False
        if self._process_is_alive(pid):
            return True
        # A strongly killed runner cannot execute its cleanup finally.  Its
        # stale lease is safe to remove only after its recorded PID is gone.
        lock_file.unlink(missing_ok=True)
        return False

    def _spawn_runner_locked(self, session: CaptureSession) -> None:
        command = [
            sys.executable, str(self._settings.resolved_realtime_runner),
            "--source", session.rtsp_url,
            "--session-id", session.session_id,
            "--capture-generation", str(session.capture_generation),
            "--output-dir", str(session.output_dir),
            "--audio-telemetry-journal", str(session.audio_telemetry_journal_path),
            "--clock-host", session.rtsp_url.split("//", 1)[1].split(":", 1)[0].strip("[]"),
            "--stop-signal-file", str(session.stop_signal_file),
            "--supervisor-pid", str(os.getpid()),
            "--capture-owner-lock-file", str(self._owner_lock_file(session.device_id)),
        ]
        environment = os.environ.copy()
        if self._settings.gateway_ca_bundle is not None:
            environment["REQUESTS_CA_BUNDLE"] = str(self._settings.gateway_ca_bundle)
        session.output_dir.parent.mkdir(parents=True, exist_ok=True)
        log = session.output_dir.parent / f"{session.output_dir.name}.supervisor.log"
        handle = log.open("w", encoding="utf-8", newline="\n")
        try:
            session.process = subprocess.Popen(
                command,
                cwd=self._settings.resolved_realtime_runner.parent.parent,
                env=environment,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
        finally:
            handle.close()
        threading.Thread(target=self._watch, args=((session.device_id, session.session_id),), daemon=True, name=f"capture-{session.session_id}").start()

    def _wait_for_previous_owner_then_start(self, key: tuple[str, str]) -> None:
        deadline = time.monotonic() + 180.0
        while self._owner_is_active(key[0]) and time.monotonic() < deadline:
            time.sleep(0.5)
        with self._lock:
            session = self._sessions.get(key)
            if session is None or session.state == "STOPPING":
                return
            if self._owner_is_active(key[0]):
                session.state = "FAILED_SETTLEMENT"
                session.error = "previous_capture_owner_did_not_exit"
                return
            try:
                self._spawn_runner_locked(session)
            except OSError as error:
                session.state = "FAILED_RUNTIME_NOT_READY"
                session.error = f"runner_start_failed:{error.__class__.__name__}"

    def start(self, device_id: str, peer_host: str, request: CaptureSessionStartRequest) -> CaptureSession:
        key = (device_id, request.session_id)
        with self._lock:
            existing = self._sessions.get(key)
            if existing is not None and existing.state in {"STARTING", "RUNNING", "STOPPING"}:
                return existing
            rtsp_url = self._rtsp_url(peer_host, request.rtsp_port, request.rtsp_path)
            policy = CaptureSessionPolicy.create(request.capture_mode, tuple(request.selected_packages))
            now = utc_now()
            output_dir = self._settings.resolved_realtime_output_dir / f"{request.session_id}-{now.strftime('%Y%m%dT%H%M%SZ')}"
            session = CaptureSession(
                request.session_id, device_id, rtsp_url, output_dir, "STARTING", iso(now),
                policy=policy, capture_generation=request.capture_generation,
                media_route_lease_id=secrets.token_urlsafe(24),
                learner_id=request.learner_id,
                capture_consent_id=request.capture_consent_id,
                consent_generation=request.consent_generation,
                authorization_capture_epoch=request.capture_epoch,
            )
            # This signal deliberately lives *next to* the runner's output
            # directory.  Creating it before a just-spawned runner reaches
            # output.mkdir(exist_ok=False) must not itself make that runner
            # fail with FileExistsError.
            session.stop_signal_file = output_dir.parent / f".{output_dir.name}.stop-requested"
            self._sessions[key] = session
            # The Android process still owns an RTSP encoder internally, but
            # v2 egress consumes the encoded callbacks and sends encrypted
            # frames over the paired HTTPS channel.  Do not start the former
            # PC RTSP pull runner beside it: that route creates plaintext
            # media work files and duplicates the same capture.
            if not self._settings.legacy_rtsp_ingress_enabled:
                if (
                    not request.learner_id or not request.capture_consent_id or
                    request.consent_generation is None or request.capture_epoch is None
                ):
                    session.state = "FAILED_LEGACY_RTSP_DISABLED"
                    session.error = "v2_capture_binding_required"
                else:
                    session.state = "RUNNING"
                    session.direct_v2_egress = True
                return session
            if not self._settings.resolved_realtime_runner.is_file():
                session.state = "FAILED_RUNTIME_NOT_READY"
                session.error = "realtime_runner_missing"
                return session
            if self._owner_is_active(device_id):
                session.state = "RECOVERING"
                session.error = "previous_capture_owner_settling"
                threading.Thread(
                    target=self._wait_for_previous_owner_then_start,
                    args=(key,),
                    daemon=True,
                    name=f"capture-recovery-{request.session_id}",
                ).start()
                return session
            try:
                self._spawn_runner_locked(session)
            except OSError as error:
                session.state = "FAILED_RUNTIME_NOT_READY"
                session.error = f"runner_start_failed:{error.__class__.__name__}"
            return session

    def media_route(self, device_id: str, session_id: str) -> tuple[str, int, int, str, str, int] | None:
        """Return only a live PC-issued route lease, never caller-supplied route text."""
        with self._lock:
            session = self._sessions.get((device_id, session_id))
            if (
                session is None
                or session.state not in {"STARTING", "RUNNING"}
                or not session.media_route_lease_id
                or not session.learner_id
                or not session.capture_consent_id
                or session.consent_generation is None
                or session.authorization_capture_epoch is None
            ):
                return None
            return (
                session.media_route_lease_id, session.media_route_epoch, session.authorization_capture_epoch,
                session.learner_id, session.capture_consent_id, session.consent_generation,
            )

    @contextmanager
    def v2_media_ingress_permit(self, device_id: str, session_id: str) -> Iterator[None]:
        """Serialize a selected-app gate change with encrypted-buffer persistence."""
        with self._lock:
            session = self._sessions.get((device_id, session_id))
            if session is None or session.state not in {"STARTING", "RUNNING"}:
                raise ValueError("media_capture_route_not_available")
            if (
                session.policy.mode == CaptureMode.SELECTED_APPS and
                session.capture_output_state != CaptureOutputState.STREAMING_ALLOWED
            ):
                session.append_audit(
                    {
                        "event_type": "V2_MEDIA_FRAGMENT_REJECTED_BY_OUTPUT_GATE",
                        "observed_at": iso(utc_now()),
                        "session_id": session.session_id,
                        "device_id": session.device_id,
                        "capture_output_state": session.capture_output_state.value,
                    }
                )
                raise ValueError("media_capture_output_blocked")
            yield

    def observe_foreground_app(
        self,
        device_id: str,
        session_id: str,
        package_name: str | None,
        observation_source: str = "DEVICE_REPORTED",
    ) -> CaptureOutputDecision:
        """Record the device-observed foreground app without ending capture.

        In ``SELECTED_APPS`` mode the Android sender consumes the returned
        decision to stop emitting media while an unselected application is
        foreground.  The capture session itself remains authorized and alive,
        so returning to a selected application does not require another
        MediaProjection consent prompt.
        """
        with self._lock:
            session = self._sessions.get((device_id, session_id))
            if session is None:
                raise KeyError("capture_session_not_found")
            if session.state not in {"STARTING", "RUNNING"}:
                raise ValueError("capture_session_not_active")
            session.last_foreground_package = package_name
            decision = session.policy.decide(package_name)
            session.capture_output_state = decision.output_state
            session.append_audit(
                {
                    "event_type": "FOREGROUND_APP_OBSERVED",
                    "observed_at": iso(utc_now()),
                    "session_id": session.session_id,
                    "device_id": session.device_id,
                    "capture_mode": session.policy.mode.value,
                    "foreground_package": package_name,
                    "observation_source": observation_source,
                    "capture_output_state": decision.output_state.value,
                    "decision_reason": decision.reason,
                }
            )
            return decision

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
            elif session.state.startswith("FAILED"):
                pass
            elif code == 0:
                # Production capture is unbounded.  A clean runner exit with
                # no user stop signal therefore means the PC observed a source
                # disconnect (for example an Android task clear).  Already
                # sealed fragments remain evidence; only the open tail is
                # incomplete.
                interruption = session.policy.interruption_outcome("PC_OBSERVED_SOURCE_DISCONNECT")
                session.state = interruption.session_state
                session.interruption_reason = interruption.reason
                session.preserve_completed_evidence = interruption.preserve_completed_evidence
            else:
                session.state = "FAILED"
                session.error = f"runner_exit_{code}"
            session.stopped_at = iso(utc_now())

    def _request_stop_locked(self, session: CaptureSession) -> None:
        if session.state in {"RUNNING", "STARTING", "RECOVERING"}:
            if session.direct_v2_egress:
                # Direct v2 ingress has no child runner or tail to settle.
                # Stop the control session immediately; already encrypted
                # fragments remain in the private buffer for audit/resume.
                session.state = "STOPPED"
                session.stopped_at = iso(utc_now())
                return
            # Phone stops its RTSP server first; the pipeline then closes
            # naturally and flushes its tail.  Do not kill a live runner
            # here, because that would discard its final evidence window.
            session.state = "STOPPING"
            if session.stop_signal_file is not None:
                session.stop_signal_file.parent.mkdir(parents=True, exist_ok=True)
                session.stop_signal_file.touch()

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
        """Last-resort cleanup for a runner and every lane it owns.

        `Popen.terminate()` kills only the Python runner on Windows.  Its OCR,
        ASR, VLM, ingress and publisher descendants would then survive without
        a supervisor.  A tail timeout is an explicit failed settlement, so its
        complete process tree must be removed before the next Android recovery
        is allowed to create another worker.
        """
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def stop(self, device_id: str, session_id: str) -> CaptureSession | None:
        with self._lock:
            session = self._sessions.get((device_id, session_id))
            if session is None:
                return None
            self._request_stop_locked(session)
            return session

    def revoke_device(self, device_id: str) -> tuple[CaptureSession, ...]:
        """Stop every non-terminal capture owned by a revoked paired device.

        Revocation must also stop a ``RECOVERING`` session: otherwise its
        delayed owner-lease recovery thread could start a new runner after the
        credential has been invalidated.  This uses the normal stop signal so
        the runner can seal its final window; it intentionally never deletes
        completed evidence.
        """

        with self._lock:
            sessions = tuple(
                session for (owner_device_id, _), session in self._sessions.items()
                if owner_device_id == device_id
            )
            for session in sessions:
                self._request_stop_locked(session)
            return sessions

    def shutdown(self, grace_seconds: float = 20.0) -> None:
        """Stop owned runners before the gateway process exits.

        An in-memory supervisor restart used to orphan its child runners on
        Windows.  A recovered Android client would then start another worker
        for the same RTSP source, duplicating analysis.  Shutdown therefore
        writes the same explicit stop signal as the phone path, waits for the
        tail window to settle, then records a failure if a runner cannot exit.
        """
        with self._lock:
            sessions = tuple(self._sessions.values())
            for session in sessions:
                self._request_stop_locked(session)
        deadline = time.monotonic() + max(0.0, grace_seconds)
        for session in sessions:
            process = session.process
            if process is None or process.poll() is not None:
                continue
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                self._terminate_process_tree(process)
                with self._lock:
                    session.state = "FAILED_SETTLEMENT"
                    session.error = "gateway_shutdown_tail_timeout"

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
                CREATE TABLE IF NOT EXISTS v2_device_credentials (
                    device_id TEXT PRIMARY KEY,
                    public_key_spki_der BLOB NOT NULL,
                    public_key_sha256 TEXT NOT NULL,
                    credential_generation INTEGER NOT NULL,
                    enrolled_at TEXT NOT NULL,
                    rotated_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS v2_access_tokens (
                    token_hash TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    credential_generation INTEGER NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT,
                    FOREIGN KEY(device_id) REFERENCES v2_device_credentials(device_id)
                );
                CREATE INDEX IF NOT EXISTS v2_access_tokens_device
                    ON v2_access_tokens(device_id, credential_generation, expires_at);
                CREATE TABLE IF NOT EXISTS v2_device_proof_nonces (
                    device_id TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    used_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY(device_id, nonce),
                    FOREIGN KEY(device_id) REFERENCES v2_device_credentials(device_id)
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
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    last_error TEXT,
                    acknowledged_at TEXT,
                    PRIMARY KEY(device_id, message_id)
                );
                CREATE INDEX IF NOT EXISTS outbox_delivery ON outbox(device_id, state, expires_at, lease_until, created_at);
                CREATE TABLE IF NOT EXISTS outbox_delivery_rejections (
                    rejection_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    delivery_token TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    retryable INTEGER NOT NULL CHECK(retryable IN (0, 1)),
                    retry_count INTEGER NOT NULL,
                    rejected_at TEXT NOT NULL,
                    next_attempt_at TEXT,
                    resulting_state TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS outbox_delivery_rejections_message
                    ON outbox_delivery_rejections(device_id, message_id, rejected_at);
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
                CREATE TABLE IF NOT EXISTS capture_audio_capability_snapshots (
                    device_id TEXT NOT NULL,
                    capture_session_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    capture_generation INTEGER NOT NULL,
                    capture_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    application_package_id TEXT,
                    restriction TEXT NOT NULL,
                    failure_code TEXT,
                    video_pts_start_us INTEGER NOT NULL,
                    video_pts_end_us INTEGER NOT NULL,
                    audio_pts_start_us INTEGER,
                    audio_pts_end_us INTEGER,
                    session_epoch_id TEXT NOT NULL,
                    clock_domain TEXT NOT NULL,
                    anchor_elapsed_realtime_ns INTEGER NOT NULL,
                    sync_error_us INTEGER,
                    recovery_attempt INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    admission TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    PRIMARY KEY(device_id, capture_session_id, snapshot_id)
                );
                CREATE INDEX IF NOT EXISTS capture_audio_capability_session_cursor
                    ON capture_audio_capability_snapshots(device_id, capture_session_id, capture_generation, received_at);
                """
            )
            self._add_outbox_state_columns(connection)
            self._add_capture_audio_capability_columns(connection)
            self._quarantine_legacy_delivery_rows(connection)

    @staticmethod
    def _add_outbox_state_columns(connection: sqlite3.Connection) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(outbox)").fetchall()
        }
        for name, sql_type in {
            "retry_count": "INTEGER NOT NULL DEFAULT 0",
            "next_attempt_at": "TEXT",
        }.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE outbox ADD COLUMN {name} {sql_type}")

    @staticmethod
    def _add_capture_audio_capability_columns(connection: sqlite3.Connection) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(capture_audio_capability_snapshots)").fetchall()
        }
        if columns and "failure_code" not in columns:
            connection.execute("ALTER TABLE capture_audio_capability_snapshots ADD COLUMN failure_code TEXT")

    @staticmethod
    def _quarantine_legacy_delivery_rows(connection: sqlite3.Connection) -> None:
        """Make historic v1 delivery rows auditable but permanently non-routable."""

        rows = connection.execute(
            "SELECT device_id, message_id, payload_json FROM outbox WHERE state IN ('PENDING', 'LEASED')"
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"]))
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("schema_version") == "mobile_result_message.v1":
                connection.execute(
                    """
                    UPDATE outbox
                    SET state='LEGACY_READ_ONLY', lease_token=NULL, lease_until=NULL,
                        last_error='legacy_v1_delivery_disabled'
                    WHERE device_id=? AND message_id=?
                    """,
                    (row["device_id"], row["message_id"]),
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

    @staticmethod
    def _issue_v2_access_token(
        connection: sqlite3.Connection,
        *,
        device_id: str,
        credential_generation: int,
        now: datetime,
    ) -> str:
        token = secrets.token_urlsafe(32)
        connection.execute(
            """
            INSERT INTO v2_access_tokens(token_hash, device_id, credential_generation, issued_at, expires_at, revoked_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (
                sha256(token), device_id, credential_generation, iso(now),
                iso(now + timedelta(seconds=V2_ACCESS_TOKEN_TTL_SECONDS)),
            ),
        )
        return token

    def enroll_v2_device_credential(self, device_id: str, public_key_spki_b64: str) -> tuple[str, int]:
        """Replace any old v2 key with a new, short-token credential generation."""

        public_key_der = _decode_v2_device_public_key(public_key_spki_b64)
        now = utc_now()
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT credential_generation FROM v2_device_credentials WHERE device_id=?", (device_id,)
                ).fetchone()
                generation = 1 if existing is None else int(existing["credential_generation"]) + 1
                connection.execute(
                    "UPDATE v2_access_tokens SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                    (iso(now), device_id),
                )
                connection.execute(
                    """
                    INSERT INTO v2_device_credentials(
                        device_id, public_key_spki_der, public_key_sha256, credential_generation,
                        enrolled_at, rotated_at, revoked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(device_id) DO UPDATE SET
                        public_key_spki_der=excluded.public_key_spki_der,
                        public_key_sha256=excluded.public_key_sha256,
                        credential_generation=excluded.credential_generation,
                        rotated_at=excluded.rotated_at,
                        revoked_at=NULL
                    """,
                    (device_id, public_key_der, sha256(public_key_der), generation, iso(now), iso(now)),
                )
                token = self._issue_v2_access_token(
                    connection, device_id=device_id, credential_generation=generation, now=now
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return token, generation

    def v2_authenticated_device(self, token: str) -> tuple[str, int] | None:
        """Resolve an unexpired, unrevoked v2 short token without extending it."""

        now = utc_now()
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """
                SELECT token.device_id, token.credential_generation, token.expires_at,
                       credential.credential_generation AS current_generation, credential.revoked_at
                FROM v2_access_tokens AS token
                JOIN v2_device_credentials AS credential ON credential.device_id=token.device_id
                WHERE token.token_hash=? AND token.revoked_at IS NULL
                """,
                (sha256(token),),
            ).fetchone()
        if (
            row is None
            or row["revoked_at"] is not None
            or int(row["credential_generation"]) != int(row["current_generation"])
            or parse_time(str(row["expires_at"])) <= now
        ):
            return None
        return str(row["device_id"]), int(row["credential_generation"])

    def v2_device_public_key(self, device_id: str) -> ec.EllipticCurvePublicKey | None:
        """Return only the enrolled public key for an active v2 credential."""

        with self._lock, self._connection() as connection:
            row = connection.execute(
                """
                SELECT public_key_spki_der FROM v2_device_credentials
                WHERE device_id=? AND revoked_at IS NULL
                """,
                (device_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            key = serialization.load_der_public_key(bytes(row["public_key_spki_der"]))
        except (TypeError, ValueError):
            return None
        return key if isinstance(key, ec.EllipticCurvePublicKey) and isinstance(key.curve, ec.SECP256R1) else None

    def rotate_v2_access_token(
        self,
        *,
        device_id: str,
        timestamp_ms: int,
        nonce: str,
        signature_b64: str,
    ) -> tuple[str, int]:
        """Rotate a short token only after a fresh, non-replayable key proof."""

        now = utc_now()
        now_ms = int(now.timestamp() * 1_000)
        if abs(now_ms - timestamp_ms) > V2_PROOF_CLOCK_SKEW_MS:
            raise ValueError("v2_device_proof_timestamp_out_of_window")
        try:
            signature = base64.b64decode(signature_b64, validate=True)
            payload = build_v2_device_proof_payload(
                method="POST",
                path="/api/v2/device-credentials/refresh",
                device_id=device_id,
                timestamp_ms=timestamp_ms,
                nonce=nonce,
                body_sha256=None,
            )
        except (TypeError, ValueError) as error:
            raise ValueError("v2_device_proof_invalid") from error
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                credential = connection.execute(
                    """
                    SELECT public_key_spki_der, credential_generation, revoked_at
                    FROM v2_device_credentials WHERE device_id=?
                    """,
                    (device_id,),
                ).fetchone()
                if credential is None or credential["revoked_at"] is not None:
                    raise ValueError("v2_device_credential_unavailable")
                try:
                    key = serialization.load_der_public_key(bytes(credential["public_key_spki_der"]))
                    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
                        raise ValueError("v2_device_credential_invalid")
                    key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
                except InvalidSignature as error:
                    raise ValueError("v2_device_proof_signature_invalid") from error
                except (TypeError, ValueError) as error:
                    raise ValueError("v2_device_credential_invalid") from error
                connection.execute(
                    "DELETE FROM v2_device_proof_nonces WHERE expires_at <= ?", (iso(now),)
                )
                try:
                    connection.execute(
                        """
                        INSERT INTO v2_device_proof_nonces(device_id, nonce, used_at, expires_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (device_id, nonce, iso(now), iso(now + timedelta(seconds=V2_PROOF_NONCE_TTL_SECONDS))),
                    )
                except sqlite3.IntegrityError as error:
                    raise ValueError("v2_device_proof_replayed") from error
                generation = int(credential["credential_generation"])
                connection.execute(
                    "UPDATE v2_access_tokens SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                    (iso(now), device_id),
                )
                token = self._issue_v2_access_token(
                    connection, device_id=device_id, credential_generation=generation, now=now
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return token, generation

    def revoke_v2_device_credential(self, device_id: str) -> None:
        now = iso(utc_now())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE v2_device_credentials SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                    (now, device_id),
                )
                connection.execute(
                    "UPDATE v2_access_tokens SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                    (now, device_id),
                )
                connection.execute(
                    """
                    UPDATE outbox
                    SET state='REVOKED', lease_token=NULL, lease_until=NULL,
                        next_attempt_at=NULL, last_error='device_revoked'
                    WHERE device_id=? AND state IN ('PENDING', 'LEASED', 'RETRY_WAIT')
                    """,
                    (device_id,),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def revoke(self, device_id: str) -> None:
        with self._lock, self._connection() as connection:
            now = iso(utc_now())
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE devices SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                (now, device_id),
            )
            connection.execute(
                "UPDATE v2_device_credentials SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                (now, device_id),
            )
            connection.execute(
                "UPDATE v2_access_tokens SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                (now, device_id),
            )
            connection.execute(
                """
                UPDATE outbox
                SET state='REVOKED', lease_token=NULL, lease_until=NULL,
                    next_attempt_at=NULL, last_error='device_revoked'
                WHERE device_id=? AND state IN ('PENDING', 'LEASED', 'RETRY_WAIT')
                """,
                (device_id,),
            )
            connection.execute("COMMIT")

    def record_capture_audio_capability(
        self,
        device_id: str,
        capture_session_id: str,
        request: AudioCapabilitySnapshotRequest,
    ) -> str:
        """Persist an immutable phone observation with retry-safe identity.

        Capture audio telemetry is intentionally stored independently from the
        v2 package/outbox.  Its only admission value is L0 technical evidence;
        no caller can convert it into L1 eligibility through this endpoint.
        """

        payload = request.model_dump(mode="json")
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        payload_hash = sha256(payload_json)
        now = iso(utc_now())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT payload_sha256 FROM capture_audio_capability_snapshots
                WHERE device_id=? AND capture_session_id=? AND snapshot_id=?
                """,
                (device_id, capture_session_id, request.snapshot_id),
            ).fetchone()
            if existing is not None:
                connection.execute("COMMIT")
                if hmac.compare_digest(str(existing["payload_sha256"]), payload_hash):
                    return "DUPLICATE"
                raise ValueError("capture_audio_snapshot_id_conflict")
            connection.execute(
                """
                INSERT INTO capture_audio_capability_snapshots(
                    device_id, capture_session_id, snapshot_id, capture_generation,
                    capture_path, status, application_package_id, restriction, failure_code,
                    video_pts_start_us, video_pts_end_us, audio_pts_start_us, audio_pts_end_us,
                    session_epoch_id, clock_domain, anchor_elapsed_realtime_ns, sync_error_us,
                    recovery_attempt, payload_json, payload_sha256, admission, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id, capture_session_id, request.snapshot_id, request.capture_generation,
                    request.capture_path, request.status, request.application_package_id, request.restriction, request.failure_code,
                    request.video_pts_start_us, request.video_pts_end_us,
                    request.audio_pts_start_us, request.audio_pts_end_us,
                    request.session_epoch_id, request.clock_domain, request.anchor_elapsed_realtime_ns,
                    request.sync_error_us, request.recovery_attempt, payload_json, payload_hash,
                    "L0_ONLY_NO_V2_CONSENT", now,
                ),
            )
            connection.execute("COMMIT")
        return "CAPTURE_AUDIO_TELEMETRY_ACCEPTED"

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
                "SELECT COUNT(*) FROM outbox WHERE device_id=? AND state IN ('PENDING','LEASED','RETRY_WAIT') AND expires_at > ?",
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
            # A restored or externally recovered SQLite file must not revive a
            # v1 delivery after process startup.
            self._quarantine_legacy_delivery_rows(connection)
            connection.execute(
                "UPDATE outbox SET state='EXPIRED', last_error='ttl_elapsed' WHERE device_id=? AND state IN ('PENDING','LEASED','RETRY_WAIT') AND expires_at <= ?",
                (device_id, iso(now)),
            )
            connection.execute(
                """
                UPDATE outbox SET state='PENDING', next_attempt_at=NULL
                WHERE device_id=? AND state='RETRY_WAIT' AND next_attempt_at <= ? AND expires_at > ?
                """,
                (device_id, iso(now), iso(now)),
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
        now = iso(utc_now())
        with self._lock, self._connection() as connection:
            updated = connection.execute(
                """UPDATE outbox SET state='ACKED', acknowledged_at=?, lease_token=NULL, lease_until=NULL
                   WHERE device_id=? AND message_id=? AND state='LEASED' AND lease_token=? AND lease_until > ?""",
                (now, device_id, message_id, delivery_token, now),
            ).rowcount
        return updated == 1

    def reject(self, device_id: str, message_id: str, delivery_token: str, reason: str, retryable: bool) -> bool:
        now_value = utc_now()
        now = iso(now_value)
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT payload_sha256, retry_count FROM outbox
                WHERE device_id=? AND message_id=? AND state='LEASED' AND lease_token=? AND lease_until > ?
                """,
                (device_id, message_id, delivery_token, now),
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                return False
            retry_count = int(row["retry_count"]) + 1
            can_retry = retryable and retry_count < MAX_DELIVERY_RETRIES
            delay_seconds = min(
                INITIAL_DELIVERY_RETRY_DELAY_SECONDS * (2 ** (retry_count - 1)),
                MAX_DELIVERY_RETRY_DELAY_SECONDS,
            )
            next_attempt_at = iso(now_value + timedelta(seconds=delay_seconds)) if can_retry else None
            state = "RETRY_WAIT" if can_retry else "DEAD_LETTER"
            connection.execute(
                """
                UPDATE outbox
                SET state=?, last_error=?, retry_count=?, next_attempt_at=?, lease_token=NULL, lease_until=NULL
                WHERE device_id=? AND message_id=?
                """,
                (state, reason, retry_count, next_attempt_at, device_id, message_id),
            )
            connection.execute(
                """
                INSERT INTO outbox_delivery_rejections(
                    rejection_id, device_id, message_id, delivery_token, payload_sha256,
                    reason, retryable, retry_count, rejected_at, next_attempt_at, resulting_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex, device_id, message_id, delivery_token, str(row["payload_sha256"]),
                    reason, int(retryable), retry_count, now, next_attempt_at, state,
                ),
            )
            connection.execute("COMMIT")
        return True

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
    store = GatewayStore(settings.resolved_database_path)
    capture_supervisor = LanCaptureSupervisor(settings)
    media_security = MediaSecurityAuthority(
        device_public_key_for=store.v2_device_public_key,
        capture_route_for=capture_supervisor.media_route,
        now_ms=lambda: int(utc_now().timestamp() * 1_000),
        session_ttl_ms=V2_MEDIA_SECURITY_SESSION_TTL_MS,
    )
    media_buffer = PcMediaBuffer(settings.artifact_dir / "media-buffer")
    # The v2 decoder has no candidate-card, L1 or notification dependency.
    # It receives a frame only after the encrypted original is fsync'ed in the
    # private buffer and writes technical L0 facts/failures independently.
    v2_l0_processor = V2L0MediaProcessor(
        root=settings.artifact_dir / "v2-l0-runtime",
        semantic_ledger_path=settings.artifact_dir / "v2-l0-semantic.sqlite3",
    )
    v2_l0_dispatcher = V2L0ProcessingDispatcher(v2_l0_processor)
    app = FastAPI(title="知行智学本地网关", version="1.1")

    @app.on_event("shutdown")
    def stop_capture_workers_before_gateway_exit() -> None:
        # A shutdown must preserve the ciphertext already sealed by the
        # ingress handler.  L0 is optional downstream work, so it receives a
        # bounded best-effort join and can never hold the gateway open.
        v2_l0_dispatcher.close(timeout=0.5)
        capture_supervisor.shutdown()
    pairing_limiter = PairingRateLimiter()
    nearby_pairing = NearbyPairingWindow()
    # The launcher uses this narrowly-scoped supplier for UDP discovery.  It
    # exposes only a short-lived bootstrap token, never the static fallback
    # code or an authenticated device token.
    app.state.nearby_pairing = nearby_pairing
    app.state.gateway_settings = settings
    app.state.capture_supervisor = capture_supervisor
    app.state.media_security = media_security
    app.state.media_buffer = media_buffer
    app.state.v2_l0_processor = v2_l0_processor
    app.state.v2_l0_dispatcher = v2_l0_dispatcher
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

    def require_v2_device_credential(authorization: str | None = Header(default=None)) -> tuple[str, int]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, detail={"code": "v2_device_access_token_required"})
        authenticated = store.v2_authenticated_device(authorization.removeprefix("Bearer "))
        if authenticated is None:
            raise HTTPException(401, detail={"code": "v2_device_access_token_invalid_or_expired"})
        return authenticated

    def require_ingress_key(x_zhixing_ingress_key: str | None = Header(default=None)) -> None:
        if x_zhixing_ingress_key is None or not hmac.compare_digest(x_zhixing_ingress_key, settings.ingress_key):
            raise HTTPException(401, detail={"code": "pc_ingress_auth_invalid"})

    @app.post("/api/v2/device-credentials/enroll")
    async def enroll_v2_device_credential(
        request: V2DeviceCredentialEnrollmentRequest,
        http_request: Request,
    ) -> dict[str, object]:
        client_host = http_request.client.host if http_request.client is not None else "unknown"
        rate_key = f"{client_host}:{request.device_id}:v2"
        if not pairing_limiter.allow(rate_key):
            raise HTTPException(429, detail={"code": "pairing_rate_limited"})
        if not (
            hmac.compare_digest(request.pairing_token, settings.pairing_code)
            or nearby_pairing.accepts(request.pairing_token)
        ):
            pairing_limiter.record_failure(rate_key)
            raise HTTPException(403, detail={"code": "pairing_code_invalid"})
        try:
            token, generation = store.enroll_v2_device_credential(
                request.device_id, request.public_key_spki_b64
            )
        except ValueError as error:
            raise HTTPException(422, detail={"code": str(error)}) from error
        pairing_limiter.clear(rate_key)
        return {
            "device_id": request.device_id,
            "credential_generation": generation,
            "access_token": token,
            "expires_in_seconds": V2_ACCESS_TOKEN_TTL_SECONDS,
        }

    @app.post("/api/v2/device-credentials/refresh")
    async def refresh_v2_device_credential(
        x_zhixing_device_id: str | None = Header(default=None),
        x_zhixing_device_timestamp_ms: str | None = Header(default=None),
        x_zhixing_device_nonce: str | None = Header(default=None),
        x_zhixing_device_signature: str | None = Header(default=None),
    ) -> dict[str, object]:
        if (
            not x_zhixing_device_id
            or not x_zhixing_device_timestamp_ms
            or not x_zhixing_device_nonce
            or not x_zhixing_device_signature
        ):
            raise HTTPException(401, detail={"code": "v2_device_proof_required"})
        try:
            timestamp_ms = int(x_zhixing_device_timestamp_ms)
            token, generation = store.rotate_v2_access_token(
                device_id=x_zhixing_device_id,
                timestamp_ms=timestamp_ms,
                nonce=x_zhixing_device_nonce,
                signature_b64=x_zhixing_device_signature,
            )
        except ValueError as error:
            code = str(error)
            status = 409 if code == "v2_device_proof_replayed" else 401
            raise HTTPException(status, detail={"code": code}) from error
        return {
            "device_id": x_zhixing_device_id,
            "credential_generation": generation,
            "access_token": token,
            "expires_in_seconds": V2_ACCESS_TOKEN_TTL_SECONDS,
        }

    @app.get("/api/v2/device-credentials/me")
    async def v2_device_credential_status(
        authenticated: tuple[str, int] = Depends(require_v2_device_credential),
    ) -> dict[str, object]:
        return {"device_id": authenticated[0], "credential_generation": authenticated[1]}

    @app.post("/api/v2/media-sessions", status_code=201)
    async def open_v2_media_security_session(
        request: V2MediaSecurityOpenIngress,
        authenticated: tuple[str, int] = Depends(require_v2_device_credential),
    ) -> dict[str, object]:
        if not hmac.compare_digest(request.device_id, authenticated[0]):
            raise HTTPException(403, detail={"code": "media_device_mismatch"})
        try:
            opened = media_security.open(
                MediaSecurityOpenRequest(
                    device_id=request.device_id,
                    learner_id=request.learner_id,
                    capture_session_id=request.capture_session_id,
                    capture_consent_id=request.capture_consent_id,
                    consent_generation=request.consent_generation,
                    route_lease_id=request.route_lease_id,
                    route_epoch=request.route_epoch,
                    capture_epoch=request.capture_epoch,
                    client_ephemeral_spki_b64=request.client_ephemeral_spki_b64,
                    signature_b64=request.signature_b64,
                )
            )
        except ValueError as error:
            code = str(error)
            status = 401 if code in {
                "media_device_credential_unavailable", "media_security_open_signature_invalid"
            } else 409 if code in {"media_capture_route_not_available", "media_capture_route_mismatch"} else 422
            raise HTTPException(status, detail={"code": code}) from error
        return asdict(opened)

    @app.post("/api/v2/media-sessions/{media_security_session_id}/fragments", status_code=202)
    async def ingest_v2_media_fragment(
        media_security_session_id: str,
        request: V2MediaFragmentIngress,
        authenticated: tuple[str, int] = Depends(require_v2_device_credential),
    ) -> dict[str, object]:
        try:
            accepted = media_security.accept_fragment(
                media_security_session_id,
                MediaFragmentEnvelope(
                    header=MediaFragmentHeader(**request.header.model_dump()),
                    nonce_b64=request.nonce_b64,
                    ciphertext_b64=request.ciphertext_b64,
                ),
                authenticated_device_id=authenticated[0],
                plaintext_validator=v2_l0_processor.validate_plaintext,
            )
        except (ValueError, V2L0MediaProcessorError) as error:
            code = str(error)
            status = 404 if code == "media_security_session_not_available" else 409
            raise HTTPException(status, detail={"code": code}) from error
        if request.capture_epoch != accepted.header.capture_epoch:
            raise HTTPException(409, detail={"code": "media_fragment_capture_epoch_mismatch"})
        try:
            with capture_supervisor.v2_media_ingress_permit(
                authenticated[0], accepted.header.capture_session_id
            ):
                buffered = media_buffer.persist(
                    accepted, capture_epoch=request.capture_epoch, device_id=authenticated[0]
                )
        except ValueError as error:
            code = str(error)
            status = 409 if code in {
                "media_buffer_revoked", "media_buffer_idempotency_conflict",
                "media_capture_route_not_available", "media_capture_output_blocked",
            } else 422
            raise HTTPException(status, detail={"code": code}) from error
        # The receipt boundary is the encrypted blob plus metadata fsync.  L0
        # decode/ledger work remains ordered but runs beyond that boundary:
        # a slow decoder must not fill Android's sender queue or induce a
        # legacy fallback.  Queue pressure is itself an auditable L0 state.
        l0_receipt = v2_l0_dispatcher.submit(accepted, buffered)
        return {
            "sequence": accepted.header.sequence,
            "media_sha256": accepted.header.media_sha256,
            "buffered": True,
            "buffer_fragment_id": buffered.fragment_id,
            "buffer_local_storage_hash": buffered.local_storage_hash,
            "l0_state": l0_receipt.state,
            "l0_fact_id": None,
        }

    @app.post("/api/v2/media-sessions/{media_security_session_id}/resume")
    async def resume_v2_media_buffer(
        media_security_session_id: str,
        request: V2MediaResumeIngress,
        authenticated: tuple[str, int] = Depends(require_v2_device_credential),
    ) -> dict[str, object]:
        try:
            binding = media_security.require_session(
                media_security_session_id, authenticated_device_id=authenticated[0]
            )
            if (
                request.learner_id != binding.learner_id
                or request.capture_session_id != binding.capture_session_id
                or request.capture_consent_id != binding.capture_consent_id
                or request.consent_generation != binding.consent_generation
                or request.route_lease_id != binding.route_lease_id
                or request.route_epoch != binding.route_epoch
                or request.capture_epoch != binding.capture_epoch
            ):
                raise ValueError("media_buffer_scope_mismatch")
            receipt = media_buffer.resume(
                learner_id=request.learner_id,
                session_id=request.capture_session_id,
                capture_consent_id=request.capture_consent_id,
                consent_generation=request.consent_generation,
                route_lease_id=request.route_lease_id,
                route_epoch=request.route_epoch,
                capture_epoch=request.capture_epoch,
                owner_endpoint_id=request.owner_endpoint_id,
                resume_attempt_id=request.resume_attempt_id,
                media_security_session_id=media_security_session_id,
                cursor=None if request.cursor is None else PcBufferResumeCursor(**request.cursor.model_dump()),
            )
        except ValueError as error:
            code = str(error)
            status = 404 if code == "media_security_session_not_available" else 409
            raise HTTPException(status, detail={"code": code}) from error
        return asdict(receipt)

    @app.post("/api/v2/media-sessions/{media_security_session_id}/ack", status_code=204)
    async def ack_v2_media_buffer(
        media_security_session_id: str,
        request: V2MediaAckIngress,
        authenticated: tuple[str, int] = Depends(require_v2_device_credential),
    ) -> Response:
        try:
            binding = media_security.require_session(
                media_security_session_id, authenticated_device_id=authenticated[0]
            )
            if (
                request.learner_id != binding.learner_id
                or request.capture_session_id != binding.capture_session_id
                or request.capture_consent_id != binding.capture_consent_id
                or request.consent_generation != binding.consent_generation
                or request.route_epoch != binding.route_epoch
                or request.capture_epoch != binding.capture_epoch
            ):
                raise ValueError("media_buffer_scope_mismatch")
            media_buffer.ack(
                learner_id=request.learner_id,
                session_id=request.capture_session_id,
                capture_consent_id=request.capture_consent_id,
                consent_generation=request.consent_generation,
                route_epoch=request.route_epoch,
                capture_epoch=request.capture_epoch,
                sequence=request.sequence,
                media_security_session_id=media_security_session_id,
            )
        except (KeyError, ValueError) as error:
            code = str(error) if isinstance(error, ValueError) else "media_buffer_fragment_not_available"
            status = 404 if code == "media_security_session_not_available" else 409
            raise HTTPException(status, detail={"code": code}) from error
        return Response(status_code=204)

    @app.delete("/api/v2/device-credentials/me", status_code=204)
    async def revoke_v2_device_credential(
        authenticated: tuple[str, int] = Depends(require_v2_device_credential),
    ) -> Response:
        store.revoke_v2_device_credential(authenticated[0])
        capture_supervisor.revoke_device(authenticated[0])
        media_security.revoke_device(authenticated[0])
        media_buffer.revoke_device(authenticated[0])
        return Response(status_code=204)

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
        capture_supervisor.revoke_device(device_id)
        media_security.revoke_device(device_id)
        media_buffer.revoke_device(device_id)
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

    @app.post("/api/capture-sessions/{session_id}/foreground-app")
    async def observe_capture_foreground_app(
        session_id: str,
        request: ForegroundAppObservationRequest,
        device_id: str = Depends(require_pairing),
    ) -> dict[str, object]:
        try:
            decision = capture_supervisor.observe_foreground_app(
                device_id,
                session_id,
                request.package_name,
                request.observation_source,
            )
        except KeyError as error:
            raise HTTPException(404, detail={"code": str(error)}) from error
        except ValueError as error:
            raise HTTPException(409, detail={"code": str(error)}) from error
        session = capture_supervisor.get(device_id, session_id)
        assert session is not None
        return {**session.response(), "decision_reason": decision.reason}

    @app.post("/api/capture-sessions/{session_id}/audio-capability", status_code=202)
    async def record_capture_audio_capability(
        session_id: str,
        request: AudioCapabilitySnapshotRequest,
        device_id: str = Depends(require_pairing),
    ) -> dict[str, object]:
        session = capture_supervisor.get(device_id, session_id)
        if session is None:
            raise HTTPException(404, detail={"code": "capture_session_not_found"})
        if session.state not in {"STARTING", "RUNNING"}:
            raise HTTPException(409, detail={"code": "capture_session_not_active"})
        if request.capture_generation != session.capture_generation:
            raise HTTPException(409, detail={"code": "capture_audio_generation_stale"})
        try:
            state = store.record_capture_audio_capability(device_id, session_id, request)
        except ValueError as error:
            raise HTTPException(409, detail={"code": str(error)}) from error
        payload = request.model_dump(mode="json")
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        try:
            session.append_audio_telemetry(
                {
                    "event_type": "CaptureAudioCapabilityObservedL0",
                    "capture_session_id": session_id,
                    "device_id": device_id,
                    "payload": payload,
                    "payload_sha256": sha256(payload_json),
                    "admission": "L0_ONLY_NO_V2_CONSENT",
                    "received_at": iso(utc_now()),
                }
            )
        except OSError as error:
            # The database receipt alone is not enough for the concurrently
            # running media pipeline to bind this L0 technical fact.  Return a
            # retryable failure; a same-ID retry remains idempotent in SQLite.
            raise HTTPException(503, detail={"code": "capture_audio_journal_unavailable"}) from error
        return {
            "snapshot_id": request.snapshot_id,
            "state": state,
            # This endpoint is deliberately unable to admit L1 or v2 media.
            # The formal v2 consent/media-security ingress will replace it.
            "admission": "L0_ONLY_NO_V2_CONSENT",
        }

    @app.post("/api/capture-sessions/{session_id}/stop", status_code=202)
    async def stop_capture_session(session_id: str, device_id: str = Depends(require_pairing)) -> dict[str, object]:
        session = capture_supervisor.stop(device_id, session_id)
        if session is None:
            raise HTTPException(404, detail={"code": "capture_session_not_found"})
        # Fence the encrypted data plane at the same user-stop boundary.  The
        # private buffer is intentionally not revoked: fragments accepted
        # before this boundary remain durable evidence for interruption
        # settlement, while late queued uploads are rejected.
        media_security.close_capture_session(session_id, device_id=device_id)
        return session.response()

    @app.get("/api/mobile-outbox/messages")
    async def list_messages(device_id: str, limit: int = 20, paired_device: str = Depends(require_pairing)) -> dict[str, object]:
        if device_id != paired_device:
            raise HTTPException(403, detail={"code": "mobile_device_mismatch"})
        return {"messages": store.lease(device_id, min(max(limit, 1), 50))}

    @app.post("/api/mobile-outbox/messages", status_code=202)
    async def enqueue_message(request: OutboxIngressRequest, _: None = Depends(require_ingress_key)) -> dict[str, str]:
        payload = request.payload
        if payload.get("schema_version") == "mobile_result_message.v1":
            raise HTTPException(410, detail={"code": "legacy_v1_ingress_disabled"})
        if payload.get("schema_version") == "CONTENT_ANALYSIS_PACKAGE.v2.l1":
            # The endpoint remains reserved so Android and PC can converge on
            # one URL. It cannot enqueue until the typed v2 codec, local
            # admission resolver and receipt transaction are connected.
            raise HTTPException(503, detail={"code": "v2_delivery_ingress_unavailable"})
        if not isinstance(payload.get("schema_version"), str):
            raise HTTPException(422, detail={"code": "mobile_message_schema_unsupported"})
        raise HTTPException(422, detail={"code": "mobile_message_schema_unsupported"})

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
