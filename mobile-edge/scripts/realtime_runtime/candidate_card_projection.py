"""Materialise mobile candidate cards from the durable fused-candidate outbox."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from .candidate_card import build_candidate_card
from .ledger import SealedWindowLedger
from .semantic_state import VisitSemanticProjector, VisitSemanticSnapshot
from .visit_candidate_card import aggregate_visit_cards


def _snapshot_document(snapshot: VisitSemanticSnapshot) -> dict[str, object]:
    return {
        "visit_id": snapshot.visit_id,
        "source_context": snapshot.source_context.value,
        "is_open": snapshot.is_open,
        "closed_at_pts_ns": snapshot.closed_at_pts_ns,
        "can_offer_l1": snapshot.can_offer_l1,
        "l1_ineligibility_reason": snapshot.l1_ineligibility_reason,
        "window_ids": [item.window_id for item in snapshot.windows],
        "classification": snapshot.classification,
    }


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(partial, path)


def project_candidate_cards(*, ledger_path: Path, artifact_root: Path, output_path: Path) -> dict[str, int]:
    """Rebuild deterministic cards and visit state from durable candidate events.

    This is intentionally replayable: no event is consumed, deleted or marked
    superseded.  A running adapter can invoke it after each fusion event; a
    restart produces the same output from the SQLite evidence ledger.
    """

    cards: list[dict[str, object]] = []
    snapshots: list[dict[str, object]] = []
    with SealedWindowLedger(ledger_path) as ledger:
        by_visit: dict[str, list] = defaultdict(list)
        for candidate in ledger.fused_candidate_events():
            by_visit[candidate.visit_id].append(candidate)
        for visit_id, candidates in by_visit.items():
            projector = VisitSemanticProjector()
            for candidate in candidates:
                projector.apply(candidate)
                cards.append(build_candidate_card(candidate, artifact_root=artifact_root))
            snapshot = projector.snapshot(visit_id)
            if snapshot is None:
                raise RuntimeError("projected_visit_missing")
            visit = ledger.visit(visit_id)
            if visit is None:
                raise RuntimeError("candidate_references_unknown_visit")
            if visit.end_pts_ns is not None:
                snapshot = projector.close(visit_id, closed_at_pts_ns=visit.end_pts_ns)
            snapshots.append(_snapshot_document(snapshot))
    cards = aggregate_visit_cards(cards)
    snapshots.sort(key=lambda item: str(item["visit_id"]))
    _write_atomic(
        output_path,
        {
            "schema_version": "candidate_card_projection.v1",
            "classification": "CANDIDATE_ONLY",
            "cards": cards,
            "visits": snapshots,
        },
    )
    return {"cards": len(cards), "visits": len(snapshots)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(project_candidate_cards(ledger_path=args.ledger, artifact_root=args.artifact_root, output_path=args.output), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
