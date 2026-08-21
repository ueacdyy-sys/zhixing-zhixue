"""One-command, fail-closed live RTSP tri-modal acceptance runner.

This is an acceptance harness, not a batch replayer.  It starts the three
resident lane workers first and refuses to open RTSP until every worker has
loaded its real runtime and written a readiness receipt.  During ingress it
records whether windows fuse *before* the live input ends.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import ctypes
import errno
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from ctypes import wintypes
from pathlib import Path
from typing import TextIO

try:  # Direct runner execution uses scripts/ as its import root.
    from realtime_runtime.contracts import AnalysisRouteLease, AnalysisRouteState
    from realtime_runtime.realtime_slo import (
        RealtimeServiceLevelPolicy,
        RealtimeStatus,
        evaluate_realtime_service_level,
        load_realtime_service_level_policy,
        measurement_from_e2e_artifacts,
    )
except ModuleNotFoundError:  # Package import from gateway/unit tests.
    from .realtime_runtime.contracts import AnalysisRouteLease, AnalysisRouteState
    from .realtime_runtime.realtime_slo import (
        RealtimeServiceLevelPolicy,
        RealtimeStatus,
        evaluate_realtime_service_level,
        load_realtime_service_level_policy,
        measurement_from_e2e_artifacts,
    )


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
MODEL_DIR = ROOT / "models" / "SmolVLM2-500M-Video-Instruct"
PY311 = ROOT / "env" / "py311" / "Scripts" / "python.exe"
VLM_PYTHON = ROOT / "env" / "fullvideo_runtime" / "Scripts" / "python.exe"


@dataclass(frozen=True)
class LaneProfile:
    lane: str
    python: Path


@dataclass(frozen=True)
class V2L0ProjectionConfig:
    """Route-bound inputs that allow workers to write L0 evidence facts only.

    The config is created solely from the signed/control-plane route lease
    supplied for this run.  Its presence does not enable scopes, L1 packages,
    interest, graph changes, or notifications.
    """

    semantic_ledger_path: Path
    route_ledger_path: Path
    learner_id: str
    capture_consent_id: str
    consent_generation: int
    route_lease_id: str
    route_epoch: int
    owner_endpoint_id: str


LANES = (
    LaneProfile("OCR", PY311),
    LaneProfile("ASR", PY311),
    LaneProfile("VLM", VLM_PYTHON),
)
TERMINAL_STATES = {"COMPLETE", "UNRESOLVED"}


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + environment.get("PYTHONPATH", "")
    return environment


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"preflight_missing_{label}:{path}")


def _prepare_ledger(path: Path) -> None:
    # The workers need a real SQLite file before they can warm and enter their
    # lease loops; the ingress process reuses exactly this ledger.
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.close()
    from realtime_runtime.ledger import SealedWindowLedger

    with SealedWindowLedger(path):
        pass


def build_worker_command(
    *,
    profile: LaneProfile,
    ledger: Path,
    capture_root: Path,
    artifact_root: Path,
    duration_seconds: float,
    projection: V2L0ProjectionConfig | None,
) -> list[str]:
    """Build a lane command without silently inventing a v2 analysis scope."""

    worker_id = f"{profile.lane.lower()}-e2e"
    command = [
        str(profile.python), "-m", "realtime_runtime.lane_worker",
        "--lane", profile.lane,
        "--ledger", str(ledger),
        "--capture-root", str(capture_root),
        "--artifact-root", str(artifact_root),
        "--model-dir", str(MODEL_DIR),
        "--worker-id", worker_id,
        # A production stream is allowed to be temporarily quiet without
        # silently losing the warmed worker.  Finite acceptance runs retain a
        # bounded post-ingress settle allowance.
        "--max-idle-seconds", str(0 if duration_seconds == 0 else int(duration_seconds + 180)),
    ]
    if projection is not None:
        command += [
            "--v2-semantic-ledger", str(projection.semantic_ledger_path),
            "--v2-learner-id", projection.learner_id,
            "--v2-capture-consent-id", projection.capture_consent_id,
            "--v2-consent-generation", str(projection.consent_generation),
            "--v2-route-ledger", str(projection.route_ledger_path),
            "--v2-route-lease-id", projection.route_lease_id,
            "--v2-route-epoch", str(projection.route_epoch),
            "--v2-owner-endpoint-id", projection.owner_endpoint_id,
        ]
    return command


def _spawn_worker(
    profile: LaneProfile,
    ledger: Path,
    capture_root: Path,
    artifact_root: Path,
    duration_seconds: float,
    projection: V2L0ProjectionConfig | None,
) -> subprocess.Popen[str]:
    worker_id = f"{profile.lane.lower()}-e2e"
    command = build_worker_command(
        profile=profile,
        ledger=ledger,
        capture_root=capture_root,
        artifact_root=artifact_root,
        duration_seconds=duration_seconds,
        projection=projection,
    )
    out = (capture_root / f"{worker_id}.out").open("w", encoding="utf-8", newline="\n")
    err = (capture_root / f"{worker_id}.err").open("w", encoding="utf-8", newline="\n")
    process = subprocess.Popen(command, cwd=SCRIPTS, env=_environment(), stdout=out, stderr=err, text=True)
    # Popen does not own these handles after launch on Windows; close them here
    # so the final report can read logs even if a worker fails immediately.
    out.close()
    err.close()
    return process


def _load_v2_l0_projection_config(
    route_lease_path: Path | None,
    *,
    output_dir: Path,
    capture_session_id: str,
) -> V2L0ProjectionConfig | None:
    """Extract worker authority from the same lease ingress will enforce.

    No lease means the retained legacy capture path remains read-only.  A
    malformed, inactive, or cross-session lease is rejected before any lane
    worker is started, rather than allowing an unauthorised L0 projection.
    """

    if route_lease_path is None:
        return None
    try:
        raw = json.loads(route_lease_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("analysis_route_lease_payload_invalid")
        def required_string(field: str) -> str:
            value = raw[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"analysis_route_lease_{field}_invalid")
            return value

        def required_integer(field: str) -> int:
            value = raw[field]
            if type(value) is not int:
                raise ValueError(f"analysis_route_lease_{field}_invalid")
            return value

        lease = AnalysisRouteLease(
            lease_id=required_string("lease_id"),
            learner_id=required_string("learner_id"),
            session_id=required_string("session_id"),
            capture_consent_id=required_string("capture_consent_id"),
            consent_generation=required_integer("consent_generation"),
            route_epoch=required_integer("route_epoch"),
            state=AnalysisRouteState(required_string("state")),
            owner_endpoint_id=required_string("owner_endpoint_id"),
            opened_receipt_hash=required_string("opened_receipt_hash"),
            student_confirmation_hash=required_string("student_confirmation_hash"),
            issued_elapsed_ns=required_integer("issued_elapsed_ns"),
            last_renewed_elapsed_ns=required_integer("last_renewed_elapsed_ns"),
            expires_elapsed_ns=required_integer("expires_elapsed_ns"),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("analysis_route_lease_unusable") from error
    if lease.session_id != capture_session_id:
        raise ValueError("analysis_route_lease_session_mismatch")
    if lease.state is not AnalysisRouteState.PC_LOCAL_ACTIVE or not lease.owner_endpoint_id:
        raise ValueError("analysis_route_lease_not_pc_local_active")
    _assert_v2_media_security_transport_available()
    return V2L0ProjectionConfig(
        semantic_ledger_path=output_dir / "semantic_l0.sqlite",
        route_ledger_path=output_dir / "analysis_route.sqlite",
        learner_id=lease.learner_id,
        capture_consent_id=lease.capture_consent_id,
        consent_generation=lease.consent_generation,
        route_lease_id=lease.lease_id,
        route_epoch=lease.route_epoch,
        owner_endpoint_id=lease.owner_endpoint_id,
    )


def _assert_v2_media_security_transport_available() -> None:
    """Fence v2 projections until the data plane meets the v2 media contract.

    The current handset-to-PC path is RTSP without mutual authentication,
    encryption, per-fragment MAC, or anti-replay.  A control-plane route lease
    cannot compensate for those missing data-plane guarantees.  Keeping this
    guard as an explicit function makes opening v2 L0 dependent on a future
    T051 implementation and its negative transport tests, rather than on a
    caller-supplied JSON flag.
    """

    raise ValueError("v2_media_security_transport_unavailable")


def _await_readiness(processes: dict[str, subprocess.Popen[str]], artifact_root: Path, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    pending = set(processes)
    while pending and time.monotonic() < deadline:
        failed = [lane for lane in pending if processes[lane].poll() is not None]
        if failed:
            raise RuntimeError(f"worker_failed_before_ready:{','.join(sorted(failed))}")
        pending = {lane for lane in pending if not (artifact_root / f"{lane.lower()}-e2e.ready.json").is_file()}
        time.sleep(0.1)
    if pending:
        raise RuntimeError(f"worker_ready_timeout:{','.join(sorted(pending))}")


def build_pipeline_command(
    *,
    source: str,
    capture_session_id: str,
    capture_generation: int,
    output_dir: Path,
    duration_seconds: float,
    fragments_per_window: int,
    window_hop_fragments: int,
    stop_signal_file: Path | None,
    analysis_route_lease_json: Path | None,
    transition_events: Path | None,
    audio_telemetry_journal: Path | None,
) -> list[str]:
    """Build the inner ingress command without changing the capture identity.

    The output directory is an implementation detail and can be timestamped or
    recreated.  The authenticated capture session ID is the only identity that
    may cross from the paired gateway into the evidence pipeline.
    """

    if not capture_session_id or type(capture_generation) is not int or capture_generation < 1:
        raise ValueError("capture_session_identity_invalid")
    command = [
        str(PY311), "-m", "realtime_runtime.pipeline", "--source", source,
        "--session-id", capture_session_id, "--capture-generation", str(capture_generation),
        "--output-dir", str(output_dir),
        "--fragment-seconds", "2", "--duration-seconds", str(duration_seconds),
        "--fragments-per-window", str(fragments_per_window),
        "--window-hop-fragments", str(window_hop_fragments),
    ]
    if stop_signal_file is not None:
        command += ["--stop-signal-file", _child_visible_path(stop_signal_file)]
    if analysis_route_lease_json is not None:
        command += ["--analysis-route-lease-json", _child_visible_path(analysis_route_lease_json)]
    if transition_events is not None:
        command += ["--transition-events", str(transition_events)]
    if audio_telemetry_journal is not None:
        command += ["--audio-telemetry-journal", _child_visible_path(audio_telemetry_journal)]
    return command


def _counts(ledger: Path) -> dict[str, int]:
    # A transaction context alone keeps the SQLite handle open on Windows.
    # The settlement loop polls repeatedly, so each snapshot must release its
    # handle before the next worker or cleanup action touches the ledger.
    with closing(sqlite3.connect(ledger)) as connection:
        total = connection.execute("select count(1) from semantic_windows").fetchone()[0]
        # An explicitly incomplete window is durable evidence of a gap, not a
        # candidate eligible for tri-modal fusion.  It must remain visible in
        # the final receipt, but it must not make the settlement loop wait for
        # an impossible fused_at_ns value forever.
        fusion_eligible = connection.execute(
            "select count(1) from semantic_windows where fusion_mode != 'EVIDENCE_INCOMPLETE'"
        ).fetchone()[0]
        incomplete = total - fusion_eligible
        fused = connection.execute("select count(1) from semantic_windows where fused_at_ns is not null").fetchone()[0]
        unresolved = connection.execute("select count(1) from jobs where state='UNRESOLVED'").fetchone()[0]
        queue_depth = connection.execute(
            "select count(1) from jobs where state in ('PENDING', 'LEASED', 'RETRY_WAIT')"
        ).fetchone()[0]
    return {
        "windows": total,
        "fusion_eligible_windows": fusion_eligible,
        "evidence_incomplete_windows": incomplete,
        "fused": fused,
        "unresolved_jobs": unresolved,
        "queue_depth": queue_depth,
    }


def _write_realtime_slo_report(
    *,
    output: Path,
    policy_path: Path | None,
    device_stream_attestation_path: Path | None,
    capture_session_id: str,
) -> dict[str, object]:
    """Persist a separate fail-closed capability report beside the old settlement receipt.

    The former acceptance summary is still useful to diagnose whether workers
    settled old semantic windows.  It is not a service-level approval, so this
    report is intentionally emitted even when no policy or phone proof exists.
    """
    policy: RealtimeServiceLevelPolicy | None = None
    measurement = None
    reasons: list[str] = []
    if policy_path is None:
        reasons.append("policy_missing")
    else:
        try:
            policy = load_realtime_service_level_policy(policy_path)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            reasons.append(f"policy_unusable:{error}")
    if device_stream_attestation_path is None:
        reasons.append("device_stream_attestation_missing")
    else:
        try:
            measurement = measurement_from_e2e_artifacts(
                ledger_path=output / "evidence_ledger.sqlite",
                progress_path=output / "online_progress.jsonl",
                device_stream_attestation_path=device_stream_attestation_path,
                expected_capture_session_id=capture_session_id,
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            reasons.append(f"measurement_unusable:{error}")
    decision = evaluate_realtime_service_level(policy, measurement) if measurement is not None else None
    if decision is not None:
        reasons.extend(item for item in decision.reasons if item not in reasons)
    status = decision.status.value if decision is not None else RealtimeStatus.NOT_REALTIME.value
    report: dict[str, object] = {
        "schema_version": "realtime-slo-report.v1",
        "generated_monotonic_ns": time.monotonic_ns(),
        "capture_session_id": capture_session_id,
        "status": status,
        "reasons": reasons,
        "policy": policy.to_dict() if policy is not None else None,
        "measurement": measurement.to_dict() if measurement is not None else None,
        "decision": decision.to_dict() if decision is not None else None,
    }
    (output / "realtime_slo_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def _settlement_outcome(state: dict[str, int]) -> str | None:
    """Return a terminal settlement result only after all lane jobs are terminal.

    A missing media interval can conservatively prevent later windows from
    reaching the contiguous tri-modal watermark.  Once no job is unresolved,
    waiting for those windows to fuse forever cannot recover evidence.  The
    caller applies a short no-progress grace period before accepting this
    failure so an idle lane worker still has time for its normal fusion pass.
    """
    if state["windows"] <= 0 or state["unresolved_jobs"] != 0:
        return None
    if state["fused"] == state["fusion_eligible_windows"]:
        return "OK"
    return "FAILED_UNFUSED_WINDOWS"


def _ingress_terminal_error(output_dir: Path) -> str | None:
    """Read the ingress receipt without treating an abrupt RTSP end as clean."""
    receipt = output_dir / "ingress_report.json"
    if not receipt.is_file():
        return "ingress_receipt_missing"
    try:
        value = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "ingress_receipt_unreadable"
    terminal_error = value.get("terminal_error")
    return str(terminal_error) if terminal_error else None


def _terminate(processes: list[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is not None:
            continue
        if os.name == "nt":
            # A lane can own ffmpeg/model runtime children.  Do not leave them
            # behind if this runner exits through an exceptional path.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        else:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _process_is_alive(pid: int) -> bool:
    """Return whether an OS process still exists without adding a runtime dependency.

    `os.kill(pid, 0)` is supported by Windows and POSIX.  Permission denial
    means the process exists but is owned by another security principal, which
    is still alive for ownership purposes.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        # Windows rejects `os.kill(pid, 0)` with ERROR_INVALID_PARAMETER even
        # when a process has simply exited, so POSIX-style probing is not a
        # reliable owner check here.  Query the process handle and its exit
        # code instead.
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            # Access denied means an extant process under another principal;
            # an invalid/nonexistent pid returns no usable handle.
            return ctypes.get_last_error() == 5
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as error:
        return error.errno not in {errno.ESRCH}
    return True


def _stop_when_supervisor_is_gone(supervisor_pid: int | None, stop_signal_file: Path | None) -> bool:
    """Write the normal stop contract when a forcibly killed gateway is gone.

    The runner must use the same stop path as an authorized user stop: ingress
    seals its current fragment and the already sealed OCR/ASR/VLM work drains.
    It must not keep consuming the RTSP source after its gateway owner died.
    """
    if supervisor_pid is None or _process_is_alive(supervisor_pid):
        return False
    if stop_signal_file is not None:
        stop_signal_file.parent.mkdir(parents=True, exist_ok=True)
        stop_signal_file.touch(exist_ok=True)
    return True


def _child_visible_path(path: Path) -> str:
    """Freeze a control-file location before crossing a process boundary.

    The realtime ingress runs with ``scripts/`` as its working directory,
    while this runner starts from the product root.  A relative stop-file path
    would therefore describe two different files and make forced gateway
    recovery unable to stop an active RTSP reader.
    """
    return str(path.expanduser().resolve())


def _acquire_capture_owner_lock(lock_file: Path | None) -> str | None:
    """Atomically claim one paired-phone capture owner across gateway restarts."""
    if lock_file is None:
        return None
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    payload = json.dumps({"pid": os.getpid(), "token": token}, separators=(",", ":"))
    for _ in range(3):
        try:
            descriptor = os.open(lock_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            try:
                existing = json.loads(lock_file.read_text(encoding="utf-8"))
                owner_pid = int(existing["pid"])
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                owner_pid = -1
            if _process_is_alive(owner_pid):
                raise RuntimeError("capture_owner_conflict")
            lock_file.unlink(missing_ok=True)
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
        return token
    raise RuntimeError("capture_owner_lock_race")


def _release_capture_owner_lock(lock_file: Path | None, token: str | None) -> None:
    if lock_file is None or token is None:
        return
    try:
        existing = json.loads(lock_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return
    if existing.get("token") == token and existing.get("pid") == os.getpid():
        lock_file.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument(
        "--session-id",
        required=True,
        help="Authenticated capture session ID supplied by the paired gateway; it must not be derived from a path.",
    )
    parser.add_argument(
        "--capture-generation",
        type=int,
        required=True,
        help="Current mobile capture-control generation; stale workers must be rejected before ledger ingress.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=0.0,
        help="0 keeps the production stream running; a positive value is an acceptance-test observation horizon.",
    )
    parser.add_argument("--clock-host", default="10.83.246.55")
    parser.add_argument(
        "--enable-clock-sampling",
        action="store_true",
        help="Only for a finite, explicitly requested clock-alignment acceptance run. Production capture keeps one RTSP ingress connection.",
    )
    parser.add_argument("--stop-signal-file", type=Path, default=None)
    parser.add_argument(
        "--audio-telemetry-journal",
        type=Path,
        default=None,
        help="Gateway-written L0 audio telemetry journal for this capture session; it never grants v2/L1 admission.",
    )
    parser.add_argument("--capture-owner-lock-file", type=Path, default=None)
    parser.add_argument(
        "--analysis-route-lease-json",
        type=Path,
        default=None,
        help="Explicit v2 PC route lease forwarded to ingress; omit only for the legacy read-only validation path.",
    )
    parser.add_argument(
        "--realtime-slo-policy-json",
        type=Path,
        default=None,
        help="Approved exact device-model SLO policy. Without it the report remains NOT_REALTIME.",
    )
    parser.add_argument(
        "--device-stream-attestation-json",
        type=Path,
        default=None,
        help="Final phone capture-session proof bound to this run; a CLI source URL cannot replace it.",
    )
    parser.add_argument(
        "--require-realtime-slo",
        action="store_true",
        help="Return failure unless realtime_slo_report.json evaluates as REALTIME after settlement.",
    )
    parser.add_argument(
        "--supervisor-pid",
        type=int,
        default=None,
        help="Owning local gateway PID; a missing owner triggers the normal tail-settlement stop contract.",
    )
    parser.add_argument(
        "--fragments-per-window",
        type=int,
        default=2,
        help="Two complete ~2 s fragments provide the online 4 s semantic window; never a frame-only shortcut.",
    )
    parser.add_argument(
        "--window-hop-fragments",
        type=int,
        default=2,
        help="Keep online windows non-overlapping so sustained VLM throughput remains measurable.",
    )
    parser.add_argument("--adb", default=None, help="Optional authorized adb.exe for passive visit-transition facts.")
    parser.add_argument("--adb-serial", default=None)
    parser.add_argument("--touch-device", default="/dev/input/event1")
    parser.add_argument(
        "--settle-timeout-seconds",
        type=float,
        default=0.0,
        help="0 drains every sealed window before exit; positive values are acceptance-test limits only.",
    )
    args = parser.parse_args()
    if args.duration_seconds < 0:
        raise SystemExit("duration must be non-negative")
    if args.enable_clock_sampling and args.duration_seconds <= 0:
        raise SystemExit("clock_sampling_requires_finite_duration")
    if args.settle_timeout_seconds < 0:
        raise SystemExit("settle_timeout_seconds_must_be_non_negative")
    if args.fragments_per_window < 1 or args.window_hop_fragments < 1:
        raise SystemExit("window_fragment_counts_must_be_positive")
    if args.supervisor_pid is not None and args.stop_signal_file is None:
        raise SystemExit("supervisor_pid_requires_stop_signal_file")
    if args.analysis_route_lease_json is not None and not args.analysis_route_lease_json.is_file():
        raise SystemExit("analysis_route_lease_json_missing")
    for profile in LANES:
        _require_file(profile.python, f"python_{profile.lane.lower()}")
    _require_file(MODEL_DIR / "config.json", "vlm_config")
    _require_file(MODEL_DIR / "model.safetensors", "vlm_weights")

    owner_token = _acquire_capture_owner_lock(args.capture_owner_lock_file)
    workers: dict[str, subprocess.Popen[str]] = {}
    sampler: subprocess.Popen[str] | None = None
    touch_monitor: subprocess.Popen[str] | None = None
    ingress: subprocess.Popen[str] | None = None
    progress_file: TextIO | None = None
    try:
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=False)
        ledger = output / "evidence_ledger.sqlite"
        artifacts = output / "artifacts"
        v2_l0_projection = _load_v2_l0_projection_config(
            args.analysis_route_lease_json,
            output_dir=output,
            capture_session_id=args.session_id,
        )
        _prepare_ledger(ledger)
        # Spawn sequentially under the same finally block.  A partial runtime
        # startup must not orphan the lanes that did launch successfully.
        for profile in LANES:
            workers[profile.lane] = _spawn_worker(
                profile,
                ledger,
                output,
                artifacts,
                args.duration_seconds,
                v2_l0_projection,
            )
        _await_readiness(workers, artifacts, timeout_seconds=120.0)
        if args.enable_clock_sampling:
            # Clock evidence is an acceptance-only side connection.  Do not
            # repeatedly attach it to the Android RTSP server during the
            # product stream: ingress must remain the one long-lived client.
            clock_duration = args.duration_seconds + 8
            sampler = subprocess.Popen(
                [str(PY311), str(SCRIPTS / "rtsp_clock_sampler.py"), "--host", args.clock_host,
                 "--duration-seconds", str(clock_duration), "--interval-seconds", "0.5",
                 "--output", str(output / "rtsp_clock_samples.jsonl")],
                cwd=ROOT, env=_environment(), text=True,
                stdout=(output / "clock_sampler.out").open("w", encoding="utf-8"),
                stderr=(output / "clock_sampler.err").open("w", encoding="utf-8"),
            )
        transition_events: Path | None = None
        if bool(args.adb) != bool(args.adb_serial):
            raise RuntimeError("adb_and_serial_must_be_provided_together")
        if args.adb and args.adb_serial:
            transition_events = output / "transition_events.jsonl"
            touch_monitor = subprocess.Popen(
                [str(PY311), str(SCRIPTS / "touch_transition_monitor.py"), "--adb", args.adb,
                 "--serial", args.adb_serial, "--device", args.touch_device,
                 "--output", str(transition_events)],
                cwd=ROOT, env=_environment(), text=True,
                stdout=(output / "touch_monitor.out").open("w", encoding="utf-8"),
                stderr=(output / "touch_monitor.err").open("w", encoding="utf-8"),
            )
        ingress_command = build_pipeline_command(
            source=args.source,
            capture_session_id=args.session_id,
            capture_generation=args.capture_generation,
            output_dir=output,
            duration_seconds=args.duration_seconds,
            fragments_per_window=args.fragments_per_window,
            window_hop_fragments=args.window_hop_fragments,
            stop_signal_file=args.stop_signal_file,
            analysis_route_lease_json=args.analysis_route_lease_json,
            transition_events=transition_events,
            audio_telemetry_journal=args.audio_telemetry_journal,
        )
        ingress = subprocess.Popen(
            ingress_command,
            cwd=SCRIPTS, env=_environment(), text=True,
            stdout=(output / "ingress.out").open("w", encoding="utf-8"),
            stderr=(output / "ingress.err").open("w", encoding="utf-8"),
        )
        progress_file = (output / "online_progress.jsonl").open("w", encoding="utf-8", newline="\n")
        while ingress.poll() is None:
            _stop_when_supervisor_is_gone(args.supervisor_pid, args.stop_signal_file)
            event = {"pc_monotonic_ns": time.monotonic_ns(), "ingress_running": True, **_counts(ledger)}
            progress_file.write(json.dumps(event, separators=(",", ":")) + "\n")
            progress_file.flush()
            dead = [lane for lane, process in workers.items() if process.poll() is not None]
            if dead:
                raise RuntimeError(f"worker_died_during_ingress:{','.join(sorted(dead))}")
            time.sleep(0.5)
        ingress_exit_ns = time.monotonic_ns()
        if ingress.returncode != 0:
            raise RuntimeError(f"ingress_failed_exit_{ingress.returncode}")

        # A received, sealed fragment is durable evidence.  Do not silently
        # discard its queued OCR/ASR/VLM work after an arbitrary 90 seconds.
        # Production therefore drains to completion; bounded settlement is
        # available only as an explicitly requested acceptance-test limit.
        settle_deadline = time.monotonic() + args.settle_timeout_seconds if args.settle_timeout_seconds else None
        previous_settlement_state: dict[str, int] | None = None
        last_settlement_change_at = time.monotonic()
        terminal_outcome: str | None = None
        while True:
            state = _counts(ledger)
            progress_file.write(json.dumps({"pc_monotonic_ns": time.monotonic_ns(), "ingress_running": False, **state}, separators=(",", ":")) + "\n")
            progress_file.flush()
            if state != previous_settlement_state:
                previous_settlement_state = state
                last_settlement_change_at = time.monotonic()
            terminal_outcome = _settlement_outcome(state)
            if terminal_outcome == "OK":
                break
            if terminal_outcome == "FAILED_UNFUSED_WINDOWS" and time.monotonic() - last_settlement_change_at >= 5.0:
                break
            dead = [lane for lane, process in workers.items() if process.poll() is not None]
            if dead:
                raise RuntimeError(f"worker_died_during_settlement:{','.join(sorted(dead))}")
            if settle_deadline is not None and time.monotonic() >= settle_deadline:
                raise RuntimeError("acceptance_settlement_timeout")
            time.sleep(0.5)
        final = _counts(ledger)
        ingress_terminal_error = _ingress_terminal_error(output)
        with sqlite3.connect(ledger) as connection:
            online_fused = connection.execute("select count(1) from semantic_windows where fused_at_ns is not null and fused_at_ns < ?", (ingress_exit_ns,)).fetchone()[0]
        status = terminal_outcome or "FAILED"
        if status == "OK" and ingress_terminal_error:
            status = "DEGRADED_TRANSPORT"
        report = {"status": status,
                  "ingress_exit_monotonic_ns": ingress_exit_ns, "online_fused_windows": online_fused, **final}
        report["ingress_terminal_error"] = ingress_terminal_error
        progress_file.flush()
        slo_report = _write_realtime_slo_report(
            output=output,
            policy_path=args.realtime_slo_policy_json,
            device_stream_attestation_path=args.device_stream_attestation_json,
            capture_session_id=args.session_id,
        )
        report["realtime_service_level_status"] = slo_report["status"]
        report["realtime_slo_report"] = "realtime_slo_report.json"
        (output / "acceptance_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
        baseline_ok = report["status"] in {"OK", "DEGRADED_TRANSPORT"} and online_fused > 0
        slo_ok = slo_report["status"] == RealtimeStatus.REALTIME.value
        return 0 if baseline_ok and (not args.require_realtime_slo or slo_ok) else 2
    finally:
        if progress_file is not None:
            progress_file.close()
        _terminate(list(workers.values()) + [item for item in (sampler, touch_monitor, ingress) if item is not None])
        _release_capture_owner_lock(args.capture_owner_lock_file, owner_token)


if __name__ == "__main__":
    raise SystemExit(main())
