"""PC 工作台的回环本机 HTTP 控制面。"""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from zhixingzhixue_hub.phone.pc_result_outbox import (
    MobileResultOutbox,
    MobileResultOutboxAuthenticationError,
    MobileResultOutboxError,
)

from zhixingzhixue_hub.pc.workbench_runtime import (
    PCLearningWorkbenchRuntime,
    WorkbenchRuntimeError,
)


class WorkbenchRequestHandler(BaseHTTPRequestHandler):
    runtime: PCLearningWorkbenchRuntime
    mobile_outbox: MobileResultOutbox

    def do_GET(self) -> None:  # noqa: N802
        request = urlsplit(self.path)
        if request.path == "/api/dashboard":
            self._write_json(HTTPStatus.OK, self.runtime.dashboard())
            return
        if request.path == "/api/mobile-outbox/messages":
            try:
                device_id = self._query_text(request.query, "device_id")
                messages = self.mobile_outbox.pull(
                    device_id=device_id,
                    access_token=self._bearer_token(),
                    limit=self._query_limit(request.query),
                )
            except MobileResultOutboxAuthenticationError as error:
                self._write_error(HTTPStatus.UNAUTHORIZED, "MOBILE_DEVICE_ACCESS_DENIED", str(error))
                return
            except MobileResultOutboxError as error:
                self._write_error(HTTPStatus.UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", str(error))
                return
            self._write_json(HTTPStatus.OK, {"messages": messages})
            return
        self._write_error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "未找到本机工作台接口。")

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._read_json()
            response = self._dispatch(payload)
        except MobileResultOutboxAuthenticationError as error:
            self._write_error(HTTPStatus.UNAUTHORIZED, "MOBILE_DEVICE_ACCESS_DENIED", str(error))
            return
        except MobileResultOutboxError as error:
            self._write_error(HTTPStatus.UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", str(error))
            return
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
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
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
        if self.path == "/api/mobile-outbox/pairing-tokens":
            self._require_loopback_client()
            ttl_seconds = payload.get("ttl_seconds", 300)
            if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
                raise ValueError("ttl_seconds_must_be_an_integer")
            return self.mobile_outbox.issue_pairing_token(ttl_seconds=ttl_seconds)
        if self.path == "/api/mobile-outbox/devices/pair":
            return self.mobile_outbox.pair_device(
                device_id=str(payload.get("device_id", "")),
                pairing_token=str(payload.get("pairing_token", "")),
            )
        if self.path == "/api/mobile-outbox/analysis-results":
            self._require_loopback_client()
            analysis_result = payload.get("analysis_result")
            if not isinstance(analysis_result, dict):
                raise ValueError("analysis_result_must_be_an_object")
            return self.mobile_outbox.enqueue_analysis_result(
                device_id=str(payload.get("device_id", "")),
                analysis_result=analysis_result,
                idempotency_key=str(payload.get("idempotency_key", "")),
            )
        if self.path == "/api/mobile-outbox/messages/ack":
            return self.mobile_outbox.acknowledge(
                device_id=str(payload.get("device_id", "")),
                access_token=self._bearer_token(),
                message_id=str(payload.get("message_id", "")),
            )
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

    def _bearer_token(self) -> str:
        value = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not value.startswith(prefix) or not value[len(prefix) :].strip():
            raise MobileResultOutboxAuthenticationError("mobile_device_access_denied")
        return value[len(prefix) :].strip()

    @staticmethod
    def _query_text(query: str, field: str) -> str:
        values = parse_qs(query).get(field, [])
        if len(values) != 1 or not values[0].strip():
            raise MobileResultOutboxError(f"{field}_required")
        return values[0].strip()

    @staticmethod
    def _query_limit(query: str) -> int:
        values = parse_qs(query).get("limit", [])
        if not values:
            return 20
        if len(values) != 1:
            raise MobileResultOutboxError("pull_limit_must_be_between_1_and_100")
        try:
            return int(values[0])
        except ValueError as error:
            raise MobileResultOutboxError("pull_limit_must_be_between_1_and_100") from error

    def _require_loopback_client(self) -> None:
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            raise MobileResultOutboxAuthenticationError("loopback_control_endpoint_required")


def create_server(
    runtime: PCLearningWorkbenchRuntime,
    host: str,
    port: int,
    mobile_outbox: MobileResultOutbox,
) -> ThreadingHTTPServer:
    class BoundWorkbenchRequestHandler(WorkbenchRequestHandler):
        pass

    BoundWorkbenchRequestHandler.runtime = runtime
    BoundWorkbenchRequestHandler.mobile_outbox = mobile_outbox
    return ThreadingHTTPServer((host, port), BoundWorkbenchRequestHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="知行智学 PC 本地工作台控制面")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument(
        "--allow-lan-mobile",
        action="store_true",
        help="允许非回环地址绑定，供已配对的局域网手机轮询结果；默认仅绑定 127.0.0.1。",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "evidence" / "runtime" / "pc-workbench",
    )
    arguments = parser.parse_args()
    if arguments.host not in {"127.0.0.1", "localhost", "::1"} and not arguments.allow_lan_mobile:
        parser.error("非回环绑定需要显式传入 --allow-lan-mobile")
    runtime = PCLearningWorkbenchRuntime(arguments.evidence_root)
    mobile_outbox = MobileResultOutbox(arguments.evidence_root / "mobile-result-outbox")
    server = create_server(runtime, arguments.host, arguments.port, mobile_outbox)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        runtime.close()
        mobile_outbox.close()


if __name__ == "__main__":
    main()
