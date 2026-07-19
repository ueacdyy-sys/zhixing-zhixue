"""Read-only content-transition facts from an outer interaction adapter."""

from __future__ import annotations

import json
from pathlib import Path


class JsonlTransitionFeed:
    """Consumes append-only gesture facts without inferring a platform or topic."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._offset = 0
        self._pending: list[int] = []

    def consume_before(self, pc_monotonic_ns: int) -> bool:
        if pc_monotonic_ns < 0:
            raise ValueError("transition_clock_invalid")
        if self._path is None:
            return False
        try:
            with self._path.open("r", encoding="utf-8") as source:
                source.seek(self._offset)
                lines = source.readlines()
                self._offset = source.tell()
        except FileNotFoundError:
            return False
        for line in lines:
            try:
                event = json.loads(line)
                event_ns = int(event["pc_monotonic_ns"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if event.get("event_type") == "ContentTransitionCandidate":
                self._pending.append(event_ns)
        eligible = [item for item in self._pending if item <= pc_monotonic_ns]
        self._pending = [item for item in self._pending if item > pc_monotonic_ns]
        return bool(eligible)
