"""Composition root for one RTSP reader and the durable evidence ledger."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from realtime_fragment_worker import LiveIngressConfig, run as run_ingress

from .contracts import SourceContext
from .ledger import SealedWindowLedger
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
    ) -> None:
        self._output_dir = output_dir.resolve()
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

    def on_fragment_committed(self, event: dict[str, Any]) -> None:
        fragment = sealed_fragment_from_worker_event(
            event, source_context=self._source_context, media_root=self._output_dir
        )
        content_transition = self._transitions.consume_before(fragment.pc_sealed_ns)
        result = self._ingestor.ingest(
            fragment,
            now_ns=time.monotonic_ns(),
            content_transition=content_transition,
        )
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
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--fragment-seconds", type=float, default=2.0)
    parser.add_argument("--duration-seconds", type=float, default=0.0)
    parser.add_argument("--fragments-per-window", type=int, default=3)
    parser.add_argument("--window-hop-fragments", type=int, default=3)
    parser.add_argument("--transition-events", default=None)
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    with SealedWindowLedger(output_dir / "evidence_ledger.sqlite") as ledger:
        pipeline = RealtimePipeline(
            ledger=ledger,
            output_dir=output_dir,
            session_id=args.session_id,
            source_context=SourceContext.PHONE_DAILY,
            fragments_per_window=args.fragments_per_window,
            window_hop_fragments=args.window_hop_fragments,
            require_full_window=True,
            transition_events=Path(args.transition_events) if args.transition_events else None,
        )
        report = run_ingress(
            LiveIngressConfig(
                source=args.source,
                session_id=args.session_id,
                output_dir=output_dir,
                fragment_seconds=args.fragment_seconds,
                duration_seconds=args.duration_seconds,
            ),
            on_fragment_committed=pipeline.on_fragment_committed,
        )
        end_pts_ns = max((int(item["end_pts_ns"]) for item in report["fragments"]), default=0)
        if end_pts_ns:
            pipeline.finalize(end_pts_ns=end_pts_ns)
    print(json.dumps({"status": "ok", "fragment_count": report["fragment_count"]}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
