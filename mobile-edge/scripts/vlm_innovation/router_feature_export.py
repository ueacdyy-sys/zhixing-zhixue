"""CLI for the unified evidence/Routing feature vector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .router_features import FEATURE_NAMES, export_router_features


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-signals", type=Path, default=None)
    args = parser.parse_args()
    count = export_router_features(args.experts, args.output, args.runtime_signals)
    print(json.dumps({"records": count, "feature_count": len(FEATURE_NAMES), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
