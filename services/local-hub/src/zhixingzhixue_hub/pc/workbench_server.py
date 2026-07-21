"""PC 工作台的回环本机 HTTP 控制面。"""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from zhixingzhixue_hub.pc.workbench_runtime import (
    PCLearningWorkbenchRuntime,
    WorkbenchRuntimeError,
)


class WorkbenchRequestHandler(BaseHTTPRequestHandler):
    runtime: PCLearningWorkbenchRuntime

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/dashboard":
            self._write_json(HTTPStatus.OK, self.runtime.dashboard())
            return
        self._write_error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "未找到本机工作台接口。")

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._read_json()
            response = self._dispatch(payload)
        except WorkbenchRuntimeError as error:
            self._write_error(HTTPStatus.CONFLICT, "WORKBENCH_STATE_ERROR", str(error))
            return
        except (TypeError, ValueError) as error:
            self._write_error(HTTPStatus.UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", str(error))
            return
        self._write_json(HTTPStatus.OK, response)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:5173")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, _: str, *args: object) -> None:
        """Do not write potentially sensitive local navigation metadata to stdout."""

    def _dispatch(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.path == "/api/tasks":
            task = self.runtime.start_task(payload)
            return {"task": task, "dashboard": self.runtime.dashboard()}
        if self.path == "/api/phases":
            phase = self.runtime.switch_phase(str(payload.get("phase_type", "")))
            return {"phase": phase, "dashboard": self.runtime.dashboard()}
        if self.path == "/api/capture":
            event = self.runtime.capture_foreground_once()
            return {"event": event, "dashboard": self.runtime.dashboard()}
        if self.path == "/api/tasks/stop":
            task = self.runtime.stop_task()
            return {"task": task, "dashboard": self.runtime.dashboard()}
        if self.path == "/api/phone-candidates":
            candidate = payload.get("candidate")
            if not isinstance(candidate, dict):
                raise ValueError("candidate_must_be_an_object")
            link = self.runtime.ingest_phone_candidate(
                candidate,
                linked_session_id=str(payload.get("linked_session_id", "")),
            )
            return {"link": link, "dashboard": self.runtime.dashboard()}
        raise WorkbenchRuntimeError("route_not_found")

    def _read_json(self) -> dict[str, Any]:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            raise ValueError("content_length_required")
        body = self.rfile.read(int(content_length))
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request_body_must_be_an_object")
        return payload

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:5173")
        self.end_headers()
        self.wfile.write(body)

    def _write_error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._write_json(status, {"error": {"code": code, "message": message}})


def create_server(
    runtime: PCLearningWorkbenchRuntime, host: str, port: int
) -> ThreadingHTTPServer:
    class BoundWorkbenchRequestHandler(WorkbenchRequestHandler):
        pass

    BoundWorkbenchRequestHandler.runtime = runtime
    return ThreadingHTTPServer((host, port), BoundWorkbenchRequestHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="知行智学 PC 本地工作台控制面")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "evidence" / "runtime" / "pc-workbench",
    )
    arguments = parser.parse_args()
    runtime = PCLearningWorkbenchRuntime(arguments.evidence_root)
    server = create_server(runtime, arguments.host, arguments.port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        runtime.close()


if __name__ == "__main__":
    main()
