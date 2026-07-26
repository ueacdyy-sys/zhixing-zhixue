"""Export Label Studio annotations and project XML as versionable JSON artifacts."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def export_project(database: Path, project_id: int) -> tuple[str, list[dict[str, Any]]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        project = connection.execute("select label_config from project where id = ?", (project_id,)).fetchone()
        if project is None:
            raise ValueError(f"label_studio_project_missing:{project_id}")
        rows = connection.execute(
            """select task.id as task_id, task.data as data, task_completion.id as annotation_id,
                      task_completion.result as result, task_completion.created_at as created_at,
                      task_completion.updated_at as updated_at, task_completion.ground_truth as ground_truth
               from task join task_completion on task_completion.task_id = task.id
               where task.project_id = ? order by task.id, task_completion.id""",
            (project_id,),
        ).fetchall()
    finally:
        connection.close()
    exported: list[dict[str, Any]] = []
    for row in rows:
        data = json.loads(row["data"])
        exported.append(
            {
                "task_id": row["task_id"],
                "annotation_id": row["annotation_id"],
                "dataset_record_id": data.get("dataset_record_id"),
                "window_id": data.get("window_id"),
                "data": data,
                "result": json.loads(row["result"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "ground_truth": bool(row["ground_truth"]),
                "provenance": "label_studio_export; annotation authorship must be audited separately",
            }
        )
    return str(project["label_config"]), exported


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config, annotations = export_project(args.database, args.project_id)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "label_config.xml").write_text(config, encoding="utf-8")
    with (args.output_dir / "annotations.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for annotation in annotations:
            handle.write(json.dumps(annotation, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"project_id": args.project_id, "annotations": len(annotations), "output_dir": str(args.output_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
