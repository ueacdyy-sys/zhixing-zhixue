from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from scripts.realtime_runtime.media_buffer import (
    PcBufferResumeCursor,
    PcMediaBuffer,
    PcMediaBufferCapacity,
)
from scripts.realtime_runtime.media_security import (
    AcceptedMediaFragment,
    MediaFragmentEnvelope,
    MediaFragmentHeader,
    MediaSecurityAuthority,
    MediaSecurityOpenRequest,
    build_media_security_open_payload,
    derive_client_fragment_key,
    encrypt_media_fragment,
)


def _opened() -> tuple[MediaSecurityAuthority, object, object]:
    device = ec.generate_private_key(ec.SECP256R1())
    client = ec.generate_private_key(ec.SECP256R1())
    authority = MediaSecurityAuthority(
        device_public_key_for=lambda _: device.public_key(),
        now_ms=lambda: 1_000_000,
        session_ttl_ms=60_000,
    )
    client_spki = base64.b64encode(
        client.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    ).decode("ascii")
    unsigned = MediaSecurityOpenRequest(
        device_id="device-1", learner_id="learner-1", capture_session_id="session-1",
        capture_consent_id="consent-1", consent_generation=2, route_lease_id="route-1",
        route_epoch=7, client_ephemeral_spki_b64=client_spki, signature_b64="",
    )
    signed = replace(unsigned, signature_b64=base64.b64encode(
        device.sign(build_media_security_open_payload(unsigned), ec.ECDSA(hashes.SHA256()))
    ).decode("ascii"))
    return authority, authority.open(signed), client


def _fragment(authority: MediaSecurityAuthority, opened: object, client: object, sequence: int, payload: bytes):
    key = derive_client_fragment_key(client, opened)
    header = MediaFragmentHeader(
        media_security_session_id=opened.media_security_session_id,
        learner_id="learner-1", capture_session_id="session-1", capture_consent_id="consent-1",
        consent_generation=2, route_lease_id="route-1", route_epoch=7, sequence=sequence,
        pts_start_us=sequence * 1000, pts_end_us=(sequence + 1) * 1000, media_sha256="",
    )
    return authority.accept_fragment(
        opened.media_security_session_id,
        encrypt_media_fragment(key, header, payload),
    )


def test_persisted_fragment_is_durable_before_resume_receipt(tmp_path: Path) -> None:
    authority, opened, client = _opened()
    accepted = _fragment(authority, opened, client, 0, b"secret-frame")
    buffer = PcMediaBuffer(tmp_path / "private-buffer")

    stored = buffer.persist(accepted, capture_epoch=3)
    assert stored.sequence == 0
    assert buffer.read_encrypted(stored.fragment_id)
    assert b"secret-frame" not in (tmp_path / "private-buffer" / "buffer.sqlite3").read_bytes()

    receipt = buffer.resume(
        learner_id="learner-1", session_id="session-1", capture_consent_id="consent-1",
        consent_generation=2, route_lease_id="route-1", route_epoch=7, capture_epoch=3,
        owner_endpoint_id="pc-1", resume_attempt_id="attempt-1",
    )
    assert receipt.fragments[0].sequence == 0
    assert receipt.last_acked_sequence == -1


def test_resume_cursor_mismatch_quarantines_gap(tmp_path: Path) -> None:
    authority, opened, client = _opened()
    buffer = PcMediaBuffer(tmp_path / "private-buffer")
    buffer.persist(_fragment(authority, opened, client, 0, b"a"), capture_epoch=3)
    cursor = PcBufferResumeCursor(epoch=2, sequence=-1, range_hash="0" * 64)

    receipt = buffer.resume(
        learner_id="learner-1", session_id="session-1", capture_consent_id="consent-1",
        consent_generation=2, route_lease_id="route-1", route_epoch=7, capture_epoch=3,
        owner_endpoint_id="pc-1", resume_attempt_id="attempt-2", cursor=cursor,
    )
    assert receipt.gap_disposition.value == "QUARANTINED"


def test_ack_only_removes_persisted_unrevoked_fragments(tmp_path: Path) -> None:
    authority, opened, client = _opened()
    buffer = PcMediaBuffer(tmp_path / "private-buffer")
    stored = buffer.persist(_fragment(authority, opened, client, 0, b"a"), capture_epoch=3)
    buffer.ack(
        learner_id="learner-1", session_id="session-1", capture_consent_id="consent-1",
        consent_generation=2, route_epoch=7, capture_epoch=3, sequence=0,
    )
    with pytest.raises(KeyError):
        buffer.read_encrypted(stored.fragment_id)

    stored = buffer.persist(_fragment(authority, opened, client, 1, b"b"), capture_epoch=3)
    buffer.revoke(learner_id="learner-1", session_id="session-1", consent_generation=2)
    with pytest.raises(ValueError, match="media_buffer_revoked"):
        buffer.ack(
            learner_id="learner-1", session_id="session-1", capture_consent_id="consent-1",
            consent_generation=2, route_epoch=7, capture_epoch=3, sequence=1,
        )
    assert buffer.read_encrypted(stored.fragment_id)


def test_capacity_exposes_soft_and_hard_watermarks_without_deleting_fragments(tmp_path: Path) -> None:
    authority, opened, client = _opened()
    buffer = PcMediaBuffer(tmp_path / "private-buffer", soft_limit_bytes=1, hard_limit_bytes=2)
    buffer.persist(_fragment(authority, opened, client, 0, b"larger-than-two"), capture_epoch=3)
    assert buffer.capacity().state is PcMediaBufferCapacity.HARD
    assert buffer.pending_count() == 1


def test_security_rekey_can_restart_fragment_sequence_without_colliding_in_the_pc_buffer(tmp_path: Path) -> None:
    buffer = PcMediaBuffer(tmp_path / "private-buffer")

    def accepted(media_security_session_id: str, payload: bytes) -> AcceptedMediaFragment:
        header = MediaFragmentHeader(
            media_security_session_id=media_security_session_id,
            learner_id="learner-1", capture_session_id="session-1", capture_consent_id="consent-1",
            consent_generation=2, route_lease_id="route-1", route_epoch=7, capture_epoch=3,
            sequence=0, pts_start_us=10_000, pts_end_us=11_000, media_sha256="b" * 64,
        )
        return AcceptedMediaFragment(
            header=header,
            plaintext=payload,
            envelope=MediaFragmentEnvelope(header=header, nonce_b64="AAAAAAAAAAAAAAAA", ciphertext_b64="BBBBBBBBBBBBBBBBBBBBBBBB"),
        )

    first = buffer.persist(accepted("security-session-1", b"first"), capture_epoch=3)
    second = buffer.persist(accepted("security-session-2", b"second"), capture_epoch=3)

    assert first.fragment_id != second.fragment_id
    assert buffer.pending_count() == 2
    for security_session in ("security-session-1", "security-session-2"):
        receipt = buffer.resume(
            learner_id="learner-1", session_id="session-1", capture_consent_id="consent-1",
            consent_generation=2, route_lease_id="route-1", route_epoch=7, capture_epoch=3,
            owner_endpoint_id="pc-1", resume_attempt_id=f"resume-{security_session}",
            media_security_session_id=security_session,
        )
        assert receipt.fragments[0].sequence == 0

    buffer.ack(
        learner_id="learner-1", session_id="session-1", capture_consent_id="consent-1",
        consent_generation=2, route_epoch=7, capture_epoch=3, sequence=0,
        media_security_session_id="security-session-1",
    )
    rekey_receipt = buffer.resume(
        learner_id="learner-1", session_id="session-1", capture_consent_id="consent-1",
        consent_generation=2, route_lease_id="route-1", route_epoch=7, capture_epoch=3,
        owner_endpoint_id="pc-1", resume_attempt_id="resume-security-session-2",
        media_security_session_id="security-session-2",
    )
    assert rekey_receipt.last_acked_sequence == -1
