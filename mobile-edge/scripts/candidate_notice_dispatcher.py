"""Deliver fresh current-visit candidate evidence to the authorized Android app."""

from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import subprocess
import time
from pathlib import Path

from realtime_runtime.candidate_card import CandidateCardBuildError, build_candidate_card
from realtime_runtime.contracts import FusedCandidate, FusionMode, SourceContext


COMPONENT = "cn.zhixingzhixue.mobile/cn.zhixingzhixue.edge.android.CandidateNoticeReceiver"
ACTION = "cn.zhixingzhixue.mobile.action.SHOW_CANDIDATE_NOTICE"


def _l1_eligibility(*, fusion_mode: str, is_current_visit: bool, is_fresh: bool) -> tuple[bool, str]:
    """L1 is evidence eligibility, never a dwell-time or notification-count level.

    L2–L4 are student-initiated learning paths and must not be selected here.
    """

    if not is_current_visit:
        return False, "VISIT_NO_LONGER_ACTIVE"
    if fusion_mode != "TRIMODAL":
        return False, "TRIMODAL_EVIDENCE_REQUIRED"
    if not is_fresh:
        return False, "LIVE_EDGE_LAG_EXCEEDED"
    return True, "CURRENT_TRIMODAL_CANDIDATE"


def _wire_card_payload(card: dict[str, object]) -> str:
    """Encode a Unicode card as one safe adb-shell token without quote splitting."""

    source = json.dumps(card, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(source).decode("ascii")


def _eligible_candidates(ledger_path: Path, artifact_root: Path, maximum_lag_ns: int) -> list[tuple[dict[str, object], str]]:
    with sqlite3.connect(ledger_path) as connection:
        connection.row_factory = sqlite3.Row
        edge = connection.execute("SELECT MAX(end_pts_ns) FROM fragments").fetchone()[0]
        if edge is None:
            return []
        active = connection.execute("SELECT visit_id, start_pts_ns FROM visits WHERE end_pts_ns IS NULL ORDER BY start_pts_ns DESC LIMIT 1").fetchone()
        if active is None:
            return []
        rows = connection.execute(
            """
            SELECT * FROM fused_candidate_events
            WHERE visit_id = ? AND fusion_mode = 'TRIMODAL'
            ORDER BY start_pts_ns, end_pts_ns, window_id
            """,
            (active["visit_id"],),
        ).fetchall()
        eligible: list[tuple[dict[str, object], str]] = []
        for row in rows:
            allowed, reason = _l1_eligibility(
                fusion_mode="TRIMODAL",
                is_current_visit=True,
                is_fresh=int(edge) - int(row["end_pts_ns"]) <= maximum_lag_ns,
            )
            if not allowed:
                continue
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
                eligible.append((build_candidate_card(candidate, artifact_root=artifact_root), reason))
            except CandidateCardBuildError:
                continue
        return eligible


def _send(adb: str, serial: str, card: dict[str, object]) -> tuple[bool, str]:
    window_id = str(card["window_id"])
    message = str(card["display_excerpt"])
    encoded_card = _wire_card_payload(card)
    command = [
        adb, "-s", serial, "shell", "am", "broadcast", "-n", COMPONENT, "-a", ACTION,
        "--es", "window_id", window_id,
        "--es", "title", "发现一段可回看内容",
        "--es", "message", message,
        "--es", "candidate_card_b64", encoded_card,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=12)
    detail = ((completed.stdout or "") + (completed.stderr or "")).strip()
    return completed.returncode == 0 and "Broadcast completed" in detail, detail[:1000]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-lag-seconds", type=float, default=10.0)
    parser.add_argument("--minimum-interval-seconds", type=float, default=60.0)
    args = parser.parse_args()
    if args.maximum_lag_seconds < 0 or args.minimum_interval_seconds < 0:
        raise SystemExit("notification durations must be non-negative")
    recorded: set[str] = set()
    last_sent = 0.0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8", newline="\n") as output:
        while True:
            for card, eligibility_reason in _eligible_candidates(args.ledger, args.artifact_root, int(args.maximum_lag_seconds * 1_000_000_000)):
                window_id = str(card["window_id"])
                if window_id in recorded:
                    continue
                if time.monotonic() - last_sent < args.minimum_interval_seconds:
                    continue
                ok, detail = _send(args.adb, args.serial, card)
                event = {"window_id": window_id, "pc_monotonic_ns": time.monotonic_ns(), "stage": "L1_ELIGIBLE", "eligibility_reason": eligibility_reason, "status": "DELIVERED_HEADS_UP" if ok else "FAILED", "detail": detail}
                output.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                output.flush()
                if ok:
                    recorded.add(window_id)
                    last_sent = time.monotonic()
            time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
