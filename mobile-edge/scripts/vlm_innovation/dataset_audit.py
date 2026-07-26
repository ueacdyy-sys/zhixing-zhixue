"""CLI entry point for a fail-closed innovation-dataset audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset import audit_dataset, require_training_eligible, write_audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-training-eligible", action="store_true")
    args = parser.parse_args()
    audit = audit_dataset(args.dataset)
    write_audit(audit, args.output)
    print(json.dumps(audit.as_dict(), ensure_ascii=False))
    if args.require_training_eligible:
        require_training_eligible(audit)
    return 0 if audit.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
