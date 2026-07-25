from __future__ import annotations

from pathlib import Path
import hashlib
import asyncio
import json
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from scripts.local_agent_gateway import AgentProviderError, AgentRunRequest, GatewaySettings, ask_openai_compatible, build_app, probe_selected_provider


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


def test_analysis_worker_can_enqueue_once_and_paired_phone_can_ack(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    payload = {"schema_version": "mobile_result_message.v1", "message_type": "ANALYSIS_RESULT", "analysis_result": {}}

    first = client.post(
        "/api/mobile-outbox/messages",
        json={"device_id": "phone-1", "message_id": "delivery-1", "payload": payload},
        headers={"X-Zhixing-Ingress-Key": "ingress-key"},
    )
    duplicate = client.post(
        "/api/mobile-outbox/messages",
        json={"device_id": "phone-1", "message_id": "delivery-1", "payload": payload},
        headers={"X-Zhixing-Ingress-Key": "ingress-key"},
    )
    delivered = client.get("/api/mobile-outbox/messages?device_id=phone-1", headers=headers(token))
    delivery_token = delivered.json()["messages"][0]["delivery_token"]
    acknowledged = client.post(
        "/api/mobile-outbox/messages/ack",
        json={"device_id": "phone-1", "message_id": "delivery-1", "delivery_token": delivery_token},
        headers=headers(token),
    )

    assert first.json()["state"] == "QUEUED"
    assert duplicate.json()["state"] == "DUPLICATE"
    assert delivered.json()["messages"][0]["message_id"] == "delivery-1"
    assert acknowledged.status_code == 204


def test_lease_survives_gateway_restart_and_nack_is_auditable(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    payload = {"schema_version": "mobile_result_message.v1", "message_type": "ANALYSIS_RESULT", "analysis_result": {}}
    queued = client.post(
        "/api/mobile-outbox/messages",
        json={"device_id": "phone-1", "message_id": "delivery-2", "payload": payload},
        headers={"X-Zhixing-Ingress-Key": "ingress-key"},
    )
    assert queued.status_code == 202
    restarted = make_client(tmp_path)
    delivery = restarted.get("/api/mobile-outbox/messages?device_id=phone-1", headers=headers(token)).json()["messages"][0]
    rejected = restarted.post(
        "/api/mobile-outbox/messages/nack",
        json={
            "device_id": "phone-1", "message_id": "delivery-2",
            "delivery_token": delivery["delivery_token"], "reason": "rejected_schema_or_gate", "retryable": False,
        },
        headers=headers(token),
    )
    assert rejected.status_code == 204
    assert restarted.get("/api/mobile-outbox/messages?device_id=phone-1", headers=headers(token)).json()["messages"] == []


def test_ack_requires_the_active_delivery_lease(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = pair(client)
    payload = {"schema_version": "mobile_result_message.v1", "message_type": "ANALYSIS_RESULT", "analysis_result": {}}
    client.post(
        "/api/mobile-outbox/messages",
        json={"device_id": "phone-1", "message_id": "delivery-3", "payload": payload},
        headers={"X-Zhixing-Ingress-Key": "ingress-key"},
    )
    rejected = client.post(
        "/api/mobile-outbox/messages/ack",
        json={"device_id": "phone-1", "message_id": "delivery-3", "delivery_token": "wrong"},
        headers=headers(token),
    )
    assert rejected.status_code == 409


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
