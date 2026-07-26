"""Run the five evidence experts over sealed dataset windows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset import write_jsonl
from .experts import build_expert_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = build_expert_rows(args.dataset)
    write_jsonl(rows, args.output)
    print(json.dumps({"records": len(rows), "experts": 5, "output": str(args.output), "classification": "CANDIDATE_ONLY"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
