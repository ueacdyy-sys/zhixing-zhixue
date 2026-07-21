from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from zhixingzhixue_hub.pc.foreground_capture import ForegroundWindowSample
from zhixingzhixue_hub.pc.workbench_runtime import PCLearningWorkbenchRuntime


@dataclass
class FakeForegroundProbe:
    sample: ForegroundWindowSample

    def read_foreground_window(self) -> ForegroundWindowSample:
        return self.sample


def _sample(*, handle: int, title: str, pid: int = 42) -> ForegroundWindowSample:
    return ForegroundWindowSample(
        window_handle=handle,
        process_id=pid,
        process_path="C:\\Program Files\\Browser\\browser.exe",
        window_title=title,
        window_class="BrowserWindow",
    )


def _runtime(tmp_path: Path) -> tuple[PCLearningWorkbenchRuntime, FakeForegroundProbe]:
    probe = FakeForegroundProbe(_sample(handle=101, title="算法课程 - 浏览器"))
    return PCLearningWorkbenchRuntime(
        tmp_path, probe=probe, now=lambda: "2026-07-21T10:00:00+08:00"
    ), probe


def _start(runtime: PCLearningWorkbenchRuntime) -> dict[str, object]:
    return runtime.start_task(
        {
            "session_id": "ses-pc-runtime-001",
            "task_id": "task-pc-runtime-001",
            "task_type": "video_course",
            "goal": "完成算法课程并记录疑问",
            "knowledge_tags": ["算法", "复杂度"],
            "phase_type": "watch",
        },
        start_sampler=False,
    )


def test_explicit_pc_task_captures_changed_foreground_as_local_replayable_fact(
    tmp_path: Path,
) -> None:
    runtime, probe = _runtime(tmp_path)

    _start(runtime)
    first = runtime.capture_foreground_once()
    repeated = runtime.capture_foreground_once()
    probe.sample = _sample(handle=102, title="复杂度检索 - 浏览器")
    changed = runtime.capture_foreground_once()

    assert first is not None
    assert first["event_type"] == "foreground_window"
    assert first["evidence_uri"].startswith("local://pc/ses-pc-runtime-001/events/")
    assert repeated is None
    assert changed is not None
    assert changed["event_id"] != first["event_id"]
    dashboard = runtime.dashboard()
    assert [entry["event_type"] for entry in dashboard["timeline"]["entries"]] == [
        "foreground_window",
        "foreground_window",
    ]
    assert "learning_diagnosis" not in dashboard["timeline"]


def test_workbench_does_not_capture_before_start_or_after_explicit_stop(tmp_path: Path) -> None:
    runtime, _ = _runtime(tmp_path)

    assert runtime.capture_foreground_once() is None
    _start(runtime)
    assert runtime.capture_foreground_once() is not None
    stopped = runtime.stop_task()

    assert stopped["status"] == "COMPLETED"
    assert runtime.capture_foreground_once() is None


def test_phone_candidate_is_visible_only_when_user_links_it_to_matching_session(
    tmp_path: Path,
) -> None:
    runtime, _ = _runtime(tmp_path)
    _start(runtime)

    runtime.ingest_phone_candidate(
        {
            "schema_version": "candidate_card.v1",
            "candidate_id": "candidate-phone-001",
            "status": "CANDIDATE_ONLY",
            "evidence_refs": ["local://phone/window-1"],
        },
        linked_session_id="ses-pc-runtime-001",
    )
    runtime.ingest_phone_candidate(
        {
            "schema_version": "candidate_card.v1",
            "candidate_id": "candidate-phone-other",
            "status": "CANDIDATE_ONLY",
            "evidence_refs": ["local://phone/window-2"],
        },
        linked_session_id="ses-other",
    )

    visible = runtime.dashboard()["phone_candidates"]

    assert [candidate["candidate_id"] for candidate in visible] == ["candidate-phone-001"]

