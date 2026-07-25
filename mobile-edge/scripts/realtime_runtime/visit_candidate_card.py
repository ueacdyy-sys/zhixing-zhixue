"""Create one student-facing candidate card for one analysed video visit.

Realtime windows are immutable PC evidence units.  They must never be exposed
as separate student messages, conversations, or knowledge nodes.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any


_LANES = ("ASR", "OCR", "VLM")


def _unique_text(values: list[str], limit: int = 240) -> str:
    selected: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(value.split())
        if cleaned and cleaned not in seen:
            selected.append(cleaned)
            seen.add(cleaned)
        if len(" ".join(selected)) >= limit:
            break
    return " ".join(selected)[:limit] or "本次视频会话已完成证据分析。"


def aggregate_visit_cards(cards: list[dict[str, object]]) -> list[dict[str, object]]:
    """Merge raw-window cards into one stable card per visit and source.

    The original window ids remain in ``evidence_window_ids`` for PC audit,
    while the mobile-facing id is stable for the whole visit.
    """

    by_visit: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for card in cards:
        by_visit[(str(card["visit_id"]), str(card["source_context"]))].append(card)

    result: list[dict[str, object]] = []
    for (visit_id, source_context), group in by_visit.items():
        ordered = sorted(group, key=lambda card: (int(card["media_range"]["start_pts_ns"]), str(card["window_id"])))
        latest = dict(ordered[-1])
        lane_facts: dict[str, list[dict[str, object]]] = defaultdict(list)
        for card in ordered:
            for fact in card["facts"]:
                lane_facts[str(fact["lane"])].append(fact)
        if set(lane_facts) != set(_LANES):
            continue
        latest["card_id"] = "visit_" + hashlib.sha256(f"{visit_id}:{source_context}".encode("utf-8")).hexdigest()[:20]
        latest["media_range"] = {
            "start_pts_ns": int(ordered[0]["media_range"]["start_pts_ns"]),
            "end_pts_ns": int(ordered[-1]["media_range"]["end_pts_ns"]),
        }
        latest["facts"] = [
            {
                "lane": lane,
                # The first reference is the entry anchor; all window ids stay
                # attached below for the PC evidence ledger.
                "evidence_uri": str(lane_facts[lane][0]["evidence_uri"]),
                "text": _unique_text([str(item["text"]) for item in lane_facts[lane]]),
            }
            for lane in _LANES
        ]
        latest["display_excerpt"] = _unique_text([str(card["display_excerpt"]) for card in ordered])
        latest["evidence_window_ids"] = [str(card["window_id"]) for card in ordered]
        latest["evidence_window_count"] = len(ordered)
        latest["can_offer_l1"] = all(bool(card.get("can_offer_l1", True)) for card in ordered)
        result.append(latest)
    return sorted(result, key=lambda card: int(card["media_range"]["end_pts_ns"]), reverse=True)
