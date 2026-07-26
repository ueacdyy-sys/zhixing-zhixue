"""Evaluate four normalized B0-B3 logs, refusing incomparable inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluation import evaluate, load_predictions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = [record for path in args.predictions for record in load_predictions(path)]
    report = evaluate(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
