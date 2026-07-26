"""Export reproducible feature rows; unavailable runtime signals retain masks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset import write_jsonl
from .features import build_feature_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = list(build_feature_rows(args.dataset))
    write_jsonl(rows, args.output)
    print(json.dumps({"records": len(rows), "feature_count": len(rows[0]["features"]) if rows else 0, "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
