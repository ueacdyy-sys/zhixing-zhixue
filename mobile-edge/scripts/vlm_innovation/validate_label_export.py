"""Fail closed when Label Studio exports cannot supervise the Router/evaluation."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_V2_FIELDS = {"content_type", "ui_interference", "asr_quality", "ocr_text_source", "vlm_quality", "vlm_error_type", "topic", "evidence_status", "correction"}


def annotation_fields(annotation: dict[str, Any]) -> set[str]:
    return {str(item.get("from_name")) for item in annotation.get("result", []) if isinstance(item, dict) and item.get("from_name")}


def audit_export(path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    incomplete: list[dict[str, Any]] = []
    unlinked = 0
    authoring = Counter()
    for row in rows:
        if not row.get("dataset_record_id"):
            unlinked += 1
        fields = annotation_fields(row)
        missing = sorted(REQUIRED_V2_FIELDS - fields)
        if missing:
            incomplete.append({"annotation_id": row.get("annotation_id"), "dataset_record_id": row.get("dataset_record_id"), "missing": missing})
        authoring["ground_truth" if row.get("ground_truth") else "not_ground_truth"] += 1
    return {
        "annotations": len(rows),
        "unlinked_dataset_record_id": unlinked,
        "missing_required_v2_fields": len(incomplete),
        "authoring_flags": dict(authoring),
        "eligible_for_training_supervision": len(rows) > 0 and not incomplete and not unlinked,
        "incomplete_examples": incomplete[:20],
        "warning": "A Label Studio ground_truth flag is not a substitute for author/audit provenance.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_export(args.annotations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["eligible_for_training_supervision"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
