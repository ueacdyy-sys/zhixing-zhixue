"""对已对齐的 PC 时间轴做保守候选封装。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import NAMESPACE_URL, uuid5


def build_fast_path_candidate(timeline: Mapping[str, Any]) -> dict[str, Any]:
    """Expose replayable PC activity as a candidate, never as a learning conclusion."""
    entries = timeline.get("entries")
    if not isinstance(entries, list) or not entries:
        return {
            "status": "NO_CANDIDATE",
            "source_mode": "PC_TIMELINE_FAST_PATH",
            "evidence_refs": [],
            "requires_slow_path": True,
        }

    evidence_refs: list[str] = []
    event_refs: list[str] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("timeline_entries_must_be_mappings")
        replay_uri = entry.get("replay_uri")
        event_id = entry.get("event_id")
        if not isinstance(replay_uri, str) or not replay_uri.startswith("local://pc/"):
            raise ValueError("replayable_local_pc_evidence_required")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("timeline_event_id_required")
        evidence_refs.append(replay_uri)
        event_refs.append(event_id)

    candidate_seed = "|".join((str(timeline.get("session_id")), str(timeline.get("task_id")), *event_refs))
    return {
        "status": "CANDIDATE_ONLY",
        "source_mode": "PC_TIMELINE_FAST_PATH",
        "candidate_id": str(uuid5(NAMESPACE_URL, candidate_seed)),
        "session_id": timeline.get("session_id"),
        "task_id": timeline.get("task_id"),
        "event_refs": event_refs,
        "evidence_refs": evidence_refs,
        "requires_slow_path": True,
    }
