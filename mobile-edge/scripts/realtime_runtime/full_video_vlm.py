"""Persistent SmolVLM2 adapter that consumes complete MP4 semantic windows."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROMPT = (
    "Describe visible facts only in one concise English sentence of at most 16 words. "
    "Include scene, activity, and any readable text when present; write unknown when unclear. "
    "Do not infer the viewer's interest, ability, attention, identity, or learning outcome."
)


@dataclass(frozen=True)
class FullVideoVlmJob:
    window_id: str
    video_mp4: Path
    start_pts_ns: int
    end_pts_ns: int
    output_dir: Path

    def __post_init__(self) -> None:
        if not self.window_id or self.video_mp4.suffix.lower() != ".mp4":
            raise ValueError("full_video_vlm_job_invalid")
        if self.start_pts_ns < 0 or self.end_pts_ns <= self.start_pts_ns:
            raise ValueError("full_video_vlm_pts_invalid")


class SmolVlmFullVideoLane:
    """A single GPU resident model; it never opens RTSP or accepts frame lists."""

    def __init__(self, model_dir: Path, *, device: str = "cuda", max_new_tokens: int = 24, max_video_frames: int = 4) -> None:
        self._model_dir = model_dir
        self._device = device
        self._max_new_tokens = max_new_tokens
        self._max_video_frames = max_video_frames
        self._processor: Any | None = None
        self._model: Any | None = None
        self._torch: Any | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        if self._device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("vlm_cuda_unavailable")
        self._processor = AutoProcessor.from_pretrained(str(self._model_dir), local_files_only=True)
        self._processor.video_processor.video_sampling["max_frames"] = self._max_video_frames
        # Transformers 4.57 hard-codes TorchCodec for chat-template videos.
        # This Windows runtime has Decord installed but no compatible TorchCodec
        # shared library, so override only this outer decoding adapter.
        from transformers.video_utils import load_video

        def fetch_with_decord(video_url_or_urls: Any, sample_indices_fn: Any = None) -> Any:
            if isinstance(video_url_or_urls, list):
                return list(zip(*[fetch_with_decord(item, sample_indices_fn) for item in video_url_or_urls]))
            return load_video(video_url_or_urls, backend="decord", sample_indices_fn=sample_indices_fn)

        self._processor.video_processor.fetch_videos = fetch_with_decord
        self._model = AutoModelForImageTextToText.from_pretrained(
            str(self._model_dir), dtype=torch.float16, local_files_only=True, low_cpu_mem_usage=True
        ).to(self._device).eval()
        self._torch = torch

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def analyze(self, job: FullVideoVlmJob) -> Path:
        if not job.video_mp4.is_file() or job.video_mp4.stat().st_size <= 0:
            raise FileNotFoundError("full_video_mp4_missing")
        self._load()
        assert self._processor is not None and self._model is not None and self._torch is not None
        started_ns = time.monotonic_ns()
        messages = [{"role": "user", "content": [{"type": "video", "path": str(job.video_mp4)}, {"type": "text", "text": PROMPT}]}]
        inputs = self._processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self._device)
        with self._torch.inference_mode():
            generated = self._model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=self._max_new_tokens,
                repetition_penalty=1.08,
            )
        prompt_tokens = inputs["input_ids"].shape[1]
        text = self._processor.batch_decode(generated[:, prompt_tokens:], skip_special_tokens=True)[0].strip()
        completed_ns = time.monotonic_ns()
        artifact = {
            "schema_version": "full_video_vlm.v1",
            "classification": "CANDIDATE_ONLY",
            "model": "HuggingFaceTB/SmolVLM2-500M-Video-Instruct",
            "input_kind": "COMPLETE_MP4_SEMANTIC_WINDOW_WITH_FRAME_SAMPLING",
            "video_sampling": {
                "max_frames": self._max_video_frames,
                "observation_boundary": "The complete MP4 is retained and hashed, but this VLM observes at most max_frames decoded samples; it is not a frame-by-frame claim.",
            },
            "window_id": job.window_id,
            "media_sha256": self._sha256(job.video_mp4),
            "coverage": {"start_pts_ns": job.start_pts_ns, "end_pts_ns": job.end_pts_ns},
            "started_monotonic_ns": started_ns,
            "completed_monotonic_ns": completed_ns,
            "raw_model_text": text,
        }
        job.output_dir.mkdir(parents=True, exist_ok=True)
        file_stem = hashlib.sha256(job.window_id.encode("utf-8")).hexdigest()[:20]
        final_path = job.output_dir / f"{file_stem}.full-video-vlm.json"
        partial_path = final_path.with_suffix(final_path.suffix + ".partial")
        partial_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(partial_path, final_path)
        return final_path
