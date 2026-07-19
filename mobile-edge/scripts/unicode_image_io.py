"""OpenCV image I/O that remains reliable under Windows Unicode paths."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


def read_image(path: Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """Decode an image through bytes instead of OpenCV's narrow-path API."""
    try:
        encoded = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if encoded.size == 0:
        return None
    return cv2.imdecode(encoded, flags)


def write_image(
    path: Path,
    image: np.ndarray,
    params: Sequence[int] | None = None,
) -> bool:
    """Encode an image and persist it through pathlib for Unicode-safe output."""
    suffix = path.suffix or ".jpg"
    ok, encoded = cv2.imencode(suffix, image, list(params or ()))
    if not ok:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded.tobytes())
    except OSError:
        return False
    return True
