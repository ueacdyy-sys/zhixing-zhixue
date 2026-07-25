"""One-command, fail-closed live RTSP tri-modal acceptance runner.

This is an acceptance harness, not a batch replayer.  It starts the three
resident lane workers first and refuses to open RTSP until every worker has
loaded its real runtime and written a readiness receipt.  During ingress it
records whether windows fuse *before* the live input ends.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
MODEL_DIR = ROOT / "models" / "SmolVLM2-500M-Video-Instruct"
PY311 = ROOT / "env" / "py311" / "Scripts" / "python.exe"
VLM_PYTHON = ROOT / "env" / "fullvideo_runtime" / "Scripts" / "python.exe"


@dataclass(frozen=True)
class LaneProfile:
    lane: str
    python: Path


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


def _spawn_worker(profile: LaneProfile, ledger: Path, capture_root: Path, artifact_root: Path, duration_seconds: float) -> subprocess.Popen[str]:
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
    out = (capture_root / f"{worker_id}.out").open("w", encoding="utf-8", newline="\n")
    err = (capture_root / f"{worker_id}.err").open("w", encoding="utf-8", newline="\n")
    process = subprocess.Popen(command, cwd=SCRIPTS, env=_environment(), stdout=out, stderr=err, text=True)
    # Popen does not own these handles after launch on Windows; close them here
    # so the final report can read logs even if a worker fails immediately.
    out.close()
    err.close()
    return process


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


def _counts(ledger: Path) -> dict[str, int]:
    with sqlite3.connect(ledger) as connection:
        total = connection.execute("select count(1) from semantic_windows").fetchone()[0]
        fused = connection.execute("select count(1) from semantic_windows where fused_at_ns is not null").fetchone()[0]
        unresolved = connection.execute("select count(1) from jobs where state='UNRESOLVED'").fetchone()[0]
    return {"windows": total, "fused": fused, "unresolved_jobs": unresolved}


def _terminate(processes: list[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=0.0,
        help="0 keeps the production stream running; a positive value is an acceptance-test observation horizon.",
    )
    parser.add_argument("--clock-host", default="10.83.246.55")
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
    parser.add_argument("--enable-candidate-notifications", action="store_true")
    parser.add_argument("--pc-outbox-gateway", default=None, help="Paired-PC local hub URL for formal candidate delivery.")
    parser.add_argument("--pc-outbox-device-id", default=None)
    args = parser.parse_args()
    if args.duration_seconds < 0:
        raise SystemExit("duration must be non-negative")
    if args.fragments_per_window < 1 or args.window_hop_fragments < 1:
        raise SystemExit("window_fragment_counts_must_be_positive")
    if bool(args.pc_outbox_gateway) != bool(args.pc_outbox_device_id):
        raise SystemExit("pc_outbox_gateway_and_device_id_must_be_provided_together")

    for profile in LANES:
        _require_file(profile.python, f"python_{profile.lane.lower()}")
    _require_file(MODEL_DIR / "config.json", "vlm_config")
    _require_file(MODEL_DIR / "model.safetensors", "vlm_weights")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    ledger = output / "evidence_ledger.sqlite"
    artifacts = output / "artifacts"
    _prepare_ledger(ledger)
    workers = {profile.lane: _spawn_worker(profile, ledger, output, artifacts, args.duration_seconds) for profile in LANES}
    sampler: subprocess.Popen[str] | None = None
    touch_monitor: subprocess.Popen[str] | None = None
    notice_dispatcher: subprocess.Popen[str] | None = None
    outbox_publisher: subprocess.Popen[str] | None = None
    ingress: subprocess.Popen[str] | None = None
    progress_file: TextIO | None = None
    try:
        _await_readiness(workers, artifacts, timeout_seconds=120.0)
        clock_duration = 0.0 if args.duration_seconds == 0 else args.duration_seconds + 8
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
        if args.enable_candidate_notifications:
            if not args.adb or not args.adb_serial:
                raise RuntimeError("candidate_notifications_require_authorized_adb")
            notice_dispatcher = subprocess.Popen(
                [str(PY311), str(SCRIPTS / "candidate_notice_dispatcher.py"), "--ledger", str(ledger),
                 "--artifact-root", str(artifacts), "--adb", args.adb, "--serial", args.adb_serial,
                 "--output", str(output / "candidate_notice_delivery.jsonl")],
                cwd=ROOT, env=_environment(), text=True,
                stdout=(output / "notice_dispatcher.out").open("w", encoding="utf-8"),
                stderr=(output / "notice_dispatcher.err").open("w", encoding="utf-8"),
            )
        if args.pc_outbox_gateway:
            outbox_publisher = subprocess.Popen(
                [str(PY311), str(SCRIPTS / "pc_outbox_candidate_publisher.py"), "--ledger", str(ledger),
                 "--artifact-root", str(artifacts), "--gateway", args.pc_outbox_gateway,
                 "--device-id", args.pc_outbox_device_id, "--output", str(output / "candidate_outbox_delivery.jsonl")],
                cwd=ROOT, env=_environment(), text=True,
                stdout=(output / "outbox_publisher.out").open("w", encoding="utf-8"),
                stderr=(output / "outbox_publisher.err").open("w", encoding="utf-8"),
            )
        ingress_command = [str(PY311), "-m", "realtime_runtime.pipeline", "--source", args.source,
             "--session-id", output.name, "--output-dir", str(output), "--fragment-seconds", "2",
             "--duration-seconds", str(args.duration_seconds), "--fragments-per-window", str(args.fragments_per_window),
             "--window-hop-fragments", str(args.window_hop_fragments)]
        if transition_events is not None:
            ingress_command += ["--transition-events", str(transition_events)]
        ingress = subprocess.Popen(
            ingress_command,
            cwd=SCRIPTS, env=_environment(), text=True,
            stdout=(output / "ingress.out").open("w", encoding="utf-8"),
            stderr=(output / "ingress.err").open("w", encoding="utf-8"),
        )
        progress_file = (output / "online_progress.jsonl").open("w", encoding="utf-8", newline="\n")
        while ingress.poll() is None:
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

        settle_deadline = time.monotonic() + 90.0
        while time.monotonic() < settle_deadline:
            state = _counts(ledger)
            progress_file.write(json.dumps({"pc_monotonic_ns": time.monotonic_ns(), "ingress_running": False, **state}, separators=(",", ":")) + "\n")
            progress_file.flush()
            if state["windows"] > 0 and state["fused"] == state["windows"] and state["unresolved_jobs"] == 0:
                break
            time.sleep(0.5)
        final = _counts(ledger)
        with sqlite3.connect(ledger) as connection:
            online_fused = connection.execute("select count(1) from semantic_windows where fused_at_ns is not null and fused_at_ns < ?", (ingress_exit_ns,)).fetchone()[0]
        report = {"status": "OK" if final["windows"] and final["fused"] == final["windows"] and final["unresolved_jobs"] == 0 else "FAILED",
                  "ingress_exit_monotonic_ns": ingress_exit_ns, "online_fused_windows": online_fused, **final}
        (output / "acceptance_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if report["status"] == "OK" and online_fused > 0 else 2
    finally:
        if progress_file is not None:
            progress_file.close()
        _terminate(list(workers.values()) + [item for item in (sampler, touch_monitor, notice_dispatcher, outbox_publisher, ingress) if item is not None])


if __name__ == "__main__":
    raise SystemExit(main())
