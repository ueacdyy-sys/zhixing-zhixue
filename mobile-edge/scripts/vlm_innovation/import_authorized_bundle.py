"""Import one authorised sealed-media source into the future training corpus.

The importer accepts only a complete RTSP/worker artifact bundle, requires an
externally verified source-video SHA-256 and records the rights basis.  It never
uses a window MP4 hash as a substitute for the complete source-video hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .contracts import InnovationContractError
from .dataset import build_evidence_index, load_manifest, write_jsonl


RIGHTS_BASES = {"USER_OWNED", "OPEN_LICENSE", "EXPLICIT_PERMISSION"}


def _sha(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
        raise InnovationContractError("verified_source_video_hash_must_be_sha256")


def _artifact_root(source_root: Path) -> Path:
    candidate = source_root / "artifacts"
    return candidate if candidate.is_dir() else source_root


def _load_existing(destination: Path) -> list[dict[str, Any]]:
    return load_manifest(destination) if (destination / "manifest.jsonl").is_file() else []


def import_bundle(
    *,
    source_root: Path,
    destination: Path,
    source_video_group: str,
    verified_source_video_hash: str,
    rights_basis: str,
    rights_reference: str,
    content_type: str,
) -> dict[str, Any]:
    if not source_video_group or not rights_reference.strip() or not content_type.strip():
        raise InnovationContractError("source_group_rights_reference_and_content_type_required")
    _sha(verified_source_video_hash)
    if rights_basis not in RIGHTS_BASES:
        raise InnovationContractError("rights_basis_invalid")
    artifacts = _artifact_root(source_root.resolve())
    vlm_paths = sorted(artifacts.glob("*.full-video-vlm.json"))
    if not vlm_paths:
        raise InnovationContractError("sealed_full_video_vlm_artifacts_missing")
    windows = artifacts / "windows"
    if not windows.is_dir():
        raise InnovationContractError("sealed_window_media_missing")
    destination = destination.resolve()
    media_root, evidence_root = destination / "media", destination / "evidence"
    media_root.mkdir(parents=True, exist_ok=True)
    evidence_root.mkdir(parents=True, exist_ok=True)
    existing = _load_existing(destination)
    existing_ids = {str(record.get("record_id")) for record in existing}
    source_session: str | None = None
    imported: list[dict[str, Any]] = []
    for vlm_path in vlm_paths:
        stem = vlm_path.name.removesuffix(".full-video-vlm.json")
        ocr_path, asr_path, video_path = artifacts / f"{stem}.ocr.json", artifacts / f"{stem}.asr.json", windows / f"{stem}.mp4"
        if not (ocr_path.is_file() and asr_path.is_file() and video_path.is_file()):
            raise InnovationContractError(f"incomplete_sealed_bundle:{stem}")
        vlm = json.loads(vlm_path.read_text(encoding="utf-8"))
        window_id = vlm.get("window_id")
        if not isinstance(window_id, str) or ":window:" not in window_id:
            raise InnovationContractError(f"window_id_invalid:{stem}")
        session = window_id.rsplit(":window:", 1)[0]
        if source_session is None:
            source_session = session
        elif source_session != session:
            raise InnovationContractError("source_root_contains_multiple_sessions")
        number = int(window_id.rsplit(":", 1)[-1])
        record_id = f"{source_video_group}-{number:06d}-{hashlib.sha256(stem.encode('utf-8')).hexdigest()[:12]}"
        if record_id in existing_ids:
            raise InnovationContractError(f"duplicate_record_id:{record_id}")
        media_name = f"{record_id}.mp4"
        copied = {"ocr": f"evidence/{record_id}.ocr.json", "asr": f"evidence/{record_id}.asr.json", "vlm": f"evidence/{record_id}.vlm.json"}
        shutil.copy2(video_path, media_root / media_name)
        shutil.copy2(ocr_path, destination / copied["ocr"])
        shutil.copy2(asr_path, destination / copied["asr"])
        shutil.copy2(vlm_path, destination / copied["vlm"])
        imported.append(
            {
                "dataset_version": "vlm_screen_training_v1",
                "record_id": record_id,
                "source_session": session,
                "source_video_group": source_video_group,
                "verified_source_video_hash": verified_source_video_hash,
                "split": "unassigned",
                "window_id": window_id,
                "window_number": number,
                "video": f"media/{media_name}",
                "evidence": copied,
                "rights": {"basis": rights_basis, "reference": rights_reference},
                "content_type_claim": content_type,
                "annotation_state": "PENDING_LABEL_STUDIO_V2_HUMAN_REVIEW",
                "candidate_status": "CANDIDATE_ONLY",
            }
        )
    merged = existing + imported
    write_jsonl(merged, destination / "manifest.jsonl")
    registry = destination / "source_registry.jsonl"
    registry_rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines() if line.strip()] if registry.is_file() else []
    registry_rows.append({"source_video_group": source_video_group, "verified_source_video_hash": verified_source_video_hash, "rights_basis": rights_basis, "rights_reference": rights_reference, "source_session": source_session, "windows_imported": len(imported)})
    write_jsonl(registry_rows, registry)
    # Re-open the copied files, checking PTS/hash binding after import rather
    # than trusting the source directory or copy operation.
    evidence_index = build_evidence_index(destination)
    write_jsonl(evidence_index, destination / "evidence_index.jsonl")
    return {"status": "IMPORTED_PENDING_HUMAN_REVIEW", "source_video_group": source_video_group, "records_imported": len(imported), "destination": str(destination)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-video-group", required=True)
    parser.add_argument("--verified-source-video-hash", required=True)
    parser.add_argument("--rights-basis", choices=sorted(RIGHTS_BASES), required=True)
    parser.add_argument("--rights-reference", required=True)
    parser.add_argument("--content-type", required=True)
    args = parser.parse_args()
    print(json.dumps(import_bundle(**vars(args)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
