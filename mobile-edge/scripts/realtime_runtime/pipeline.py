"""Composition root for one RTSP reader and the durable evidence ledger."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import time
from pathlib import Path
from typing import Any, Callable

from realtime_fragment_worker import IngressTransportInterrupted, LiveIngressConfig, run as run_ingress

from .analysis_route import AnalysisRouteLedger
from .contracts import AnalysisRouteLease, AnalysisRouteState, ContractError, SourceContext
from .ledger import SealedWindowLedger
from .l0_audio_telemetry import load_fragment_audio_telemetry
from .orchestrator import RealtimeIngestor
from .transitions import JsonlTransitionFeed
from .worker_adapter import sealed_fragment_from_worker_event


class RealtimePipeline:
    """Wires outer RTSP ingress inward; semantic lanes consume resulting ledger jobs."""

    def __init__(
        self,
        *,
        ledger: SealedWindowLedger,
        output_dir: Path,
        session_id: str,
        source_context: SourceContext,
        fragments_per_window: int = 3,
        window_hop_fragments: int = 1,
        require_full_window: bool = False,
        transition_events: Path | None = None,
        route_authorizer: Callable[[], None] | None = None,
        expected_capture_generation: int | None = None,
        audio_telemetry_journal: Path | None = None,
    ) -> None:
        self._output_dir = output_dir.resolve()
        self._ledger = ledger
        self._ingestor = RealtimeIngestor(
            ledger,
            session_id=session_id,
            source_context=source_context,
            fragments_per_window=fragments_per_window,
            window_hop_fragments=window_hop_fragments,
            require_full_window=require_full_window,
        )
        self._runtime_events = self._output_dir / "runtime_events.jsonl"
        self._source_context = source_context
        self._transitions = JsonlTransitionFeed(transition_events)
        self._route_authorizer = route_authorizer
        if expected_capture_generation is not None and expected_capture_generation < 1:
            raise ValueError("capture_generation_invalid")
        self._expected_capture_generation = expected_capture_generation
        self._audio_telemetry_journal = audio_telemetry_journal

    def on_fragment_committed(self, event: dict[str, Any]) -> None:
        # A route lease authorizes every new PC ingress, not just process
        # startup. Expiry/epoch loss therefore fences a stale worker before it
        # can create a window for another analysis owner.
        if self._route_authorizer is not None:
            self._route_authorizer()
        if self._expected_capture_generation is not None:
            if event.get("capture_generation") != self._expected_capture_generation:
                raise ContractError("worker_capture_generation_mismatch")
        fragment = sealed_fragment_from_worker_event(
            event, source_context=self._source_context, media_root=self._output_dir
        )
        references = ()
        if self._expected_capture_generation is not None:
            references = load_fragment_audio_telemetry(
                self._audio_telemetry_journal,
                capture_session_id=fragment.session_id,
                capture_generation=self._expected_capture_generation,
                start_pts_ns=fragment.start_pts_ns,
                end_pts_ns=fragment.end_pts_ns,
            )
        content_transition = self._transitions.consume_before(fragment.pc_sealed_ns)
        result = self._ingestor.ingest(
            fragment,
            now_ns=time.monotonic_ns(),
            content_transition=content_transition,
        )
        if references:
            self._ledger.append_l0_audio_telemetry_refs(fragment.fragment_id, references)
        if result.planned_window is None:
            return
        self._runtime_events.parent.mkdir(parents=True, exist_ok=True)
        with self._runtime_events.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {
                        "event_type": "SemanticWindowScheduled",
                        "fragment_id": fragment.fragment_id,
                        "window_id": result.planned_window.window.window_id,
                        "visit_id": result.planned_window.window.visit_id,
                        "fusion_mode": result.planned_window.fusion_mode.value,
                        "required_lanes": [lane.value for lane in result.planned_window.window.required_lanes],
                        "content_transition_before_fragment": content_transition,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def finalize(self, *, end_pts_ns: int) -> None:
        planned = self._ingestor.flush_tail(now_ns=time.monotonic_ns())
        self._ingestor.close_session(end_pts_ns=end_pts_ns)
        if planned is None:
            return
        with self._runtime_events.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {
                        "event_type": "SemanticWindowScheduled",
                        "window_id": planned.window.window_id,
                        "visit_id": planned.window.visit_id,
                        "fusion_mode": planned.fusion_mode.value,
                        "required_lanes": [lane.value for lane in planned.window.required_lanes],
                        "reason": "SESSION_TAIL_FLUSH",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--capture-generation", type=int, required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--fragment-seconds", type=float, default=2.0)
    parser.add_argument("--duration-seconds", type=float, default=0.0)
    parser.add_argument("--fragments-per-window", type=int, default=3)
    parser.add_argument("--window-hop-fragments", type=int, default=3)
    parser.add_argument("--transition-events", default=None)
    parser.add_argument("--audio-telemetry-journal", type=Path, default=None)
    parser.add_argument("--stop-signal-file", type=Path, default=None)
    parser.add_argument(
        "--analysis-route-lease-json",
        type=Path,
        default=None,
        help="Explicit v2 PC route lease. Without it this runner remains legacy L0-only and cannot claim v2 ingress.",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    with ExitStack() as resources:
        ledger = resources.enter_context(SealedWindowLedger(output_dir / "evidence_ledger.sqlite"))
        route_authorizer: Callable[[], None] | None = None
        if args.analysis_route_lease_json is not None:
            raw = json.loads(args.analysis_route_lease_json.read_text(encoding="utf-8"))
            lease = AnalysisRouteLease(
                lease_id=str(raw["lease_id"]), learner_id=str(raw["learner_id"]), session_id=str(raw["session_id"]),
                capture_consent_id=str(raw["capture_consent_id"]), consent_generation=int(raw["consent_generation"]),
                route_epoch=int(raw["route_epoch"]), state=AnalysisRouteState(str(raw["state"])),
                owner_endpoint_id=raw.get("owner_endpoint_id"), opened_receipt_hash=str(raw["opened_receipt_hash"]),
                student_confirmation_hash=str(raw["student_confirmation_hash"]), issued_elapsed_ns=int(raw["issued_elapsed_ns"]),
                last_renewed_elapsed_ns=int(raw["last_renewed_elapsed_ns"]), expires_elapsed_ns=int(raw["expires_elapsed_ns"]),
            )
            routes = resources.enter_context(AnalysisRouteLedger(output_dir / "analysis_route.sqlite"))
            routes.open(lease, now_elapsed_ns=time.monotonic_ns())
            if lease.state is not AnalysisRouteState.PC_LOCAL_ACTIVE or not lease.owner_endpoint_id:
                raise ValueError("pc_v2_ingress_requires_active_pc_route")

            def authorize_route() -> None:
                routes.assert_pc_ingress_authorized(
                    lease_id=lease.lease_id, learner_id=lease.learner_id, session_id=lease.session_id,
                    capture_consent_id=lease.capture_consent_id, consent_generation=lease.consent_generation,
                    route_epoch=lease.route_epoch, endpoint_id=lease.owner_endpoint_id, now_elapsed_ns=time.monotonic_ns(),
                )

            route_authorizer = authorize_route
        pipeline = RealtimePipeline(
            ledger=ledger,
            output_dir=output_dir,
            session_id=args.session_id,
            source_context=SourceContext.PHONE_DAILY,
            fragments_per_window=args.fragments_per_window,
            window_hop_fragments=args.window_hop_fragments,
            require_full_window=True,
            transition_events=Path(args.transition_events) if args.transition_events else None,
            route_authorizer=route_authorizer,
            expected_capture_generation=args.capture_generation,
            audio_telemetry_journal=args.audio_telemetry_journal,
        )
        try:
            report = run_ingress(
                LiveIngressConfig(
                    source=args.source,
                    session_id=args.session_id,
                    output_dir=output_dir,
                    capture_generation=args.capture_generation,
                    fragment_seconds=args.fragment_seconds,
                    duration_seconds=args.duration_seconds,
                    stop_signal_file=args.stop_signal_file,
                ),
                on_fragment_committed=pipeline.on_fragment_committed,
            )
        except IngressTransportInterrupted as interrupted:
            # The ingress adapter has already sealed its accepted fragments
            # and persisted the transport failure.  Finish the inner policy
            # rather than abandoning valid windows because the next reconnect
            # could not be opened.
            report = interrupted.report
        end_pts_ns = max((int(item["end_pts_ns"]) for item in report["fragments"]), default=0)
        if end_pts_ns:
            pipeline.finalize(end_pts_ns=end_pts_ns)
        # This receipt is the explicit hand-off from the outer RTSP adapter to
        # the runner.  A non-empty terminal_error is not silently converted
        # into a clean capture: the runner may still settle and return the
        # intact earlier evidence, but must report the degraded transport.
        (output_dir / "ingress_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "status": "degraded_transport" if report["terminal_error"] else "ok",
                "fragment_count": report["fragment_count"],
                "terminal_error": report["terminal_error"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
