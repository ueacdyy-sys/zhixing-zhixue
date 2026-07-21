from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zhixingzhixue_hub.phone.pc_result_outbox import (
    MobileResultOutbox,
    MobileResultOutboxAuthenticationError,
    MobileResultOutboxError,
)


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def _result(*, result_id: str = "result-001") -> dict[str, object]:
    return {
        "schema_version": "pc_knowledge_analysis_result.v1",
        "result_id": result_id,
        "session_id": "mobile-session-001",
        "visit_id": "visit-001",
        "created_at": "2026-07-21T08:00:00+00:00",
        "evidence_refs": ["local://pc/mobile-session-001/fusion/window-001.json"],
        "associations": [
            {
                "association_type": "CANDIDATE_KNOWLEDGE_LINK",
                "from_ref": "candidate-card-001",
                "to_ref": "knowledge-node-algorithm-001",
                "status": "CANDIDATE_ONLY",
            }
        ],
    }


def _pair(outbox: MobileResultOutbox, *, device_id: str = "nova8-001") -> dict[str, str]:
    pairing = outbox.issue_pairing_token()
    return outbox.pair_device(device_id=device_id, pairing_token=pairing["pairing_token"])


def test_pairing_token_is_single_use_and_access_token_is_not_stored_in_clear_text(tmp_path: Path) -> None:
    clock = Clock()
    outbox = MobileResultOutbox(tmp_path, now=clock.now)

    pairing = outbox.issue_pairing_token(ttl_seconds=60)
    paired = outbox.pair_device(device_id="nova8-001", pairing_token=pairing["pairing_token"])

    assert paired["device_id"] == "nova8-001"
    assert paired["access_token"]
    with pytest.raises(MobileResultOutboxAuthenticationError, match="pairing_token_invalid_or_expired"):
        outbox.pair_device(device_id="nova8-002", pairing_token=pairing["pairing_token"])
    raw_database = (tmp_path / "mobile-result-outbox.sqlite3").read_bytes()
    assert pairing["pairing_token"].encode("utf-8") not in raw_database
    assert paired["access_token"].encode("utf-8") not in raw_database


def test_pairing_token_expires(tmp_path: Path) -> None:
    clock = Clock()
    outbox = MobileResultOutbox(tmp_path, now=clock.now)
    pairing = outbox.issue_pairing_token(ttl_seconds=5)
    clock.advance(6)

    with pytest.raises(MobileResultOutboxAuthenticationError, match="pairing_token_invalid_or_expired"):
        outbox.pair_device(device_id="nova8-001", pairing_token=pairing["pairing_token"])


def test_analysis_result_is_persistent_until_authenticated_device_acknowledges(tmp_path: Path) -> None:
    clock = Clock()
    outbox = MobileResultOutbox(tmp_path, now=clock.now)
    paired = _pair(outbox)
    queued = outbox.enqueue_analysis_result(
        device_id="nova8-001",
        analysis_result=_result(),
        idempotency_key="fusion-window-001",
    )
    outbox.close()

    reopened = MobileResultOutbox(tmp_path, now=clock.now)
    pulled = reopened.pull(device_id="nova8-001", access_token=paired["access_token"])

    assert [message["message_id"] for message in pulled] == [queued["message_id"]]
    assert pulled[0]["status"] == "DELIVERED"
    assert pulled[0]["payload"]["analysis_result"]["associations"][0]["status"] == "CANDIDATE_ONLY"
    acknowledged = reopened.acknowledge(
        device_id="nova8-001",
        access_token=paired["access_token"],
        message_id=queued["message_id"],
    )
    assert acknowledged["status"] == "ACKED"
    assert reopened.pull(device_id="nova8-001", access_token=paired["access_token"]) == []


def test_pull_replays_unacknowledged_delivery_and_enqueue_is_idempotent(tmp_path: Path) -> None:
    outbox = MobileResultOutbox(tmp_path, now=Clock().now)
    paired = _pair(outbox)
    first = outbox.enqueue_analysis_result(
        device_id="nova8-001", analysis_result=_result(), idempotency_key="fusion-window-001"
    )
    duplicate = outbox.enqueue_analysis_result(
        device_id="nova8-001", analysis_result=_result(), idempotency_key="fusion-window-001"
    )

    assert duplicate["message_id"] == first["message_id"]
    assert len(outbox.pull(device_id="nova8-001", access_token=paired["access_token"])) == 1
    assert len(outbox.pull(device_id="nova8-001", access_token=paired["access_token"])) == 1
    with pytest.raises(MobileResultOutboxError, match="idempotency_key_reused_with_different_result"):
        outbox.enqueue_analysis_result(
            device_id="nova8-001",
            analysis_result=_result(result_id="result-002"),
            idempotency_key="fusion-window-001",
        )


def test_device_token_cannot_pull_or_ack_another_devices_results(tmp_path: Path) -> None:
    outbox = MobileResultOutbox(tmp_path, now=Clock().now)
    first_device = _pair(outbox, device_id="nova8-001")
    second_device = _pair(outbox, device_id="nova8-002")
    queued = outbox.enqueue_analysis_result(
        device_id="nova8-001", analysis_result=_result(), idempotency_key="fusion-window-001"
    )

    with pytest.raises(MobileResultOutboxAuthenticationError, match="mobile_device_access_denied"):
        outbox.pull(device_id="nova8-001", access_token=second_device["access_token"])
    with pytest.raises(MobileResultOutboxError, match="outbox_message_not_found"):
        outbox.acknowledge(
            device_id="nova8-002",
            access_token=second_device["access_token"],
            message_id=queued["message_id"],
        )
    assert outbox.pull(device_id="nova8-001", access_token=first_device["access_token"])
