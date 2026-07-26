"""Train the temporal Router only after video-level splits and labels are valid."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from .dataset import audit_dataset, require_training_eligible
from .router import build_temporal_expert_router, router_loss


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _validated_examples(features: list[dict[str, Any]], supervision: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels = {row.get("record_id"): row for row in supervision}
    examples: list[dict[str, Any]] = []
    for row in features:
        label = labels.get(row.get("record_id"))
        required = ("expert_weights", "cache_action", "execution", "confidence")
        if label is None or any(key not in label for key in required):
            continue
        if len(label["expert_weights"]) != 5 or len(label["execution"]) != 3:
            raise ValueError(f"router_supervision_shape_invalid:{row.get('record_id')}")
        examples.append({**row, "target": label})
    if not examples:
        raise ValueError("no_labelled_router_examples; weak labels are not Router supervision")
    return examples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--supervision", type=Path, required=True, help="Human-reviewed Router targets, not generated defaults")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260726)
    args = parser.parse_args()
    audit = audit_dataset(args.dataset)
    require_training_eligible(audit)
    if args.epochs < 1:
        raise ValueError("epochs_must_be_positive")
    import torch
    from torch import optim

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    examples = _validated_examples(_jsonl(args.features), _jsonl(args.supervision))
    train = [row for row in examples if row["split"] == "train"]
    validation = [row for row in examples if row["split"] == "validation"]
    if not train or not validation:
        raise ValueError("router_training_requires_labelled_train_and_validation_examples")
    dimension = len(train[0]["features"])
    if any(len(row["features"]) != dimension for row in examples):
        raise ValueError("router_feature_dimension_mismatch")
    model = build_temporal_expert_router(feature_dim=dimension)
    optimizer = optim.AdamW(model.parameters(), lr=2e-4, weight_decay=1e-3)
    history = []
    for epoch in range(args.epochs):
        model.train()
        losses = []
        for row in train:
            features = torch.tensor([row["features"]], dtype=torch.float32)
            output = model(features, features.unsqueeze(1))
            target = row["target"]
            targets = {
                "expert_weights": torch.tensor([target["expert_weights"]], dtype=torch.float32),
                "cache_action": torch.tensor([target["cache_action"]], dtype=torch.long),
                "execution": torch.tensor([target["execution"]], dtype=torch.float32),
                "confidence": torch.tensor([target["confidence"]], dtype=torch.float32),
            }
            loss = router_loss(output, targets)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        history.append({"epoch": epoch + 1, "train_loss": sum(losses) / len(losses)})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "feature_dim": dimension, "seed": args.seed}, args.output_dir / "router.pt")
    report = {"status": "TRAINED", "train_examples": len(train), "validation_examples": len(validation), "epochs": args.epochs, "history": history, "warning": "Evaluation is separate; do not infer correctness from train loss."}
    (args.output_dir / "training_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
