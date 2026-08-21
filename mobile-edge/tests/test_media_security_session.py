from __future__ import annotations

import base64
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from scripts.realtime_runtime.media_security import (
    MediaFragmentHeader,
    MediaSecurityAuthority,
    MediaSecurityOpenRequest,
    build_media_security_open_payload,
    derive_client_fragment_key,
    encrypt_media_fragment,
)


def _authority(device_public_key: ec.EllipticCurvePublicKey, *, now_ms: int = 1_000_000) -> MediaSecurityAuthority:
    return MediaSecurityAuthority(
        device_public_key_for=lambda device_id: device_public_key if device_id == "device-1" else None,
        now_ms=lambda: now_ms,
        session_ttl_ms=60_000,
    )


def _open(
    authority: MediaSecurityAuthority,
    device_private_key: ec.EllipticCurvePrivateKey,
    client_ephemeral_key: ec.EllipticCurvePrivateKey,
) -> tuple[MediaSecurityOpenRequest, object]:
    client_public_key_b64 = base64.b64encode(
        client_ephemeral_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode("ascii")
    unsigned = MediaSecurityOpenRequest(
        device_id="device-1",
        learner_id="learner-1",
        capture_session_id="capture-1",
        capture_consent_id="consent-1",
        consent_generation=3,
        route_lease_id="route-1",
        route_epoch=5,
        client_ephemeral_spki_b64=client_public_key_b64,
        signature_b64="",
    )
    signature = device_private_key.sign(
        build_media_security_open_payload(unsigned), ec.ECDSA(hashes.SHA256())
    )
    request = replace(unsigned, signature_b64=base64.b64encode(signature).decode("ascii"))
    return request, authority.open(request)


def _header(session_id: str, *, sequence: int = 0, learner_id: str = "learner-1") -> MediaFragmentHeader:
    return MediaFragmentHeader(
        media_security_session_id=session_id,
        learner_id=learner_id,
        capture_session_id="capture-1",
        capture_consent_id="consent-1",
        consent_generation=3,
        route_lease_id="route-1",
        route_epoch=5,
        sequence=sequence,
        pts_start_us=10_000,
        pts_end_us=12_000,
        media_sha256="",
    )


def test_media_security_session_accepts_only_a_bound_encrypted_fragment() -> None:
    device_key = ec.generate_private_key(ec.SECP256R1())
    ephemeral_key = ec.generate_private_key(ec.SECP256R1())
    authority = _authority(device_key.public_key())
    _, opened = _open(authority, device_key, ephemeral_key)
    key = derive_client_fragment_key(ephemeral_key, opened)
    body = b"encoded-h264-and-aac-bytes"
    envelope = encrypt_media_fragment(key, _header(opened.media_security_session_id), body)

    accepted = authority.accept_fragment(opened.media_security_session_id, envelope)

    assert accepted.plaintext == body
    assert accepted.header.sequence == 0
    assert accepted.header.learner_id == "learner-1"
    assert accepted.header.media_sha256


def test_media_security_session_rejects_replay_and_requires_the_next_sequence() -> None:
    device_key = ec.generate_private_key(ec.SECP256R1())
    ephemeral_key = ec.generate_private_key(ec.SECP256R1())
    authority = _authority(device_key.public_key())
    _, opened = _open(authority, device_key, ephemeral_key)
    key = derive_client_fragment_key(ephemeral_key, opened)
    first = encrypt_media_fragment(key, _header(opened.media_security_session_id, sequence=0), b"fragment-0")
    authority.accept_fragment(opened.media_security_session_id, first)

    with pytest.raises(ValueError, match="media_fragment_sequence_replayed_or_out_of_order"):
        authority.accept_fragment(opened.media_security_session_id, first)

    skipped = encrypt_media_fragment(key, _header(opened.media_security_session_id, sequence=2), b"fragment-2")
    with pytest.raises(ValueError, match="media_fragment_sequence_gap"):
        authority.accept_fragment(opened.media_security_session_id, skipped)


def test_media_security_session_rejects_tampered_ciphertext_without_advancing_cursor() -> None:
    device_key = ec.generate_private_key(ec.SECP256R1())
    ephemeral_key = ec.generate_private_key(ec.SECP256R1())
    authority = _authority(device_key.public_key())
    _, opened = _open(authority, device_key, ephemeral_key)
    key = derive_client_fragment_key(ephemeral_key, opened)
    envelope = encrypt_media_fragment(key, _header(opened.media_security_session_id), b"fragment-0")
    tampered_ciphertext = bytearray(base64.b64decode(envelope.ciphertext_b64))
    tampered_ciphertext[-1] ^= 0x01
    tampered = replace(envelope, ciphertext_b64=base64.b64encode(tampered_ciphertext).decode("ascii"))

    with pytest.raises(ValueError, match="media_fragment_authentication_failed"):
        authority.accept_fragment(opened.media_security_session_id, tampered)

    assert authority.accept_fragment(opened.media_security_session_id, envelope).header.sequence == 0


def test_media_security_plaintext_validator_rejects_without_spending_the_sequence() -> None:
    device_key = ec.generate_private_key(ec.SECP256R1())
    ephemeral_key = ec.generate_private_key(ec.SECP256R1())
    authority = _authority(device_key.public_key())
    _, opened = _open(authority, device_key, ephemeral_key)
    key = derive_client_fragment_key(ephemeral_key, opened)
    envelope = encrypt_media_fragment(key, _header(opened.media_security_session_id), b"structurally-valid-aead")

    with pytest.raises(ValueError, match="inner_frame_invalid"):
        authority.accept_fragment(
            opened.media_security_session_id,
            envelope,
            plaintext_validator=lambda _header, _plaintext: (_ for _ in ()).throw(ValueError("inner_frame_invalid")),
        )

    assert authority.accept_fragment(opened.media_security_session_id, envelope).header.sequence == 0


def test_media_security_session_rejects_cross_scope_header_before_decrypting() -> None:
    device_key = ec.generate_private_key(ec.SECP256R1())
    ephemeral_key = ec.generate_private_key(ec.SECP256R1())
    authority = _authority(device_key.public_key())
    _, opened = _open(authority, device_key, ephemeral_key)
    key = derive_client_fragment_key(ephemeral_key, opened)
    cross_scope = encrypt_media_fragment(
        key,
        _header(opened.media_security_session_id, learner_id="learner-other"),
        b"must-not-enter-other-scope",
    )

    with pytest.raises(ValueError, match="media_fragment_scope_mismatch"):
        authority.accept_fragment(opened.media_security_session_id, cross_scope)


def test_media_security_session_hides_missing_and_expired_endpoints_behind_one_rejection() -> None:
    device_key = ec.generate_private_key(ec.SECP256R1())
    ephemeral_key = ec.generate_private_key(ec.SECP256R1())
    authority = _authority(device_key.public_key(), now_ms=1_000_000)
    _, opened = _open(authority, device_key, ephemeral_key)
    key = derive_client_fragment_key(ephemeral_key, opened)
    envelope = encrypt_media_fragment(key, _header(opened.media_security_session_id), b"fragment")

    with pytest.raises(ValueError, match="media_security_session_not_available"):
        authority.accept_fragment("not-a-real-session", envelope)

    clock = {"now_ms": 2_000_000}
    expired = MediaSecurityAuthority(
        device_public_key_for=lambda device_id: device_key.public_key() if device_id == "device-1" else None,
        now_ms=lambda: clock["now_ms"],
        session_ttl_ms=1,
    )
    expired_client_key = ec.generate_private_key(ec.SECP256R1())
    _, expired_opened = _open(expired, device_key, expired_client_key)
    expired_envelope = encrypt_media_fragment(
        derive_client_fragment_key(expired_client_key, expired_opened),
        _header(expired_opened.media_security_session_id),
        b"fragment",
    )
    clock["now_ms"] = int(expired_opened.expires_at_ms)
    with pytest.raises(ValueError, match="media_security_session_not_available"):
        expired.accept_fragment(expired_opened.media_security_session_id, expired_envelope)


def test_capture_stop_closes_only_that_capture_data_plane() -> None:
    device_key = ec.generate_private_key(ec.SECP256R1())
    ephemeral_key = ec.generate_private_key(ec.SECP256R1())
    authority = _authority(device_key.public_key())
    _, opened = _open(authority, device_key, ephemeral_key)
    key = derive_client_fragment_key(ephemeral_key, opened)
    envelope = encrypt_media_fragment(key, _header(opened.media_security_session_id), b"late-queued-frame")

    authority.close_capture_session("capture-1", device_id="device-1")

    with pytest.raises(ValueError, match="media_security_session_not_available"):
        authority.accept_fragment(opened.media_security_session_id, envelope)
