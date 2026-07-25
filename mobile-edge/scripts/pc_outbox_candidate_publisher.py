"""Publish fresh PC candidate cards to a paired phone through the local LAN hub.

This is the production alternative to the ADB diagnostic broadcaster.  It
uses the same evidence gate, retains the current-visit predicate, and sends no
candidate when the shared ingress key is absent.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from candidate_notice_dispatcher import _eligible_candidates
from realtime_runtime.visit_candidate_card import aggregate_visit_cards


def publish(gateway: str, device_id: str, ingress_key: str, card: dict[str, object]) -> tuple[bool, str]:
    message_id = "candidate:" + str(card["card_id"])
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=10)
    payload = {
        "schema_version": "mobile_result_message.v1",
        "message_type": "CANDIDATE_CARD",
        "candidate_card": card,
        "visit_id": str(card["visit_id"]),
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "is_current_visit": True,
        "notice_title": "L1 概念小结",
        "notice_message": "已为你准备概念小结，点击查看。",
    }
    response = requests.post(
        gateway.rstrip("/") + "/api/mobile-outbox/messages",
        headers={"X-Zhixing-Ingress-Key": ingress_key},
        json={"device_id": device_id, "message_id": message_id, "payload": payload, "expires_at": expires_at.isoformat()},
        timeout=12,
    )
    if response.status_code not in {200, 202}:
        return False, f"pc_outbox_http_{response.status_code}"
    return True, str(response.json().get("state", "UNKNOWN"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-lag-seconds", type=float, default=10.0)
    parser.add_argument("--minimum-interval-seconds", type=float, default=60.0)
    args = parser.parse_args()
    if args.maximum_lag_seconds < 0 or args.minimum_interval_seconds < 0:
        raise SystemExit("notification_durations_must_be_non_negative")
    ingress_key = os.environ.get("ZHIXING_ANALYSIS_INGRESS_KEY", "").strip()
    if not ingress_key:
        raise SystemExit("ZHIXING_ANALYSIS_INGRESS_KEY is required")
    recorded: set[str] = set()
    last_sent = 0.0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8", newline="\n") as output:
        while True:
            candidates = _eligible_candidates(
                args.ledger,
                args.artifact_root,
                int(args.maximum_lag_seconds * 1_000_000_000),
            )
            raw_cards = [card for card, _ in candidates]
            reasons = {str(card["visit_id"]): reason for card, reason in candidates}
            for card in aggregate_visit_cards(raw_cards):
                card_id = str(card["card_id"])
                if card_id in recorded or time.monotonic() - last_sent < args.minimum_interval_seconds:
                    continue
                ok, detail = publish(args.gateway, args.device_id, ingress_key, card)
                event = {
                    "card_id": card_id,
                    "pc_monotonic_ns": time.monotonic_ns(),
                    "eligibility_reason": reasons.get(str(card["visit_id"]), "VISIT_AGGREGATED"),
                    "status": "QUEUED_FOR_PAIRED_PHONE" if ok else "FAILED",
                    "detail": detail,
                }
                output.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                output.flush()
                if ok:
                    recorded.add(card_id)
                    last_sent = time.monotonic()
            time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
