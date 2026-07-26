"""Summarise real VLM diagnostic observations without claiming an ablation."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

from .dataset import load_manifest


def quantile(values: list[float], level: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * level
    low, high = int(position), min(len(values) - 1, int(position) + 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    durations_ms: list[float] = []
    quality = Counter()
    for record in load_manifest(args.dataset):
        quality[str(record.get("manual_diagnostic", {}).get("vlm_quality", "unlabelled"))] += 1
        vlm = json.loads((args.dataset / record["evidence"]["vlm"]).read_text(encoding="utf-8"))
        start, end = vlm.get("started_monotonic_ns"), vlm.get("completed_monotonic_ns")
        if isinstance(start, int) and isinstance(end, int) and end >= start:
            durations_ms.append((end - start) / 1_000_000)
    report = {
        "status": "DIAGNOSTIC_ONLY_NOT_ABLATION",
        "records": sum(quality.values()),
        "source_video_groups": len({record["source_video_group"] for record in load_manifest(args.dataset)}),
        "vlm_quality_labels": dict(sorted(quality.items())),
        "vlm_duration_ms": {"p50": quantile(durations_ms, 0.50), "p95": quantile(durations_ms, 0.95), "max": max(durations_ms) if durations_ms else None},
        "limitations": [
            "one source video group only; not train/validation/test eligible",
            "manual diagnostic labels are error-analysis labels, not a complete content-understanding gold standard",
            "this report is not B0 and cannot be compared with B1-B3",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
