"""Produce the PTS/hash evidence index consumed by innovation experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset import build_evidence_index, write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = build_evidence_index(args.dataset)
    write_jsonl(rows, args.output)
    print(json.dumps({"records": len(rows), "output": str(args.output), "integrity": "PTS_HASH_ALIGNED"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
