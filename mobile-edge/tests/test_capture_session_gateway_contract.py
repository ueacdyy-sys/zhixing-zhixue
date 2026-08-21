from __future__ import annotations

import sys
import tempfile
import unittest
import json
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.capture_session_policy import CaptureMode, CaptureOutputState, CaptureSessionPolicy  # noqa: E402
from scripts.local_agent_gateway import CaptureSession, CaptureSessionStartRequest, GatewaySettings, LanCaptureSupervisor  # noqa: E402


class _CaptureProcess:
    def __init__(self, exit_code: int | None, final_code: int = 0) -> None:
        self.exit_code = exit_code
        self.final_code = final_code

    def poll(self) -> int | None:
        return self.exit_code

    def wait(self, timeout: float | None = None) -> int:
        return self.final_code

    def terminate(self) -> None:
        self.exit_code = self.final_code


class CaptureSessionGatewayContractTests(unittest.TestCase):
    def _supervisor(self, root: Path) -> LanCaptureSupervisor:
        return LanCaptureSupervisor(GatewaySettings("pair-code", None, None, root, "ingress-key"))

    def test_selected_app_block_does_not_stop_the_authorized_capture_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            supervisor = self._supervisor(root)
            session = CaptureSession(
                "capture-selected", "phone-1", "rtsp://127.0.0.1:8554/live", root / "session", "RUNNING", "now",
                policy=CaptureSessionPolicy.create(CaptureMode.SELECTED_APPS, ("tv.danmaku.bili",)),
            )
            supervisor._sessions[("phone-1", "capture-selected")] = session

            decision = supervisor.observe_foreground_app("phone-1", "capture-selected", "com.android.settings")

            self.assertEqual(CaptureOutputState.STREAMING_BLOCKED, decision.output_state)
            self.assertEqual("RUNNING", session.state)
            self.assertEqual("com.android.settings", session.last_foreground_package)
            self.assertEqual("STREAMING_BLOCKED", session.response()["capture_output_state"])
            audit = [json.loads(line) for line in session.audit_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual("FOREGROUND_APP_OBSERVED", audit[-1]["event_type"])
            self.assertEqual("com.android.settings", audit[-1]["foreground_package"])
            self.assertEqual("FOREGROUND_APP_NOT_SELECTED", audit[-1]["decision_reason"])

    def test_unexpected_clean_runner_exit_is_an_interruption_that_preserves_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            supervisor = self._supervisor(root)
            output = root / "session"
            artifacts = output / "artifacts"
            artifacts.mkdir(parents=True)
            for lane in ("ocr", "asr", "vlm"):
                (artifacts / f"{lane}-e2e.ready.json").write_text("{}", encoding="utf-8")
            session = CaptureSession(
                "capture-disconnect", "phone-1", "rtsp://127.0.0.1:8554/live", output, "STARTING", "now",
                policy=CaptureSessionPolicy.create(CaptureMode.FULL_CONTINUOUS, ()),
            )
            session.process = _CaptureProcess(exit_code=None, final_code=0)  # type: ignore[assignment]
            supervisor._sessions[("phone-1", "capture-disconnect")] = session

            supervisor._watch(("phone-1", "capture-disconnect"))

            self.assertEqual("INTERRUPTED", session.state)
            self.assertEqual("PC_OBSERVED_SOURCE_DISCONNECT", session.interruption_reason)
            self.assertTrue(session.response()["preserve_completed_evidence"])

    def test_v2_paired_capture_never_starts_the_legacy_rtsp_pull_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runner = root / "run_realtime_e2e.py"
            runner.write_text("", encoding="utf-8")
            supervisor = LanCaptureSupervisor(
                GatewaySettings("pair-code", None, None, root, "ingress-key", realtime_runner=runner),
            )
            request = CaptureSessionStartRequest(
                session_id="capture-no-public-url",
                capture_generation=1,
                rtsp_port=8554,
                rtsp_path="screen",
                capture_mode="FULL_CONTINUOUS",
                learner_id="learner-1",
                capture_consent_id="consent-1",
                consent_generation=1,
                capture_epoch=1,
            )

            with patch.object(supervisor, "_spawn_runner_locked") as spawn:
                session = supervisor.start("phone-1", "127.0.0.1", request)

            self.assertEqual("RUNNING", session.state)
            self.assertIsNone(session.error)
            self.assertTrue(session.direct_v2_egress)
            spawn.assert_not_called()

    def test_runner_command_binds_required_session_id_to_capture_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runner = root / "run_realtime_e2e.py"
            runner.write_text("", encoding="utf-8")
            supervisor = LanCaptureSupervisor(
                GatewaySettings("pair-code", None, None, root, "ingress-key", realtime_runner=runner),
            )
            session = CaptureSession(
                "capture-command-session", "phone-1", "rtsp://127.0.0.1:8554/live", root / "session", "STARTING", "now",
            )
            session.stop_signal_file = root / ".stop-requested"

            with patch("scripts.local_agent_gateway.subprocess.Popen") as start, patch(
                "scripts.local_agent_gateway.threading.Thread"
            ):
                supervisor._spawn_runner_locked(session)

        command = start.call_args.args[0]
        self.assertEqual("capture-command-session", command[command.index("--session-id") + 1])


if __name__ == "__main__":
    unittest.main()
