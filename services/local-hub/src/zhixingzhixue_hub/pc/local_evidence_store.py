"""PC 工作台的本机 JSON 证据和 SQLite 索引。"""

from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Mapping


class LocalEvidenceStore:
    """Keep raw evidence local while SQLite indexes only replay metadata."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self.root / "evidence-index.sqlite3",
            check_same_thread=False,
        )
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_index (
                    session_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    record_kind TEXT NOT NULL,
                    record_id TEXT NOT NULL UNIQUE,
                    evidence_uri TEXT NOT NULL UNIQUE,
                    captured_at TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL
                )
                """
            )
            self._connection.commit()

    def write_state(self, session_id: str, state: Mapping[str, Any]) -> None:
        path = self.root / "sessions" / session_id / "state.json"
        self._write_json(path, state)

    def read_state(self, session_id: str) -> dict[str, Any] | None:
        path = self.root / "sessions" / session_id / "state.json"
        if not path.is_file():
            return None
        return self._read_json(path)

    def append_evidence(
        self,
        *,
        session_id: str,
        task_id: str,
        record_kind: str,
        record_id: str,
        captured_at: str,
        payload: Mapping[str, Any],
    ) -> str:
        relative_path = Path("sessions") / session_id / record_kind / f"{record_id}.json"
        path = self.root / relative_path
        if path.exists():
            raise ValueError("immutable_evidence_record_already_exists")
        serialised = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        content_sha256 = sha256(serialised.encode("utf-8")).hexdigest()
        self._write_text(path, serialised)
        evidence_uri = f"local://pc/{session_id}/{record_kind}/{record_id}.json"
        try:
            with self._lock:
                self._connection.execute(
                    """
                    INSERT INTO evidence_index (
                        session_id, task_id, record_kind, record_id, evidence_uri, captured_at, content_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        task_id,
                        record_kind,
                        record_id,
                        evidence_uri,
                        captured_at,
                        content_sha256,
                    ),
                )
                self._connection.commit()
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return evidence_uri

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("local_evidence_json_must_be_an_object")
        return payload

    @staticmethod
    def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
        serialised = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        LocalEvidenceStore._write_text(path, serialised)

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
