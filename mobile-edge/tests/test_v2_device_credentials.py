from __future__ import annotations

import base64
from contextlib import closing
from dataclasses import asdict, replace
import hashlib
import sqlite3
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from scripts.local_agent_gateway import CaptureSession, GatewaySettings, build_app, build_v2_device_proof_payload
from scripts.capture_session_policy import CaptureMode, CaptureOutputState, CaptureSessionPolicy
from scripts.realtime_runtime.media_security import (
    MediaFragmentHeader,
    MediaSecurityOpenRequest,
    MediaSecurityOpenResponse,
    build_media_security_open_payload,
    derive_client_fragment_key,
    encrypt_media_fragment,
)
from scripts.realtime_runtime.encoded_media_frame import EncodedMediaFrame, EncodedMediaTrack, encode_encoded_media_frame


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        build_app(GatewaySettings("pair-code", None, None, tmp_path, "ingress-key", database_path=tmp_path / "gateway.sqlite3"))
    )


def _enroll(client: TestClient, private_key: ec.EllipticCurvePrivateKey) -> dict[str, object]:
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    response = client.post(
        "/api/v2/device-credentials/enroll",
        json={
            "device_id": "phone-v2",
            "pairing_token": "pair-code",
            "public_key_spki_b64": base64.b64encode(public_der).decode("ascii"),
        },
    )
    assert response.status_code == 200
    return response.json()


def _proof_headers(private_key: ec.EllipticCurvePrivateKey, *, nonce: str) -> dict[str, str]:
    timestamp_ms = int(time.time() * 1_000)
    payload = build_v2_device_proof_payload(
        method="POST",
        path="/api/v2/device-credentials/refresh",
        device_id="phone-v2",
        timestamp_ms=timestamp_ms,
        nonce=nonce,
        body_sha256=None,
    )
    signature = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
    return {
        "X-Zhixing-Device-Id": "phone-v2",
        "X-Zhixing-Device-Timestamp-Ms": str(timestamp_ms),
        "X-Zhixing-Device-Nonce": nonce,
        "X-Zhixing-Device-Signature": base64.b64encode(signature).decode("ascii"),
    }


def test_v2_credential_uses_short_access_token_and_rotation_requires_non_replayable_key_proof(tmp_path: Path) -> None:
    client = _client(tmp_path)
    private_key = ec.generate_private_key(ec.SECP256R1())

    enrolled = _enroll(client, private_key)
    first_token = str(enrolled["access_token"])
    assert 0 < int(enrolled["expires_in_seconds"]) <= 900
    assert client.get(
        "/api/v2/device-credentials/me", headers={"Authorization": f"Bearer {first_token}"}
    ).json()["device_id"] == "phone-v2"

    headers = _proof_headers(private_key, nonce="nonce-000000000001")
    refreshed = client.post("/api/v2/device-credentials/refresh", headers=headers)
    assert refreshed.status_code == 200
    second_token = refreshed.json()["access_token"]
    assert second_token != first_token
    assert client.get(
        "/api/v2/device-credentials/me", headers={"Authorization": f"Bearer {first_token}"}
    ).status_code == 401
    assert client.get(
        "/api/v2/device-credentials/me", headers={"Authorization": f"Bearer {second_token}"}
    ).status_code == 200
    assert client.post("/api/v2/device-credentials/refresh", headers=headers).status_code == 409


def test_v2_credential_revocation_invalidates_the_short_token_immediately(tmp_path: Path) -> None:
    client = _client(tmp_path)
    private_key = ec.generate_private_key(ec.SECP256R1())
    token = str(_enroll(client, private_key)["access_token"])
    headers = {"Authorization": f"Bearer {token}"}
    payload_json = '{"schema_version":"test.outbox.v2"}'
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        connection.execute(
            """INSERT INTO outbox(
                   device_id,message_id,payload_json,payload_sha256,created_at,expires_at,state,lease_token,lease_until
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                "phone-v2",
                "v2-revoked-lease",
                payload_json,
                hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                "2026-07-30T00:00:00+00:00",
                "2030-01-01T00:00:00+00:00",
                "LEASED",
                "lease-must-not-survive-revoke",
                "2030-01-01T00:00:30+00:00",
            ),
        )
        connection.commit()

    assert client.delete("/api/v2/device-credentials/me", headers=headers).status_code == 204
    assert client.get("/api/v2/device-credentials/me", headers=headers).status_code == 401
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        state, lease_token, lease_until, reason = connection.execute(
            "SELECT state, lease_token, lease_until, last_error FROM outbox WHERE device_id=? AND message_id=?",
            ("phone-v2", "v2-revoked-lease"),
        ).fetchone()
    assert (state, lease_token, lease_until, reason) == ("REVOKED", None, None, "device_revoked")


def test_v2_credential_revocation_stops_only_its_capture_workers_and_preserves_sealed_evidence(tmp_path: Path) -> None:
    app = build_app(
        GatewaySettings("pair-code", None, None, tmp_path, "ingress-key", database_path=tmp_path / "gateway.sqlite3")
    )
    client = TestClient(app)
    private_key = ec.generate_private_key(ec.SECP256R1())
    token = str(_enroll(client, private_key)["access_token"])

    supervisor = app.state.capture_supervisor
    running = CaptureSession(
        "capture-v2-running", "phone-v2", "rtsp://127.0.0.1:8554/live", tmp_path / "running", "RUNNING", "now"
    )
    recovering = CaptureSession(
        "capture-v2-recovering", "phone-v2", "rtsp://127.0.0.1:8554/live", tmp_path / "recovering", "RECOVERING", "now"
    )
    unrelated = CaptureSession(
        "capture-other", "other-phone", "rtsp://127.0.0.1:8554/live", tmp_path / "other", "RUNNING", "now"
    )
    for session in (running, recovering, unrelated):
        session.stop_signal_file = session.output_dir.parent / f".{session.session_id}.stop-requested"
        supervisor._sessions[(session.device_id, session.session_id)] = session
    sealed_evidence = running.output_dir / "sealed-fragment.json"
    sealed_evidence.parent.mkdir(parents=True)
    sealed_evidence.write_text('{"sealed":true}', encoding="utf-8")

    response = client.delete("/api/v2/device-credentials/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 204
    assert running.state == "STOPPING"
    assert recovering.state == "STOPPING"
    assert running.stop_signal_file.is_file()
    assert recovering.stop_signal_file.is_file()
    assert running.preserve_completed_evidence is True
    assert sealed_evidence.read_text(encoding="utf-8") == '{"sealed":true}'
    assert unrelated.state == "RUNNING"
    assert not unrelated.stop_signal_file.exists()


def test_v2_media_ingress_requires_an_authenticated_ephemeral_session_and_only_accepts_encrypted_fragments(
    tmp_path: Path,
) -> None:
    app = build_app(
        GatewaySettings("pair-code", None, None, tmp_path, "ingress-key", database_path=tmp_path / "gateway.sqlite3")
    )
    client = TestClient(app)
    device_key = ec.generate_private_key(ec.SECP256R1())
    token = str(_enroll(client, device_key)["access_token"])
    app.state.capture_supervisor._sessions[("phone-v2", "capture-v2-1")] = CaptureSession(
        "capture-v2-1", "phone-v2", "rtsp://127.0.0.1:8554/live", tmp_path / "capture", "RUNNING", "now",
        capture_generation=1, media_route_lease_id="route-v2-1", media_route_epoch=1,
        learner_id="learner-1", capture_consent_id="consent-v2-1", consent_generation=1,
        authorization_capture_epoch=1,
    )
    ephemeral_key = ec.generate_private_key(ec.SECP256R1())
    ephemeral_spki_b64 = base64.b64encode(
        ephemeral_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode("ascii")
    unsigned_open = MediaSecurityOpenRequest(
        device_id="phone-v2",
        learner_id="learner-1",
        capture_session_id="capture-v2-1",
        capture_consent_id="consent-v2-1",
        consent_generation=1,
        route_lease_id="route-v2-1",
        route_epoch=1,
        client_ephemeral_spki_b64=ephemeral_spki_b64,
        signature_b64="",
    )
    signature = device_key.sign(build_media_security_open_payload(unsigned_open), ec.ECDSA(hashes.SHA256()))
    open_response = client.post(
        "/api/v2/media-sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            **unsigned_open.unsigned_payload(),
            "signature_b64": base64.b64encode(signature).decode("ascii"),
        },
    )

    assert open_response.status_code == 201
    opened = open_response.json()
    key = derive_client_fragment_key(ephemeral_key, MediaSecurityOpenResponse(**opened))
    header = MediaFragmentHeader(
        media_security_session_id=opened["media_security_session_id"],
        learner_id="learner-1",
        capture_session_id="capture-v2-1",
        capture_consent_id="consent-v2-1",
        consent_generation=1,
        route_lease_id="route-v2-1",
        route_epoch=1,
        sequence=0,
        pts_start_us=10_000,
        pts_end_us=12_000,
        media_sha256="",
    )
    envelope = encrypt_media_fragment(
        key,
        header,
        encode_encoded_media_frame(EncodedMediaFrame(EncodedMediaTrack.VIDEO, 10_000, 2_000, True, b"encoded-media-fragment")),
    )
    accepted = client.post(
        f"/api/v2/media-sessions/{opened['media_security_session_id']}/fragments",
        headers={"Authorization": f"Bearer {token}"},
        json={"header": asdict(envelope.header), "nonce_b64": envelope.nonce_b64, "ciphertext_b64": envelope.ciphertext_b64},
    )
    replay = client.post(
        f"/api/v2/media-sessions/{opened['media_security_session_id']}/fragments",
        headers={"Authorization": f"Bearer {token}"},
        json={"header": asdict(envelope.header), "nonce_b64": envelope.nonce_b64, "ciphertext_b64": envelope.ciphertext_b64},
    )

    assert accepted.status_code == 202
    assert accepted.json()["sequence"] == 0
    assert accepted.json()["l0_state"] == "QUEUED_L0"
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "media_fragment_sequence_replayed_or_out_of_order"

    session = app.state.capture_supervisor._sessions[("phone-v2", "capture-v2-1")]
    session.policy = CaptureSessionPolicy.create(CaptureMode.SELECTED_APPS, ("tv.danmaku.bili",))
    session.capture_output_state = CaptureOutputState.STREAMING_BLOCKED
    blocked_header = MediaFragmentHeader(
        **{**asdict(header), "sequence": 1, "pts_start_us": 12_000, "pts_end_us": 14_000},
    )
    blocked_envelope = encrypt_media_fragment(
        key,
        blocked_header,
        encode_encoded_media_frame(
            EncodedMediaFrame(EncodedMediaTrack.VIDEO, 12_000, 2_000, False, b"late-frame-must-not-persist")
        ),
    )
    blocked = client.post(
        f"/api/v2/media-sessions/{opened['media_security_session_id']}/fragments",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "header": asdict(blocked_envelope.header),
            "nonce_b64": blocked_envelope.nonce_b64,
            "ciphertext_b64": blocked_envelope.ciphertext_b64,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "media_capture_output_blocked"


def test_v2_media_session_cannot_be_opened_without_an_active_pc_issued_capture_route(tmp_path: Path) -> None:
    client = _client(tmp_path)
    device_key = ec.generate_private_key(ec.SECP256R1())
    token = str(_enroll(client, device_key)["access_token"])
    ephemeral = ec.generate_private_key(ec.SECP256R1())
    spki = base64.b64encode(
        ephemeral.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    ).decode("ascii")
    unsigned = MediaSecurityOpenRequest(
        device_id="phone-v2", learner_id="learner-1", capture_session_id="unissued-capture",
        capture_consent_id="consent-1", consent_generation=1, route_lease_id="forged-route",
        route_epoch=1, client_ephemeral_spki_b64=spki, signature_b64="",
    )
    signature = device_key.sign(build_media_security_open_payload(unsigned), ec.ECDSA(hashes.SHA256()))

    rejected = client.post(
        "/api/v2/media-sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={**unsigned.unsigned_payload(), "signature_b64": base64.b64encode(signature).decode("ascii")},
    )

    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "media_capture_route_not_available"
