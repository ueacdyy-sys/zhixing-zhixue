"""Authenticated, encrypted v2 media-fragment protocol primitives.

This module deliberately contains no RTSP adapter.  It is the narrow protocol
core that both the PC gateway and Android transport must use before a media
fragment can enter the v2 pipeline.  RTSP alone remains a legacy transport and
must never be treated as a ``MediaSecuritySession``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import asdict, dataclass, replace
from typing import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _b64decode(value: str, *, code: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as error:
        raise ValueError(code) from error


def _load_p256_public_key(value: str, *, code: str) -> ec.EllipticCurvePublicKey:
    try:
        key = serialization.load_der_public_key(_b64decode(value, code=code))
    except (TypeError, ValueError) as error:
        raise ValueError(code) from error
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError(code)
    return key


@dataclass(frozen=True)
class MediaSecurityOpenRequest:
    device_id: str
    learner_id: str
    capture_session_id: str
    capture_consent_id: str
    consent_generation: int
    route_lease_id: str
    route_epoch: int
    client_ephemeral_spki_b64: str
    signature_b64: str
    capture_epoch: int = 1

    def unsigned_payload(self) -> dict[str, object]:
        return {
            "capture_consent_id": self.capture_consent_id,
            "capture_epoch": self.capture_epoch,
            "capture_session_id": self.capture_session_id,
            "client_ephemeral_spki_b64": self.client_ephemeral_spki_b64,
            "consent_generation": self.consent_generation,
            "device_id": self.device_id,
            "learner_id": self.learner_id,
            "route_epoch": self.route_epoch,
            "route_lease_id": self.route_lease_id,
        }


def build_media_security_open_payload(request: MediaSecurityOpenRequest) -> bytes:
    """Canonical bytes that the enrolled Android signing key must sign."""

    return b"ZHIXING_MEDIA_SECURITY_OPEN.v1\n" + _canonical_json(request.unsigned_payload()) + b"\n"


@dataclass(frozen=True)
class MediaSecurityOpenResponse:
    media_security_session_id: str
    device_id: str
    learner_id: str
    capture_session_id: str
    capture_consent_id: str
    consent_generation: int
    route_lease_id: str
    route_epoch: int
    server_ephemeral_spki_b64: str
    key_derivation_salt_b64: str
    expires_at_ms: int
    cipher_suite: str = "P-256-HKDF-SHA256-AES-256-GCM"
    capture_epoch: int = 1

    def binding_payload(self) -> dict[str, object]:
        return {
            "capture_consent_id": self.capture_consent_id,
            "capture_epoch": self.capture_epoch,
            "capture_session_id": self.capture_session_id,
            "consent_generation": self.consent_generation,
            "device_id": self.device_id,
            "learner_id": self.learner_id,
            "media_security_session_id": self.media_security_session_id,
            "route_epoch": self.route_epoch,
            "route_lease_id": self.route_lease_id,
        }


@dataclass(frozen=True)
class MediaFragmentHeader:
    media_security_session_id: str
    learner_id: str
    capture_session_id: str
    capture_consent_id: str
    consent_generation: int
    route_lease_id: str
    route_epoch: int
    sequence: int
    pts_start_us: int
    pts_end_us: int
    media_sha256: str
    capture_epoch: int = 1


@dataclass(frozen=True)
class MediaFragmentEnvelope:
    header: MediaFragmentHeader
    nonce_b64: str
    ciphertext_b64: str


@dataclass(frozen=True)
class AcceptedMediaFragment:
    header: MediaFragmentHeader
    plaintext: bytes
    # Kept only so the PC buffer can durably retain the already authenticated
    # ciphertext.  It is never serialized into a control-plane receipt.
    envelope: MediaFragmentEnvelope | None = None


@dataclass
class _ActiveMediaSecuritySession:
    response: MediaSecurityOpenResponse
    fragment_key: bytes
    next_sequence: int = 0
    revoked: bool = False


def _derive_fragment_key(
    private_key: ec.EllipticCurvePrivateKey,
    peer_public_key: ec.EllipticCurvePublicKey,
    response: MediaSecurityOpenResponse,
) -> bytes:
    salt = _b64decode(response.key_derivation_salt_b64, code="media_security_kdf_salt_invalid")
    if len(salt) != 32:
        raise ValueError("media_security_kdf_salt_invalid")
    shared_secret = private_key.exchange(ec.ECDH(), peer_public_key)
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"ZHIXING_MEDIA_FRAGMENT_KEY.v1\n" + _canonical_json(response.binding_payload()) + b"\n",
    ).derive(shared_secret)


def derive_client_fragment_key(
    client_ephemeral_private_key: ec.EllipticCurvePrivateKey,
    response: MediaSecurityOpenResponse,
) -> bytes:
    """Reference client derivation; Android implements the same byte contract."""

    return _derive_fragment_key(
        client_ephemeral_private_key,
        _load_p256_public_key(response.server_ephemeral_spki_b64, code="media_security_server_key_invalid"),
        response,
    )


def _header_aad(header: MediaFragmentHeader) -> bytes:
    return b"ZHIXING_MEDIA_FRAGMENT_AAD.v1\n" + _canonical_json(asdict(header)) + b"\n"


def encrypt_media_fragment(
    fragment_key: bytes,
    header: MediaFragmentHeader,
    plaintext: bytes,
) -> MediaFragmentEnvelope:
    """Encrypt one encoded fragment and bind all routing identity as AEAD AAD."""

    if len(fragment_key) != 32:
        raise ValueError("media_security_fragment_key_invalid")
    if not plaintext:
        raise ValueError("media_fragment_empty")
    completed_header = replace(header, media_sha256=_sha256(plaintext))
    nonce = os.urandom(12)
    ciphertext = AESGCM(fragment_key).encrypt(nonce, plaintext, _header_aad(completed_header))
    return MediaFragmentEnvelope(
        header=completed_header,
        nonce_b64=base64.b64encode(nonce).decode("ascii"),
        ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
    )


class MediaSecurityAuthority:
    """PC-side active-session authority; fragment keys never leave memory."""

    def __init__(
        self,
        *,
        device_public_key_for: Callable[[str], ec.EllipticCurvePublicKey | None],
        capture_route_for: Callable[[str, str], tuple[str, int, int, str, str, int] | None] | None = None,
        now_ms: Callable[[], int],
        session_ttl_ms: int,
    ) -> None:
        if session_ttl_ms <= 0:
            raise ValueError("media_security_session_ttl_invalid")
        self._device_public_key_for = device_public_key_for
        self._capture_route_for = capture_route_for
        self._now_ms = now_ms
        self._session_ttl_ms = session_ttl_ms
        self._sessions: dict[str, _ActiveMediaSecuritySession] = {}

    def open(self, request: MediaSecurityOpenRequest) -> MediaSecurityOpenResponse:
        self._validate_open_request(request)
        if self._capture_route_for is not None:
            issued_route = self._capture_route_for(request.device_id, request.capture_session_id)
            if issued_route is None:
                raise ValueError("media_capture_route_not_available")
            lease_id, route_epoch, capture_epoch, learner_id, consent_id, consent_generation = issued_route
            if (
                not hmac.compare_digest(request.route_lease_id, lease_id)
                or request.route_epoch != route_epoch
                or request.capture_epoch != capture_epoch
                or not hmac.compare_digest(request.learner_id, learner_id)
                or not hmac.compare_digest(request.capture_consent_id, consent_id)
                or request.consent_generation != consent_generation
            ):
                raise ValueError("media_capture_route_mismatch")
        device_key = self._device_public_key_for(request.device_id)
        if device_key is None:
            raise ValueError("media_device_credential_unavailable")
        try:
            device_key.verify(
                _b64decode(request.signature_b64, code="media_security_open_signature_invalid"),
                build_media_security_open_payload(request),
                ec.ECDSA(hashes.SHA256()),
            )
        except InvalidSignature as error:
            raise ValueError("media_security_open_signature_invalid") from error
        client_key = _load_p256_public_key(
            request.client_ephemeral_spki_b64, code="media_security_client_key_invalid"
        )
        server_key = ec.generate_private_key(ec.SECP256R1())
        session_id = secrets.token_urlsafe(32)
        now = self._now_ms()
        response = MediaSecurityOpenResponse(
            media_security_session_id=session_id,
            device_id=request.device_id,
            learner_id=request.learner_id,
            capture_session_id=request.capture_session_id,
            capture_consent_id=request.capture_consent_id,
            consent_generation=request.consent_generation,
            route_lease_id=request.route_lease_id,
            route_epoch=request.route_epoch,
            server_ephemeral_spki_b64=base64.b64encode(
                server_key.public_key().public_bytes(
                    serialization.Encoding.DER,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            ).decode("ascii"),
            key_derivation_salt_b64=base64.b64encode(os.urandom(32)).decode("ascii"),
            expires_at_ms=now + self._session_ttl_ms,
            capture_epoch=request.capture_epoch,
        )
        self._sessions[session_id] = _ActiveMediaSecuritySession(
            response=response,
            fragment_key=_derive_fragment_key(server_key, client_key, response),
        )
        return response

    def accept_fragment(
        self,
        session_id: str,
        envelope: MediaFragmentEnvelope,
        *,
        authenticated_device_id: str | None = None,
        plaintext_validator: Callable[[MediaFragmentHeader, bytes], None] | None = None,
    ) -> AcceptedMediaFragment:
        active = self._available_session(session_id)
        header = envelope.header
        response = active.response
        if authenticated_device_id is not None and not hmac.compare_digest(
            authenticated_device_id, response.device_id
        ):
            raise ValueError("media_security_session_not_available")
        if header.media_security_session_id != response.media_security_session_id:
            raise ValueError("media_fragment_scope_mismatch")
        if not self._is_bound_header(response, header):
            raise ValueError("media_fragment_scope_mismatch")
        if header.sequence < active.next_sequence:
            raise ValueError("media_fragment_sequence_replayed_or_out_of_order")
        if header.sequence > active.next_sequence:
            raise ValueError("media_fragment_sequence_gap")
        if header.pts_start_us < 0 or header.pts_end_us < header.pts_start_us:
            raise ValueError("media_fragment_pts_invalid")
        if len(header.media_sha256) != 64:
            raise ValueError("media_fragment_hash_invalid")
        nonce = _b64decode(envelope.nonce_b64, code="media_fragment_authentication_failed")
        ciphertext = _b64decode(envelope.ciphertext_b64, code="media_fragment_authentication_failed")
        if len(nonce) != 12 or len(ciphertext) < 16:
            raise ValueError("media_fragment_authentication_failed")
        try:
            plaintext = AESGCM(active.fragment_key).decrypt(nonce, ciphertext, _header_aad(header))
        except Exception as error:
            raise ValueError("media_fragment_authentication_failed") from error
        if not hmac.compare_digest(_sha256(plaintext), header.media_sha256):
            raise ValueError("media_fragment_payload_hash_mismatch")
        # The inner frame contract is part of authenticated admission, not a
        # best-effort post-ACK check.  A rejected plaintext must not advance
        # the anti-replay sequence, otherwise the Android sender cannot repair
        # one malformed encoded frame without creating an artificial gap.
        if plaintext_validator is not None:
            plaintext_validator(header, plaintext)
        active.next_sequence += 1
        return AcceptedMediaFragment(header=header, plaintext=plaintext, envelope=envelope)

    def revoke_device(self, device_id: str) -> None:
        for active in self._sessions.values():
            if active.response.device_id == device_id:
                active.revoked = True

    def close_capture_session(self, capture_session_id: str, *, device_id: str | None = None) -> None:
        """Close live media-security ingress for one capture interruption.

        This is deliberately narrower than device/consent revocation: the
        already durable encrypted buffer remains retained and auditable, while
        queued handset uploads cannot arrive after the user stopped the
        capture.  A later explicit capture gets a new route/security session.
        """
        for active in self._sessions.values():
            if active.response.capture_session_id != capture_session_id:
                continue
            if device_id is not None and active.response.device_id != device_id:
                continue
            active.revoked = True

    def require_session(self, session_id: str, *, authenticated_device_id: str | None = None) -> MediaSecurityOpenResponse:
        """Return the live binding for receipt/ACK endpoints without exposing keys."""
        active = self._available_session(session_id)
        if authenticated_device_id is not None and not hmac.compare_digest(
            authenticated_device_id, active.response.device_id
        ):
            raise ValueError("media_security_session_not_available")
        return active.response

    def _available_session(self, session_id: str) -> _ActiveMediaSecuritySession:
        active = self._sessions.get(session_id)
        if active is None or active.revoked or self._now_ms() >= active.response.expires_at_ms:
            # Do not tell an unauthenticated caller whether an opaque endpoint
            # existed, expired, or was revoked.
            raise ValueError("media_security_session_not_available")
        return active

    @staticmethod
    def _is_bound_header(response: MediaSecurityOpenResponse, header: MediaFragmentHeader) -> bool:
        return (
            header.learner_id == response.learner_id
            and header.capture_session_id == response.capture_session_id
            and header.capture_consent_id == response.capture_consent_id
            and header.consent_generation == response.consent_generation
            and header.route_lease_id == response.route_lease_id
            and header.route_epoch == response.route_epoch
            and header.capture_epoch == response.capture_epoch
        )

    @staticmethod
    def _validate_open_request(request: MediaSecurityOpenRequest) -> None:
        required = (
            request.device_id,
            request.learner_id,
            request.capture_session_id,
            request.capture_consent_id,
            request.route_lease_id,
            request.client_ephemeral_spki_b64,
            request.signature_b64,
        )
        if any(not value or "\n" in value or "\r" in value for value in required):
            raise ValueError("media_security_open_request_invalid")
        if request.consent_generation < 1 or request.route_epoch < 1 or request.capture_epoch < 1:
            raise ValueError("media_security_open_request_invalid")
