"""Persistent GPU Whisper lane with a local CUDA DLL boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class PersistentWhisperLane:
    """Resident ASR lane isolated from the VLM CUDA workload.

    The tiny model is deliberately CPU/int8 here: concurrent CUDA ASR and VLM
    caused kernel/context contention on the 11 GiB RTX 2080 Ti and increased
    the critical fusion tail.  CPU ASR remains a separate, simultaneous lane.
    """

    def __init__(self, model_id: str = "tiny", *, cpu_threads: int = 8) -> None:
        if cpu_threads < 1:
            raise ValueError("asr_cpu_threads_invalid")
        self._model_id = model_id
        self._cpu_threads = cpu_threads
        self._model: Any | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            self._model_id,
            device="cpu",
            compute_type="int8",
            cpu_threads=self._cpu_threads,
            num_workers=1,
            local_files_only=True,
        )

    def transcribe(self, wav_path: Path) -> list[dict[str, float | str]]:
        self._load()
        assert self._model is not None
        segments, _ = self._model.transcribe(str(wav_path), beam_size=1, vad_filter=True, condition_on_previous_text=False)
        return [{"start_s": float(item.start), "end_s": float(item.end), "text": str(item.text).strip()} for item in segments]
