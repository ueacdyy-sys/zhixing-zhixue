"""Dataset audit and video-level split gates for innovation experiments."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .contracts import InnovationContractError


@dataclass
class DatasetAudit:
    dataset_root: Path
    records: int = 0
    source_video_groups: set[str] = field(default_factory=set)
    split_groups: dict[str, set[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_root": str(self.dataset_root),
            "records": self.records,
            "source_video_groups": len(self.source_video_groups),
            "splits": {name: sorted(groups) for name, groups in sorted(self.split_groups.items())},
            "errors": self.errors,
            "warnings": self.warnings,
            "ok": self.ok,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(dataset_root: Path) -> list[dict[str, Any]]:
    manifest = dataset_root / "manifest.jsonl"
    if not manifest.is_file():
        raise FileNotFoundError(f"manifest_missing:{manifest}")
    records: list[dict[str, Any]] = []
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise InnovationContractError(f"manifest_json_invalid_line_{number}") from error
        if not isinstance(payload, dict):
            raise InnovationContractError(f"manifest_record_not_object_line_{number}")
        records.append(payload)
    if not records:
        raise InnovationContractError("manifest_has_no_records")
    return records


def audit_dataset(dataset_root: Path) -> DatasetAudit:
    root = dataset_root.resolve()
    audit = DatasetAudit(dataset_root=root)
    try:
        records = load_manifest(root)
    except Exception as error:
        audit.errors.append(str(error))
        return audit
    seen_ids: set[str] = set()
    group_to_split: dict[str, str] = {}
    for index, record in enumerate(records, 1):
        audit.records += 1
        record_id = record.get("record_id")
        group = record.get("source_video_group")
        split = record.get("split")
        if not isinstance(record_id, str) or not record_id:
            audit.errors.append(f"record_{index}_missing_record_id")
        elif record_id in seen_ids:
            audit.errors.append(f"duplicate_record_id:{record_id}")
        else:
            seen_ids.add(record_id)
        if not isinstance(group, str) or not group:
            audit.errors.append(f"record_{index}_missing_source_video_group")
            continue
        if not isinstance(split, str) or not split:
            audit.errors.append(f"record_{index}_missing_split")
            continue
        prior = group_to_split.setdefault(group, split)
        if prior != split:
            audit.errors.append(f"video_group_split_leakage:{group}:{prior}:{split}")
        audit.source_video_groups.add(group)
        audit.split_groups.setdefault(split, set()).add(group)
        video = record.get("video")
        if not isinstance(video, str) or not (root / video).is_file():
            audit.errors.append(f"record_{index}_media_missing")
        evidence = record.get("evidence")
        if not isinstance(evidence, dict):
            audit.errors.append(f"record_{index}_evidence_missing")
        else:
            for lane in ("ocr", "asr", "vlm"):
                value = evidence.get(lane)
                if not isinstance(value, str) or not (root / value).is_file():
                    audit.errors.append(f"record_{index}_{lane}_evidence_missing")
    if len(audit.source_video_groups) < 3:
        audit.warnings.append("fewer_than_three_source_video_groups; training/validation/test is not eligible")
    if set(audit.split_groups) == {"diagnostic_holdout_only"}:
        audit.warnings.append("diagnostic_holdout_only; this data is not eligible for Router training")
    return audit


def require_training_eligible(audit: DatasetAudit) -> None:
    required = {"train", "validation", "test"}
    present = {name for name, groups in audit.split_groups.items() if groups}
    if not audit.ok:
        raise InnovationContractError("dataset_audit_failed:" + ";".join(audit.errors))
    if not required.issubset(present):
        raise InnovationContractError("training_requires_nonempty_video_level_train_validation_test_splits")
    if len(audit.source_video_groups) < 3:
        raise InnovationContractError("training_requires_at_least_three_independent_source_video_groups")


def assign_video_level_splits(records: Iterable[dict[str, Any]], *, seed: str) -> list[dict[str, Any]]:
    """Deterministic group split.  It never splits records from one video."""

    copied = [dict(record) for record in records]
    groups = sorted({str(record.get("source_video_group", "")) for record in copied if record.get("source_video_group")})
    if len(groups) < 3:
        raise InnovationContractError("cannot_split_fewer_than_three_source_video_groups")
    ranked = sorted(groups, key=lambda group: hashlib.sha256(f"{seed}:{group}".encode("utf-8")).hexdigest())
    assignments: dict[str, str] = {}
    for index, group in enumerate(ranked):
        assignments[group] = "test" if index % 10 == 0 else "validation" if index % 10 == 1 else "train"
    # Guarantee all three splits exist for the smallest valid corpus.
    assignments[ranked[0]], assignments[ranked[1]], assignments[ranked[2]] = "test", "validation", "train"
    for record in copied:
        record["split"] = assignments[str(record["source_video_group"])]
    return copied


def write_audit(audit: DatasetAudit, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_evidence_index(dataset_root: Path) -> list[dict[str, Any]]:
    """Derive one immutable PTS/hash bundle per manifest record.

    This upgrades a legacy manifest without overwriting it.  All three lane
    artifacts must name the same window, media hash and PTS coverage; otherwise
    the record is rejected instead of silently becoming a training example.
    """

    root = dataset_root.resolve()
    index: list[dict[str, Any]] = []
    for record in load_manifest(root):
        evidence_paths = {lane: root / value for lane, value in record["evidence"].items()}
        artifacts = {lane: json.loads(path.read_text(encoding="utf-8")) for lane, path in evidence_paths.items()}
        lanes = ("ocr", "asr", "vlm")
        if set(lanes) - set(artifacts):
            raise InnovationContractError(f"missing_lane_artifact:{record.get('record_id')}")
        window_ids = {artifacts["vlm"].get("window_id"), *(artifacts[lane].get("window_id") for lane in ("ocr", "asr"))}
        if len(window_ids) != 1 or None in window_ids or next(iter(window_ids)) != record.get("window_id"):
            raise InnovationContractError(f"window_id_mismatch:{record.get('record_id')}")
        media = root / record["video"]
        media_hash = sha256_file(media)
        declared_hashes = {
            artifacts["vlm"].get("media_sha256"),
            artifacts["ocr"].get("input_media_sha256"),
            artifacts["asr"].get("input_media_sha256"),
        }
        if declared_hashes != {media_hash}:
            raise InnovationContractError(f"media_hash_mismatch:{record.get('record_id')}")
        vlm_coverage = artifacts["vlm"].get("coverage", {})
        start = vlm_coverage.get("start_pts_ns")
        end = vlm_coverage.get("end_pts_ns")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            raise InnovationContractError(f"vlm_coverage_invalid:{record.get('record_id')}")
        for lane in ("ocr", "asr"):
            if artifacts[lane].get("coverage_start_pts_ns") != start or artifacts[lane].get("coverage_end_pts_ns") != end:
                raise InnovationContractError(f"pts_coverage_mismatch:{record.get('record_id')}:{lane}")
        index.append(
            {
                "record_id": record["record_id"],
                "source_session": record["source_session"],
                "source_video_group": record["source_video_group"],
                "split": record["split"],
                "window_id": record["window_id"],
                "media": record["video"],
                "media_sha256": media_hash,
                "start_pts_ns": start,
                "end_pts_ns": end,
                "evidence": {
                    lane: {"path": record["evidence"][lane], "sha256": sha256_file(evidence_paths[lane])}
                    for lane in lanes
                },
                "integrity": "PTS_HASH_ALIGNED",
            }
        )
    return index


def write_jsonl(records: Iterable[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
