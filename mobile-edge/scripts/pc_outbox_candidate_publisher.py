"""Publish fresh PC candidate cards to a paired phone through the local LAN hub.

This is the production alternative to the ADB diagnostic broadcaster.  It
publishes one durable L0 evidence card after a completed visit, and sends no
candidate when the shared ingress key is absent.  L1 remains a separate,
current-visit interest decision on the phone.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from realtime_runtime.candidate_card import CandidateCardBuildError, build_candidate_card
from realtime_runtime.contracts import FusedCandidate, FusionMode, SourceContext
from realtime_runtime.visit_candidate_card import aggregate_visit_cards


def _gateway_ca_bundle() -> str | bool:
    """Return the explicitly configured private-LAN CA, if any."""
    configured = os.environ.get("REQUESTS_CA_BUNDLE", "").strip()
    return configured if configured else True


def publish(gateway: str, device_id: str, ingress_key: str, card: dict[str, object]) -> tuple[bool, str]:
    message_id = "candidate:" + str(card["card_id"])
    now = datetime.now(timezone.utc)
    # Message persistence must outlive Android's periodic sync interval.  UI
    # freshness remains a separate current-visit decision on the phone.
    expires_at = now + timedelta(minutes=5)
    payload = {
        "schema_version": "mobile_result_message.v1",
        "message_type": "CANDIDATE_CARD",
        "candidate_card": card,
        "visit_id": str(card["visit_id"]),
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        # PC analysis can return a durable L0 evidence candidate when the
        # capture visit closes.  L1 is a separate student-interest decision;
        # do not turn tri-modal media completeness into a heads-up notice.
        "is_current_visit": False,
    }
    session = requests.Session()
    # This is PC -> its paired private-LAN gateway.  Ambient proxy variables
    # can intercept TLS and make a valid private CA fail verification.
    session.trust_env = False
    response = session.post(
        gateway.rstrip("/") + "/api/mobile-outbox/messages",
        headers={"X-Zhixing-Ingress-Key": ingress_key},
        json={"device_id": device_id, "message_id": message_id, "payload": payload, "expires_at": expires_at.isoformat()},
        timeout=12,
        verify=_gateway_ca_bundle(),
    )
    if response.status_code not in {200, 202}:
        return False, f"pc_outbox_http_{response.status_code}"
    return True, str(response.json().get("state", "UNKNOWN"))


def _completed_visit_cards(ledger_path: Path, artifact_root: Path) -> list[tuple[dict[str, object], str]]:
    """Return one non-notifying L0 card per completed visit.

    A screen stream is split into immutable analysis windows internally.  The
    phone must receive one visit-level card rather than dozens of short
    fragments.  Delivery happens after visit closure so its content is stable;
    this function intentionally does not decide L1 eligibility.
    """
    # sqlite3's transaction context manager commits/rolls back but does not
    # close the Windows file handle.  Close it deterministically because this
    # publisher polls the same durable ledger for the life of the session.
    with closing(sqlite3.connect(ledger_path)) as connection:
        connection.row_factory = sqlite3.Row
        visits = connection.execute(
            "SELECT visit_id FROM visits WHERE end_pts_ns IS NOT NULL ORDER BY end_pts_ns"
        ).fetchall()
        result: list[tuple[dict[str, object], str]] = []
        for visit in visits:
            rows = connection.execute(
                """
                SELECT * FROM fused_candidate_events
                WHERE visit_id = ? AND fusion_mode = 'TRIMODAL'
                ORDER BY start_pts_ns, end_pts_ns, window_id
                """,
                (visit["visit_id"],),
            ).fetchall()
            raw: list[dict[str, object]] = []
            for row in rows:
                candidate = FusedCandidate(
                    window_id=str(row["window_id"]),
                    visit_id=str(row["visit_id"]),
                    source_context=SourceContext(row["source_context"]),
                    start_pts_ns=int(row["start_pts_ns"]),
                    end_pts_ns=int(row["end_pts_ns"]),
                    evidence_uris=tuple(json.loads(row["evidence_uris_json"])),
                    fused_at_ns=int(row["fused_at_ns"]),
                    fusion_mode=FusionMode(row["fusion_mode"]),
                    classification=str(row["classification"]),
                )
                try:
                    raw.append(build_candidate_card(candidate, artifact_root=artifact_root))
                except CandidateCardBuildError:
                    continue
            for card in aggregate_visit_cards(raw):
                card["can_offer_l1"] = False
                result.append((card, "COMPLETED_TRIMODAL_VISIT_L0"))
        return result


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
            candidates = _completed_visit_cards(args.ledger, args.artifact_root)
            for card, reason in candidates:
                card_id = str(card["card_id"])
                if card_id in recorded or time.monotonic() - last_sent < args.minimum_interval_seconds:
                    continue
                ok, detail = publish(args.gateway, args.device_id, ingress_key, card)
                event = {
                    "card_id": card_id,
                    "pc_monotonic_ns": time.monotonic_ns(),
                    "eligibility_reason": reason,
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
