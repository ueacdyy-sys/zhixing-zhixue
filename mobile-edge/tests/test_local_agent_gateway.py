from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import sqlite3
from contextlib import closing
import hashlib
import asyncio
import json
import subprocess
import sys
import time
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from scripts.local_agent_gateway import AgentProviderError, AgentRunRequest, CaptureSession, GatewaySettings, LanCaptureSupervisor, ask_openai_compatible, build_app, probe_selected_provider
from scripts.run_realtime_e2e import _process_is_alive


def make_client(tmp_path: Path) -> TestClient:
    return TestClient(build_app(GatewaySettings("pair-code", None, None, tmp_path, "ingress-key", database_path=tmp_path / "gateway.sqlite3")))


def pair(client: TestClient) -> str:
    response = client.post(
        "/api/mobile-outbox/devices/pair",
        json={"device_id": "phone-1", "pairing_token": "pair-code"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _CaptureProcess:
    def __init__(self, exit_code: int | None, final_code: int = 0) -> None:
        self.exit_code = exit_code
        self.final_code = final_code
        self.terminated = False

    def poll(self) -> int | None:
        return self.exit_code

    def wait(self, timeout: float | None = None) -> int:
        return self.final_code

    def terminate(self) -> None:
        self.terminated = True
        self.exit_code = self.final_code


def test_capture_supervisor_requires_all_worker_ready_receipts(tmp_path: Path) -> None:
    settings = GatewaySettings("pair-code", None, None, tmp_path, "ingress-key")
    supervisor = LanCaptureSupervisor(settings)
    session = CaptureSession("capture-1", "phone-1", "rtsp://127.0.0.1:8554/live", tmp_path / "session", "STARTING", "now")
    session.process = _CaptureProcess(exit_code=3, final_code=3)  # type: ignore[assignment]
    supervisor._sessions[("phone-1", "capture-1")] = session

    supervisor._watch(("phone-1", "capture-1"))

    assert session.state == "FAILED_RUNTIME_NOT_READY"
    assert session.error == "worker_exited_before_ready"


def test_capture_supervisor_marks_unexpected_clean_exit_as_interrupted_after_all_ready_receipts(tmp_path: Path) -> None:
    settings = GatewaySettings("pair-code", None, None, tmp_path, "ingress-key")
    supervisor = LanCaptureSupervisor(settings)
    output = tmp_path / "session"
    artifacts = output / "artifacts"
    artifacts.mkdir(parents=True)
    for lane in ("ocr", "asr", "vlm"):
        (artifacts / f"{lane}-e2e.ready.json").write_text("{}", encoding="utf-8")
    session = CaptureSession("capture-2", "phone-1", "rtsp://127.0.0.1:8554/live", output, "STARTING", "now")
    session.process = _CaptureProcess(exit_code=None, final_code=0)  # type: ignore[assignment]
    supervisor._sessions[("phone-1", "capture-2")] = session

    supervisor._watch(("phone-1", "capture-2"))

    assert session.state == "INTERRUPTED"
    assert session.interruption_reason == "PC_OBSERVED_SOURCE_DISCONNECT"
    assert session.error is None


def test_audio_capability_snapshot_is_bound_to_capture_generation_idempotent_and_auditable(tmp_path: Path) -> None:
    app = build_app(GatewaySettings("pair-code", None, None, tmp_path, "ingress-key", database_path=tmp_path / "gateway.sqlite3"))
    client = TestClient(app)
    token = pair(client)
    session = CaptureSession(
        "capture-audio-1", "phone-1", "rtsp://127.0.0.1:8554/live", tmp_path / "session", "RUNNING", "now",
    )
    # This is a capture-control generation, not a v2 consent generation.  The
    # current capture route has not yet become a v2 media-security handshake.
    session.capture_generation = 7
    app.state.capture_supervisor._sessions[("phone-1", session.session_id)] = session
    body = {
        "snapshot_id": "audio-snapshot-1",
        "capture_generation": 7,
        "capture_path": "PLAYBACK",
        "status": "CAPTURE_ACTIVE_UNVERIFIED",
        "application_package_id": "tv.danmaku.bili",
        "restriction": "NONE",
        "failure_code": None,
        "video_pts_start_us": 1_000,
        "video_pts_end_us": 2_000,
        "audio_pts_start_us": 1_010,
        "audio_pts_end_us": 2_010,
        "session_epoch_id": "rtsp-epoch-1",
        "clock_domain": "ANDROID_ELAPSED_REALTIME_MONOTONIC",
        "anchor_elapsed_realtime_ns": 100_000,
        "sync_error_us": 10,
        "recovery_attempt": 0,
    }

    accepted = client.post(f"/api/capture-sessions/{session.session_id}/audio-capability", json=body, headers=headers(token))
    duplicate = client.post(f"/api/capture-sessions/{session.session_id}/audio-capability", json=body, headers=headers(token))
    conflicting = client.post(
        f"/api/capture-sessions/{session.session_id}/audio-capability",
        json={
            **body,
            "status": "UNRESOLVED",
            "restriction": "DRM_PROTECTED",
            "failure_code": "drm-protected",
        },
        headers=headers(token),
    )

    assert accepted.status_code == 202
    assert accepted.json()["state"] == "CAPTURE_AUDIO_TELEMETRY_ACCEPTED"
    assert accepted.json()["admission"] == "L0_ONLY_NO_V2_CONSENT"
    assert duplicate.status_code == 202
    assert duplicate.json()["state"] == "DUPLICATE"
    assert conflicting.status_code == 409
    assert conflicting.json()["detail"]["code"] == "capture_audio_snapshot_id_conflict"
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        stored = connection.execute(
            "SELECT capture_generation, failure_code, payload_sha256, admission FROM capture_audio_capability_snapshots "
            "WHERE device_id=? AND capture_session_id=? AND snapshot_id=?",
            ("phone-1", "capture-audio-1", "audio-snapshot-1"),
        ).fetchone()
    assert stored is not None
    assert stored[0] == 7
    assert stored[1] is None
    assert stored[2] == hashlib.sha256(json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
    assert stored[3] == "L0_ONLY_NO_V2_CONSENT"
    journal_records = [json.loads(line) for line in session.audio_telemetry_journal_path.read_text(encoding="utf-8").splitlines()]
    assert journal_records[0]["event_type"] == "CaptureAudioCapabilityObservedL0"
    assert journal_records[0]["capture_session_id"] == session.session_id
    assert journal_records[0]["payload"] == body
    assert journal_records[0]["payload_sha256"] == stored[2]


def test_audio_capability_snapshot_rejects_a_stale_capture_generation(tmp_path: Path) -> None:
    app = build_app(GatewaySettings("pair-code", None, None, tmp_path, "ingress-key", database_path=tmp_path / "gateway.sqlite3"))
    client = TestClient(app)
    token = pair(client)
    session = CaptureSession(
        "capture-audio-stale", "phone-1", "rtsp://127.0.0.1:8554/live", tmp_path / "session", "RUNNING", "now",
    )
    session.capture_generation = 8
    app.state.capture_supervisor._sessions[("phone-1", session.session_id)] = session

    response = client.post(
        f"/api/capture-sessions/{session.session_id}/audio-capability",
        json={
            "snapshot_id": "audio-snapshot-stale",
            "capture_generation": 7,
            "capture_path": "NONE",
            "status": "NOT_REQUESTED",
            "restriction": "NONE",
            "video_pts_start_us": 1_000,
            "video_pts_end_us": 2_000,
            "session_epoch_id": "rtsp-epoch-1",
            "clock_domain": "ANDROID_ELAPSED_REALTIME_MONOTONIC",
            "anchor_elapsed_realtime_ns": 100_000,
            "recovery_attempt": 0,
        },
        headers=headers(token),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "capture_audio_generation_stale"


def test_audio_capability_snapshot_rejects_unresolved_audio_without_a_real_restriction(tmp_path: Path) -> None:
    app = build_app(GatewaySettings("pair-code", None, None, tmp_path, "ingress-key", database_path=tmp_path / "gateway.sqlite3"))
    client = TestClient(app)
    token = pair(client)
    session = CaptureSession(
        "capture-audio-unresolved", "phone-1", "rtsp://127.0.0.1:8554/live", tmp_path / "session", "RUNNING", "now",
    )
    session.capture_generation = 9
    app.state.capture_supervisor._sessions[("phone-1", session.session_id)] = session

    response = client.post(
        f"/api/capture-sessions/{session.session_id}/audio-capability",
        json={
            "snapshot_id": "audio-snapshot-unresolved",
            "capture_generation": 9,
            "capture_path": "PLAYBACK",
            "status": "UNRESOLVED",
            "restriction": "NONE",
            "failure_code": None,
            "video_pts_start_us": 1_000,
            "video_pts_end_us": 2_000,
            "session_epoch_id": "rtsp-epoch-1",
            "clock_domain": "ANDROID_ELAPSED_REALTIME_MONOTONIC",
            "anchor_elapsed_realtime_ns": 100_000,
            "recovery_attempt": 0,
        },
        headers=headers(token),
    )

    assert response.status_code == 422
    assert "capture_audio_unresolved_requires_restriction" in response.text
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        stored = connection.execute("SELECT COUNT(*) FROM capture_audio_capability_snapshots").fetchone()[0]
    assert stored == 0


def test_capture_supervisor_stop_writes_explicit_runner_stop_signal(tmp_path: Path) -> None:
    settings = GatewaySettings("pair-code", None, None, tmp_path, "ingress-key")
    supervisor = LanCaptureSupervisor(settings)
    signal = tmp_path / "session" / ".stop-requested"
    session = CaptureSession("capture-stop", "phone-1", "rtsp://127.0.0.1:8554/live", tmp_path / "session", "RUNNING", "now")
    session.stop_signal_file = signal
    session.process = _CaptureProcess(exit_code=None, final_code=0)  # type: ignore[assignment]
    supervisor._sessions[("phone-1", "capture-stop")] = session

    result = supervisor.stop("phone-1", "capture-stop")

    assert result is session
    assert session.state == "STOPPING"
    assert signal.is_file()
    assert not session.process.terminated


def test_v2_capture_route_returns_consent_epoch_without_replacing_runner_generation(tmp_path: Path) -> None:
    """The consent epoch is a media-security fence, not an RTSP retry counter."""
    app = build_app(GatewaySettings("pair-code", None, None, tmp_path, "ingress-key", database_path=tmp_path / "gateway.sqlite3"))
    client = TestClient(app)
    token = pair(client)
    supervisor = app.state.capture_supervisor
    request = {
        "session_id": "capture-v2-epoch-1",
        "capture_generation": 1,
        "rtsp_port": 8554,
        "rtsp_path": "live",
        "learner_id": "learner-1",
        "capture_consent_id": "consent-2",
        "consent_generation": 2,
        "capture_epoch": 2,
    }

    with (
        patch.object(supervisor, "_rtsp_url", return_value="rtsp://127.0.0.1:8554/live"),
        patch.object(supervisor, "_spawn_runner_locked"),
    ):
        response = client.post("/api/capture-sessions", json=request, headers=headers(token))

    assert response.status_code == 202
    payload = response.json()
    assert payload["capture_epoch"] == 2
    assert payload["capture_generation"] == 1
    assert payload["media_route_lease_id"]
    route = supervisor.media_route("phone-1", request["session_id"])
    assert route is not None
    assert route[2] == 2
    session = supervisor.get("phone-1", request["session_id"])
    assert session is not None
    assert session.capture_generation == 1


def test_capture_supervisor_shutdown_signals_owned_runner_before_gateway_exit(tmp_path: Path) -> None:
    settings = GatewaySettings("pair-code", None, None, tmp_path, "ingress-key")
    supervisor = LanCaptureSupervisor(settings)
    signal = tmp_path / "session" / ".stop-requested"
    session = CaptureSession("capture-shutdown", "phone-1", "rtsp://127.0.0.1:8554/live", tmp_path / "session", "RUNNING", "now")
    session.stop_signal_file = signal
    session.process = _CaptureProcess(exit_code=None, final_code=0)  # type: ignore[assignment]
    supervisor._sessions[("phone-1", "capture-shutdown")] = session

    supervisor.shutdown(grace_seconds=0.0)

    assert session.state == "STOPPING"
    assert signal.is_file()


def test_capture_supervisor_timeout_cleanup_removes_runner_process_tree(tmp_path: Path) -> None:
    # This is deliberately a real Windows process-tree test rather than a mock:
    # killing only the runner PID is the regression that previously left lane
    # workers alive after a gateway settlement timeout.
    runner_code = (
        "import subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "print(child.pid, flush=True); time.sleep(60)"
    )
    runner = subprocess.Popen(
        [sys.executable, "-c", runner_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert runner.stdout is not None
        child_pid = int(runner.stdout.readline().strip())
        LanCaptureSupervisor._terminate_process_tree(runner)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if not _process_is_alive(child_pid):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("runner_descendant_survived_tree_cleanup")
        assert runner.poll() is not None
    finally:
        if runner.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(runner.pid), "/T", "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                runner.kill()


def test_paired_phone_sees_explicit_provider_unavailable_status(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)

    response = client.get("/api/agent/status", headers=headers(token))

    assert response.status_code == 200
    assert response.json()["state"] == "UNAVAILABLE"
    assert response.json()["connectivity"] == "UNCONFIGURED"


def test_unconfigured_provider_fails_a_real_agent_run_instead_of_fabricating_answer(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    body = {
        "client_request_id": "request-1",
        "conversation_id": "conversation-1",
        "mode": "ANSWER",
        "prompt": "请解释这条会话。",
        "contexts": [],
        "resources": [],
    }

    response = client.post("/api/agent/runs", json=body, headers=headers(token))

    assert response.status_code == 200
    assert response.json()["state"] == "FAILED"
    assert response.json()["answer"] is None
    assert response.json()["error"]["code"] == "agent_provider_unconfigured"


def test_agent_run_requires_paired_token(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/agent/runs",
        json={
            "client_request_id": "request-1",
            "conversation_id": "conversation-1",
            "mode": "ANSWER",
            "prompt": "test",
        },
    )

    assert response.status_code == 401


def test_unpair_revokes_token_for_every_authenticated_endpoint(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)

    revoked = client.delete("/api/mobile-outbox/devices/me", headers=headers(token))
    after_revoke = client.get("/api/agent/status", headers=headers(token))

    assert revoked.status_code == 204
    assert after_revoke.status_code == 401


def test_legacy_unpair_stops_its_capture_worker_without_deleting_sealed_evidence(tmp_path: Path) -> None:
    app = build_app(GatewaySettings("pair-code", None, None, tmp_path, "ingress-key", database_path=tmp_path / "gateway.sqlite3"))
    client = TestClient(app)
    token = pair(client)
    session = CaptureSession(
        "capture-legacy-revoke", "phone-1", "rtsp://127.0.0.1:8554/live", tmp_path / "legacy-session", "RUNNING", "now"
    )
    session.stop_signal_file = session.output_dir.parent / ".capture-legacy-revoke.stop-requested"
    app.state.capture_supervisor._sessions[(session.device_id, session.session_id)] = session
    sealed_evidence = session.output_dir / "sealed-fragment.json"
    sealed_evidence.parent.mkdir(parents=True)
    sealed_evidence.write_text('{"sealed":true}', encoding="utf-8")

    response = client.delete("/api/mobile-outbox/devices/me", headers=headers(token))

    assert response.status_code == 204
    assert session.state == "STOPPING"
    assert session.stop_signal_file.is_file()
    assert session.preserve_completed_evidence is True
    assert sealed_evidence.read_text(encoding="utf-8") == '{"sealed":true}'


def test_capture_stop_fences_late_v2_uploads_without_revoking_buffered_evidence(tmp_path: Path) -> None:
    app = build_app(GatewaySettings("pair-code", None, None, tmp_path, "ingress-key", database_path=tmp_path / "gateway.sqlite3"))
    client = TestClient(app)
    token = pair(client)
    session = CaptureSession(
        "capture-v2-stop", "phone-1", "rtsp://127.0.0.1:8554/live", tmp_path / "session", "RUNNING", "now",
        direct_v2_egress=True,
    )
    app.state.capture_supervisor._sessions[(session.device_id, session.session_id)] = session
    with patch.object(app.state.media_security, "close_capture_session", wraps=app.state.media_security.close_capture_session) as close:
        response = client.post(f"/api/capture-sessions/{session.session_id}/stop", headers=headers(token))

    assert response.status_code == 202
    assert response.json()["state"] == "STOPPED"
    close.assert_called_once_with(session.session_id, device_id="phone-1")


def test_pairing_code_is_rate_limited_after_repeated_failures(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    for _ in range(5):
        response = client.post(
            "/api/mobile-outbox/devices/pair",
            json={"device_id": "phone-rate", "pairing_token": "wrong"},
        )
        assert response.status_code == 403
    rate_limited = client.post(
        "/api/mobile-outbox/devices/pair",
        json={"device_id": "phone-rate", "pairing_token": "pair-code"},
    )
    assert rate_limited.status_code == 429


def test_pairing_creates_a_long_lived_but_revocable_device_credential(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    paired = client.post(
        "/api/mobile-outbox/devices/pair",
        json={"device_id": "phone-long-lived", "pairing_token": "pair-code"},
    )

    assert paired.status_code == 200
    expires_at = datetime.fromisoformat(paired.json()["expires_at"])
    assert (expires_at - datetime.now(timezone.utc)).days >= 364


def test_existing_unrevoked_short_lived_pairing_is_migrated_without_manual_repair(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    paired = client.post(
        "/api/mobile-outbox/devices/pair",
        json={"device_id": "phone-migrate", "pairing_token": "pair-code"},
    )
    token = paired.json()["access_token"]
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        connection.execute("UPDATE devices SET token_expires_at=? WHERE device_id=?", ("2000-01-01T00:00:00+00:00", "phone-migrate"))
        connection.commit()

    resumed = make_client(tmp_path).get("/api/mobile-outbox/messages?device_id=phone-migrate", headers=headers(token))

    assert resumed.status_code == 200
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        renewed = connection.execute("SELECT token_expires_at FROM devices WHERE device_id=?", ("phone-migrate",)).fetchone()[0]
    assert (datetime.fromisoformat(renewed) - datetime.now(timezone.utc)).days >= 364


def test_legacy_analysis_worker_cannot_enqueue_or_poll_a_candidate_payload(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    payload = {"schema_version": "mobile_result_message.v1", "message_type": "ANALYSIS_RESULT", "analysis_result": {}}

    first = client.post(
        "/api/mobile-outbox/messages",
        json={"device_id": "phone-1", "message_id": "delivery-1", "payload": payload},
        headers={"X-Zhixing-Ingress-Key": "ingress-key"},
    )
    delivered = client.get("/api/mobile-outbox/messages?device_id=phone-1", headers=headers(token))

    assert first.status_code == 410
    assert first.json()["detail"]["code"] == "legacy_v1_ingress_disabled"
    assert delivered.json()["messages"] == []


def test_gateway_quarantines_historic_v1_delivery_rows_on_restart(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    payload = {"schema_version": "mobile_result_message.v1", "message_type": "ANALYSIS_RESULT", "analysis_result": {}}
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        connection.execute(
            """
            INSERT INTO outbox(device_id, message_id, payload_json, payload_sha256, created_at, expires_at,
                               state, lease_token, lease_until, delivery_count)
            VALUES(?, ?, ?, ?, ?, ?, 'PENDING', NULL, NULL, 0)
            """,
            (
                "phone-1", "delivery-2", payload_json, hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                "2026-07-30T00:00:00+00:00", "2030-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()
    restarted = make_client(tmp_path)
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        state, reason = connection.execute(
            "SELECT state, last_error FROM outbox WHERE device_id=? AND message_id=?", ("phone-1", "delivery-2")
        ).fetchone()
    assert (state, reason) == ("LEGACY_READ_ONLY", "legacy_v1_delivery_disabled")
    assert restarted.get("/api/mobile-outbox/messages?device_id=phone-1", headers=headers(token)).json()["messages"] == []


def test_ack_requires_the_active_delivery_lease(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    # This direct database fixture exercises the generic historic lease guard;
    # public ingress cannot create this row and v1 is quarantined before lease.
    payload = {"schema_version": "test.outbox.v2"}
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        connection.execute(
            """INSERT INTO outbox(device_id,message_id,payload_json,payload_sha256,created_at,expires_at,state,delivery_count)
               VALUES(?,?,?,?,?,?, 'PENDING', 0)""",
            ("phone-1", "delivery-3", payload_json, hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
             "2026-07-30T00:00:00+00:00", "2030-01-01T00:00:00+00:00"),
        )
        connection.commit()
    rejected = client.post(
        "/api/mobile-outbox/messages/ack",
        json={"device_id": "phone-1", "message_id": "delivery-3", "delivery_token": "wrong"},
        headers=headers(token),
    )
    assert rejected.status_code == 409


def test_expired_delivery_lease_cannot_ack_or_nack_before_a_new_poll(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    payload = {"schema_version": "test.outbox.v2"}
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        connection.execute(
            """INSERT INTO outbox(device_id,message_id,payload_json,payload_sha256,created_at,expires_at,state,delivery_count)
               VALUES(?,?,?,?,?,?, 'PENDING', 0)""",
            ("phone-1", "delivery-expired", payload_json, hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
             "2026-07-30T00:00:00+00:00", "2030-01-01T00:00:00+00:00"),
        )
        connection.commit()
    delivery = client.get("/api/mobile-outbox/messages?device_id=phone-1", headers=headers(token)).json()["messages"][0]
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        connection.execute("UPDATE outbox SET lease_until=? WHERE device_id=? AND message_id=?", ("2000-01-01T00:00:00+00:00", "phone-1", "delivery-expired"))
        connection.commit()
    for endpoint, body in (
        ("ack", {"device_id": "phone-1", "message_id": "delivery-expired", "delivery_token": delivery["delivery_token"]}),
        ("nack", {"device_id": "phone-1", "message_id": "delivery-expired", "delivery_token": delivery["delivery_token"], "reason": "late", "retryable": False}),
    ):
        response = client.post(f"/api/mobile-outbox/messages/{endpoint}", json=body, headers=headers(token))
        assert response.status_code == 409


def test_retryable_nack_waits_then_dead_letters_with_an_immutable_audit(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    payload_json = json.dumps({"schema_version": "test.outbox.v2"}, sort_keys=True, separators=(",", ":"))
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        connection.execute(
            """INSERT INTO outbox(device_id,message_id,payload_json,payload_sha256,created_at,expires_at,state,delivery_count)
               VALUES(?,?,?,?,?,?, 'PENDING', 0)""",
            ("phone-1", "retrying", payload_json, hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
             "2026-07-30T00:00:00+00:00", "2030-01-01T00:00:00+00:00"),
        )
        connection.commit()
    delivery = client.get("/api/mobile-outbox/messages?device_id=phone-1", headers=headers(token)).json()["messages"][0]
    response = client.post(
        "/api/mobile-outbox/messages/nack",
        json={"device_id": "phone-1", "message_id": "retrying", "delivery_token": delivery["delivery_token"], "reason": "local_retry", "retryable": True},
        headers=headers(token),
    )
    assert response.status_code == 204
    assert client.get("/api/mobile-outbox/messages?device_id=phone-1", headers=headers(token)).json()["messages"] == []
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        state, retry_count, next_attempt = connection.execute(
            "SELECT state, retry_count, next_attempt_at FROM outbox WHERE device_id=? AND message_id=?", ("phone-1", "retrying")
        ).fetchone()
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM outbox_delivery_rejections WHERE device_id=? AND message_id=?", ("phone-1", "retrying")
        ).fetchone()[0]
    assert state == "RETRY_WAIT"
    assert retry_count == 1
    assert next_attempt is not None
    assert audit_count == 1


def test_revoke_cancels_pending_deliveries_before_a_stale_client_can_poll(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    payload_json = json.dumps({"schema_version": "test.outbox.v2"}, sort_keys=True, separators=(",", ":"))
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        connection.execute(
            """INSERT INTO outbox(device_id,message_id,payload_json,payload_sha256,created_at,expires_at,state,delivery_count)
               VALUES(?,?,?,?,?,?, 'PENDING', 0)""",
            ("phone-1", "revoked", payload_json, hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
             "2026-07-30T00:00:00+00:00", "2030-01-01T00:00:00+00:00"),
        )
        connection.commit()
    assert client.delete("/api/mobile-outbox/devices/me", headers=headers(token)).status_code == 204
    with closing(sqlite3.connect(tmp_path / "gateway.sqlite3")) as connection:
        state, reason = connection.execute(
            "SELECT state, last_error FROM outbox WHERE device_id=? AND message_id=?", ("phone-1", "revoked")
        ).fetchone()
    assert (state, reason) == ("REVOKED", "device_revoked")


def test_uploaded_utf8_resource_is_hashed_persisted_and_available_to_agent_context(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    body = "可引用的学习资料正文。".encode("utf-8")
    uploaded = client.put(
        "/api/agent/resources/resource-1",
        content=body,
        headers={
            **headers(token),
            "Content-Type": "text/plain; charset=utf-8",
            "X-Resource-Name": "study.txt",
            "X-Resource-Sha256": hashlib.sha256(body).hexdigest(),
        },
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["state"] == "READY_FOR_AGENT"


def test_unsupported_resource_is_saved_but_not_misrepresented_as_parse_ready(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    body = b"opaque-binary-resource"
    uploaded = client.put(
        "/api/agent/resources/resource-2",
        content=body,
        headers={
            **headers(token),
            "Content-Type": "application/octet-stream",
            "X-Resource-Name": "study.bin",
            "X-Resource-Sha256": hashlib.sha256(body).hexdigest(),
        },
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["state"] == "FAILED"
    assert uploaded.json()["error"] == "agent_resource_parser_unsupported"


def test_invalid_document_is_not_misrepresented_as_parse_ready(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    body = b"%PDF-synthetic"
    uploaded = client.put(
        "/api/agent/resources/resource-invalid-pdf",
        content=body,
        headers={
            **headers(token),
            "Content-Type": "application/pdf",
            "X-Resource-Name": "broken.pdf",
            "X-Resource-Sha256": hashlib.sha256(body).hexdigest(),
        },
    )

    assert uploaded.status_code == 200
    assert uploaded.json()["state"] == "FAILED"
    assert uploaded.json()["error"] == "agent_document_parse_failed"


def test_knowledge_graph_events_are_durable_idempotent_and_version_checked(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    event = {
        "event_id": "graph-event-1", "entity_kind": "NODE", "entity_id": "student:binary-search",
        "operation": "CREATE", "base_revision": 0,
        "occurred_at": "2026-07-23T12:00:00+08:00",
        "payload": {"label": "二分查找"},
    }
    first = client.post("/api/knowledge-graph/events", json={"events": [event]}, headers=headers(token))
    duplicate = client.post("/api/knowledge-graph/events", json={"events": [event]}, headers=headers(token))
    stale = client.post(
        "/api/knowledge-graph/events",
        json={"events": [{**event, "event_id": "graph-event-2", "operation": "STUDENT_PATCH"}]},
        headers=headers(token),
    )
    restarted = make_client(tmp_path)
    sync = restarted.get("/api/knowledge-graph/sync?after=0", headers=headers(token))

    assert first.json()["results"][0]["state"] == "ACKED"
    assert duplicate.json()["results"][0]["state"] == "DUPLICATE"
    assert stale.json()["results"][0]["state"] == "CONFLICT"
    assert [item["event_id"] for item in sync.json()["events"]] == ["graph-event-1"]


def test_pc_graph_proposal_requires_evidence_and_replays_to_target_phone(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    proposal = {
        "device_id": "phone-1", "event_id": "pc-proposal-1", "entity_kind": "NODE", "entity_id": "pc:topic",
        "operation": "SUGGEST", "base_revision": 0,
        "occurred_at": "2026-07-23T12:00:00+08:00",
        "payload": {"evidence_refs": ["local://pc/one.json"], "analysis_result": {"schema_version": "pc_knowledge_analysis_result.v1"}},
    }
    accepted = client.post("/api/knowledge-graph/proposals", json=proposal, headers={"X-Zhixing-Ingress-Key": "ingress-key"})
    missing_evidence = client.post(
        "/api/knowledge-graph/proposals",
        json={**proposal, "event_id": "pc-proposal-2", "entity_id": "pc:bad", "payload": {}},
        headers={"X-Zhixing-Ingress-Key": "ingress-key"},
    )
    synced = client.get("/api/knowledge-graph/sync?after=0", headers=headers(token))

    assert accepted.status_code == 202
    assert missing_evidence.status_code == 422
    assert synced.json()["events"][0]["actor"] == "PC_AI"


def test_openai_compatible_provider_uses_bearer_contract_and_returns_text(tmp_path: Path) -> None:
    settings = GatewaySettings(
        "pair-code", None, None, tmp_path, "ingress-key",
        ai_provider="openai_compatible",
        openai_base_url="https://provider.invalid/v1",
        openai_api_key="test-key",
        openai_model="test-model",
    )
    request = AgentRunRequest(client_request_id="request-1", conversation_id="conversation-1", mode="ANSWER", prompt="解释二分查找")
    original = httpx.AsyncClient

    def handler(incoming: httpx.Request) -> httpx.Response:
        assert incoming.headers["authorization"] == "Bearer test-key"
        if incoming.url.path.endswith("/chat/completions"):
            assert json.loads(incoming.content)["model"] == "test-model"
            return httpx.Response(200, json={"choices": [{"message": {"content": "在有序数组中折半缩小范围。"}}]})
        if incoming.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "test-model"}]})
        return httpx.Response(404)

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    async def exercise() -> None:
        with patch("scripts.local_agent_gateway.httpx.AsyncClient", client_factory):
            answer = await ask_openai_compatible(settings, request, "")
            status = await probe_selected_provider(settings)
        assert answer == "在有序数组中折半缩小范围。"
        assert status["state"] == "READY"
        assert status["connectivity"] == "REACHABLE"

    asyncio.run(exercise())


def test_openai_compatible_provider_maps_401_without_leaking_response_body(tmp_path: Path) -> None:
    settings = GatewaySettings(
        "pair-code", None, None, tmp_path, "ingress-key",
        ai_provider="openai_compatible",
        openai_base_url="https://provider.invalid/v1",
        openai_api_key="test-key",
        openai_model="test-model",
    )
    request = AgentRunRequest(client_request_id="request-1", conversation_id="conversation-1", mode="ANSWER", prompt="test")
    original = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(lambda _: httpx.Response(401, text="provider-private-error"))
        return original(*args, **kwargs)

    async def exercise() -> None:
        with patch("scripts.local_agent_gateway.httpx.AsyncClient", client_factory):
            try:
                await ask_openai_compatible(settings, request, "")
            except AgentProviderError as error:
                assert error.code == "agent_provider_unauthorized"
                assert "provider-private-error" not in error.public_message
            else:
                raise AssertionError("expected provider failure")

    asyncio.run(exercise())
