"""PC 独立学习工作台的本地用例编排。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from threading import Event, RLock, Thread, current_thread
from typing import Any
from uuid import uuid4

from zhixingzhixue_hub.pc.foreground_capture import (
    ForegroundCaptureUnavailable,
    ForegroundWindowProbe,
    WindowsForegroundWindowProbe,
)
from zhixingzhixue_hub.pc.local_evidence_store import LocalEvidenceStore
from zhixingzhixue_hub.pc.task_workbench import (
    add_pc_task_phase,
    create_pc_task_session,
    record_pc_environment_fact,
)
from zhixingzhixue_hub.timeline.aligner import build_pc_timeline


class WorkbenchRuntimeError(ValueError):
    """Raised when a UI command conflicts with the PC task lifecycle."""


def _current_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class PCLearningWorkbenchRuntime:
    """One local, explicitly started PC task and its replayable fact ledger."""

    def __init__(
        self,
        evidence_root: Path,
        *,
        probe: ForegroundWindowProbe | None = None,
        now: Callable[[], str] = _current_timestamp,
        sample_interval_seconds: float = 1.0,
    ) -> None:
        if sample_interval_seconds <= 0:
            raise ValueError("sample_interval_seconds_must_be_positive")
        self._store = LocalEvidenceStore(evidence_root)
        self._probe = probe or WindowsForegroundWindowProbe()
        self._now = now
        self._sample_interval_seconds = sample_interval_seconds
        self._state: dict[str, Any] | None = None
        self._last_fingerprint: tuple[int, int, str, str, str] | None = None
        self._lock = RLock()
        self._sampler_stop = Event()
        self._sampler_thread: Thread | None = None
        self._candidate_links: list[dict[str, Any]] = []

    def start_task(
        self,
        payload: Mapping[str, Any],
        *,
        start_sampler: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            if self._is_active():
                raise WorkbenchRuntimeError("pc_task_already_active")
            started_at = self._now()
            task = create_pc_task_session(
                {
                    "session_id": payload.get("session_id") or f"pc-session-{uuid4()}",
                    "task_id": payload.get("task_id") or f"pc-task-{uuid4()}",
                    "task_type": payload.get("task_type"),
                    "goal": payload.get("goal"),
                    "knowledge_tags": payload.get("knowledge_tags"),
                    "started_at": started_at,
                    "source": "pc",
                }
            )
            phase = add_pc_task_phase(
                task,
                {
                    "phase_id": f"pc-phase-{uuid4()}",
                    "task_id": task["task_id"],
                    "phase_type": payload.get("phase_type") or "watch",
                    "started_at": started_at,
                    "source": "pc",
                },
            )
            self._state = {
                "task": task,
                "current_phase": phase,
                "closed_phases": [],
                "events": [],
                "status": "ACTIVE",
                "capture_status": "ACTIVE",
                "capture_quality_flags": [],
            }
            self._last_fingerprint = None
            self._persist_state()
        if start_sampler:
            self._start_sampler()
        return task

    def switch_phase(self, phase_type: str) -> dict[str, Any]:
        if not isinstance(phase_type, str) or not phase_type.strip():
            raise WorkbenchRuntimeError("phase_type_required")
        with self._lock:
            state = self._require_active_state()
            self._close_current_phase(state, self._now())
            task = state["task"]
            state["current_phase"] = add_pc_task_phase(
                task,
                {
                    "phase_id": f"pc-phase-{uuid4()}",
                    "task_id": task["task_id"],
                    "phase_type": phase_type.strip(),
                    "started_at": self._now(),
                    "source": "pc",
                },
            )
            self._last_fingerprint = None
            self._persist_state()
            return dict(state["current_phase"])

    def capture_foreground_once(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._is_active():
                return None
            state = self._require_active_state()
            try:
                sample = self._probe.read_foreground_window()
            except ForegroundCaptureUnavailable as error:
                state["capture_quality_flags"] = [str(error)]
                self._persist_state()
                return None
            if sample.fingerprint == self._last_fingerprint:
                return None

            captured_at = self._now()
            event_id = f"pc-window-{uuid4()}"
            task = state["task"]
            phase = state["current_phase"]
            quality_flags = [] if sample.process_path else ["process_path_unavailable"]
            evidence_uri = self._store.append_evidence(
                session_id=task["session_id"],
                task_id=task["task_id"],
                record_kind="events",
                record_id=event_id,
                captured_at=captured_at,
                payload={
                    "schema_version": "pc_foreground_evidence.v1",
                    "captured_at": captured_at,
                    "capture_method": "win32_foreground_window_poll",
                    "window_handle": sample.window_handle,
                    "process_id": sample.process_id,
                    "process_path": sample.process_path,
                    "window_title": sample.window_title,
                    "window_class": sample.window_class,
                    "quality_flags": quality_flags,
                },
            )
            event = record_pc_environment_fact(
                task,
                {
                    "event_id": event_id,
                    "session_id": task["session_id"],
                    "task_id": task["task_id"],
                    "phase_id": phase["phase_id"],
                    "source": "pc",
                    "modality": "behavior",
                    "event_type": "foreground_window",
                    "start_ts": captured_at,
                    "end_ts": captured_at,
                    "confidence": 1.0,
                    "quality_flags": quality_flags,
                    "evidence_uri": evidence_uri,
                    "privacy_level": "local_only",
                    "review_status": "auto",
                },
            )
            state["events"].append(event)
            state["capture_quality_flags"] = quality_flags
            self._last_fingerprint = sample.fingerprint
            self._persist_state()
            return event

    def stop_task(self) -> dict[str, Any]:
        with self._lock:
            state = self._require_active_state()
            self._close_current_phase(state, self._now())
            state["status"] = "COMPLETED"
            state["capture_status"] = "STOPPED"
            self._last_fingerprint = None
            self._persist_state()
            task = dict(state["task"])
            task["status"] = "COMPLETED"
        self._stop_sampler()
        return task

    def ingest_phone_candidate(
        self,
        candidate: Mapping[str, Any],
        *,
        linked_session_id: str,
    ) -> dict[str, Any]:
        schema_version = candidate.get("schema_version")
        candidate_id = candidate.get("candidate_id")
        status = candidate.get("status")
        if schema_version != "candidate_card.v1":
            raise WorkbenchRuntimeError("phone_candidate_schema_version_not_supported")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise WorkbenchRuntimeError("phone_candidate_id_required")
        if status != "CANDIDATE_ONLY":
            raise WorkbenchRuntimeError("phone_candidate_must_remain_candidate_only")
        if not isinstance(linked_session_id, str) or not linked_session_id.strip():
            raise WorkbenchRuntimeError("linked_session_id_required")
        link_id = f"phone-candidate-link-{uuid4()}"
        link = {
            "link_id": link_id,
            "linked_session_id": linked_session_id,
            "association_type": "USER_CONFIRMED_SESSION_LINK",
            "candidate": dict(candidate),
        }
        self._store.append_evidence(
            session_id=linked_session_id,
            task_id="phone-candidate-link",
            record_kind="phone-candidates",
            record_id=link_id,
            captured_at=self._now(),
            payload={
                "schema_version": "pc_phone_candidate_link.v1",
                **link,
            },
        )
        with self._lock:
            self._candidate_links.append(link)
        return dict(link)

    def dashboard(self) -> dict[str, Any]:
        with self._lock:
            if self._state is None:
                return {
                    "active_task": None,
                    "capture": {"status": "IDLE", "quality_flags": []},
                    "timeline": None,
                    "phone_candidates": [],
                }
            task = dict(self._state["task"])
            task["status"] = self._state["status"]
            session_id = task["session_id"]
            return {
                "active_task": task,
                "capture": {
                    "status": self._state["capture_status"],
                    "quality_flags": list(self._state["capture_quality_flags"]),
                },
                "timeline": self._build_live_timeline(),
                "phone_candidates": [
                    dict(link["candidate"])
                    for link in self._candidate_links
                    if link["linked_session_id"] == session_id
                ],
            }

    def close(self) -> None:
        self._stop_sampler()
        self._store.close()

    def _build_live_timeline(self) -> dict[str, Any]:
        state = self._require_state()
        phases = [*state["closed_phases"]]
        if state["status"] == "ACTIVE":
            current_phase = dict(state["current_phase"])
            current_phase["ended_at"] = self._now()
            phases.append(current_phase)
        return build_pc_timeline(state["task"], state["events"], phases=phases)

    def _close_current_phase(self, state: dict[str, Any], ended_at: str) -> None:
        current_phase = dict(state["current_phase"])
        current_phase["ended_at"] = ended_at
        state["closed_phases"].append(current_phase)

    def _persist_state(self) -> None:
        state = self._require_state()
        self._store.write_state(state["task"]["session_id"], state)

    def _require_state(self) -> dict[str, Any]:
        if self._state is None:
            raise WorkbenchRuntimeError("pc_task_not_started")
        return self._state

    def _require_active_state(self) -> dict[str, Any]:
        state = self._require_state()
        if not self._is_active():
            raise WorkbenchRuntimeError("pc_task_not_active")
        return state

    def _is_active(self) -> bool:
        return self._state is not None and self._state["status"] == "ACTIVE"

    def _start_sampler(self) -> None:
        with self._lock:
            if self._sampler_thread is not None and self._sampler_thread.is_alive():
                return
            self._sampler_stop.clear()
            self._sampler_thread = Thread(
                target=self._sample_loop,
                name="zhixing-pc-foreground-capture",
                daemon=True,
            )
            self._sampler_thread.start()

    def _stop_sampler(self) -> None:
        self._sampler_stop.set()
        thread = self._sampler_thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=self._sample_interval_seconds + 1)
        self._sampler_thread = None

    def _sample_loop(self) -> None:
        while not self._sampler_stop.is_set():
            self.capture_foreground_once()
            self._sampler_stop.wait(self._sample_interval_seconds)
