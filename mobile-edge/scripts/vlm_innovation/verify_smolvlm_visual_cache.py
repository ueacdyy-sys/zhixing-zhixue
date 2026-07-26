"""Execute one real SmolVLM visual-encoder/cache safety check on sealed media.

This is intentionally not a B2 result: a high-UI diagnostic window should be
refused for reuse.  The check proves the framework's image-hidden-state path
and the evidence-aware rejection path with a real local model and MP4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from realtime_runtime.full_video_vlm import PROMPT, SmolVlmFullVideoLane

from .cache import EvidenceAwareVisualCache
from .contracts import CacheQuality, EvidenceWindowKey
from .dataset import load_manifest, sha256_file
from .smolvlm_visual_cache import SmolVlmVisualTokenAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--record-id", default=None)
    args = parser.parse_args()
    records = load_manifest(args.dataset)
    record = next((item for item in records if item["record_id"] == args.record_id), records[0])
    video = args.dataset / record["video"]
    vlm = json.loads((args.dataset / record["evidence"]["vlm"]).read_text(encoding="utf-8"))
    lane = SmolVlmFullVideoLane(args.model_dir)
    lane._load()
    assert lane._model is not None and lane._processor is not None
    messages = [{"role": "user", "content": [{"type": "video", "path": str(video)}, {"type": "text", "text": PROMPT}]}]
    inputs = lane._processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt").to(lane._device)
    quality = CacheQuality(ui_interference=1.0, ocr_asr_support=0.50, content_change=0.10)
    coverage = vlm["coverage"]
    key = EvidenceWindowKey(record["source_session"], f"diagnostic:{record['window_id']}", sha256_file(video), int(coverage["start_pts_ns"]), int(coverage["end_pts_ns"]), str(vlm["model"]))
    cache = EvidenceAwareVisualCache(args.output_dir / "cache", max_bytes=512 * 1024 * 1024)
    adapter = SmolVlmVisualTokenAdapter(lane._model, cache)
    started = time.monotonic_ns()
    block_id = adapter.encode_and_keep(key=key, quality=quality, pixel_values=inputs["pixel_values"], pixel_attention_mask=inputs.get("pixel_attention_mask"))
    encoder_ms = (time.monotonic_ns() - started) / 1_000_000
    reused = adapter.try_reuse(block_id=block_id, target=key, target_quality=quality, max_gap_ns=0)
    report = {
        "status": "COMPONENT_CHECK_ONLY",
        "record_id": record["record_id"],
        "model": vlm["model"],
        "framework_cache_object": "SmolVLM.image_hidden_states",
        "encoded_visual_block": block_id,
        "vision_encoder_ms": encoder_ms,
        "reuse_result": "REFUSED_AS_EXPECTED" if reused is None else "UNEXPECTED_REUSE",
        "refusal_reason": "high_ui_interference; this diagnostic window must not be reused",
        "not_an_ablation": True,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "component_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if reused is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
