"""运行两条领域验收链并写入脱敏验证日志。"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from zhixingzhixue_hub.validation_chains import run_pc_validation_chain, run_phone_validation_chain


def _reference_fingerprints(references: list[str]) -> list[str]:
    return [sha256(f"zhixingzhixue-validation-v1|{reference}".encode()).hexdigest() for reference in references]


def _phone_log() -> dict[str, object]:
    result = run_phone_validation_chain()
    return {
        "chain": result["chain"],
        "session_status": result["session_status"],
        "card_id": result["card"]["card_id"],
        "card_confidence": result["card"]["confidence"],
        "receipt_action": result["receipt"]["action"],
        "evidence_ref_sha256": _reference_fingerprints(result["evidence_refs"]),
    }


def _pc_log() -> dict[str, object]:
    result = run_pc_validation_chain()
    return {
        "chain": result["chain"],
        "task_id": result["task"]["task_id"],
        "timeline_event_refs": [entry["event_id"] for entry in result["timeline"]["entries"]],
        "candidate_id": result["candidate"]["candidate_id"],
        "candidate_status": result["candidate"]["status"],
        "quality_decision": result["quality_log"]["decision"],
        "quality_flags": result["quality_log"]["canonical_flags"],
        "card_id": result["card"]["card_id"],
        "card_downgrade_reason": result["card"]["downgrade_reason"],
        "export_id": result["export"]["export_id"],
        "evidence_ref_sha256": _reference_fingerprints(result["export"]["evidence_refs"]),
    }


def main() -> None:
    output_dir = Path(__file__).resolve().parents[1] / "evidence" / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in (("phone-public-media-chain.json", _phone_log()), ("pc-learning-chain.json", _pc_log())):
        (output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
