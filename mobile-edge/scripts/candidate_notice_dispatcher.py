"""Deliver fresh current-visit candidate evidence to the authorized Android app."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import time
from pathlib import Path


COMPONENT = "cn.zhixingzhixue.mobile/cn.zhixingzhixue.edge.android.CandidateNoticeReceiver"
ACTION = "cn.zhixingzhixue.mobile.action.SHOW_CANDIDATE_NOTICE"


def _message(artifact_root: Path, evidence_uris: list[str]) -> str:
    for uri in evidence_uris:
        if not uri.startswith("local://artifact/"):
            continue
        file = artifact_root / uri.rsplit("/", 1)[-1]
        try:
            document = json.loads(file.read_text(encoding="utf-8"))
            result = document.get("result", {})
            if isinstance(result, dict):
                nested = result.get("raw_model_text")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()[:180]
        except (OSError, json.JSONDecodeError):
            continue
    return "已形成一段同源音视频与文字候选证据，可自主查看。"


def _interest_level(dwell_seconds: float) -> str:
    if dwell_seconds < 3:
        return "L0"
    if dwell_seconds < 8:
        return "L1"
    if dwell_seconds <= 20:
        return "L2"
    return "L3"


def _eligible_candidates(ledger_path: Path, maximum_lag_ns: int) -> list[tuple[str, list[str], str, float]]:
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
            SELECT window_id, end_pts_ns FROM semantic_windows
            WHERE fused_at_ns IS NOT NULL AND visit_id = ? AND fusion_mode = 'TRIMODAL'
            ORDER BY fused_at_ns
            """,
            (active["visit_id"],),
        ).fetchall()
        dwell_seconds = (int(edge) - int(active["start_pts_ns"])) / 1_000_000_000
        level = _interest_level(dwell_seconds)
        eligible: list[tuple[str, list[str], str, float]] = []
        for row in rows:
            if int(edge) - int(row["end_pts_ns"]) > maximum_lag_ns:
                continue
            evidence = connection.execute(
                "SELECT artifact_uri FROM lane_evidence WHERE window_id = ? ORDER BY lane", (row["window_id"],)
            ).fetchall()
            eligible.append((str(row["window_id"]), [str(item["artifact_uri"]) for item in evidence], level, dwell_seconds))
        return eligible


def _send(adb: str, serial: str, window_id: str, message: str) -> tuple[bool, str]:
    command = [
        adb, "-s", serial, "shell", "am", "broadcast", "-n", COMPONENT, "-a", ACTION,
        "--es", "window_id", window_id,
        "--es", "title", "发现一段可回看内容",
        "--es", "message", message,
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
            for window_id, evidence_uris, level, dwell_seconds in _eligible_candidates(args.ledger, int(args.maximum_lag_seconds * 1_000_000_000)):
                if window_id in recorded:
                    continue
                if level in {"L0", "L1", "L2"}:
                    output.write(json.dumps({"window_id": window_id, "pc_monotonic_ns": time.monotonic_ns(), "level": level, "dwell_seconds": dwell_seconds, "status": "CANDIDATE_ONLY_NO_HEADS_UP"}, ensure_ascii=False, separators=(",", ":")) + "\n")
                    output.flush()
                    recorded.add(window_id)
                    continue
                if time.monotonic() - last_sent < args.minimum_interval_seconds:
                    continue
                message = _message(args.artifact_root, evidence_uris)
                ok, detail = _send(args.adb, args.serial, window_id, message)
                event = {"window_id": window_id, "pc_monotonic_ns": time.monotonic_ns(), "level": level, "dwell_seconds": dwell_seconds, "status": "DELIVERED_HEADS_UP" if ok else "FAILED", "detail": detail}
                output.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                output.flush()
                if ok:
                    recorded.add(window_id)
                    last_sent = time.monotonic()
            time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
