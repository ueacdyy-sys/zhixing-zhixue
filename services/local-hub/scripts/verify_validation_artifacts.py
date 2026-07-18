"""检查端到端验证日志不含敏感字段，且证据引用保持本地化。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FORBIDDEN_KEY_PARTS = ("credential", "teacher", "user_hash", "token", "password", "adb")


def _check_value(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if any(part in key.lower() for part in FORBIDDEN_KEY_PARTS):
                raise ValueError(f"forbidden_key:{path}.{key}")
            _check_value(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _check_value(nested, f"{path}[{index}]")
    elif isinstance(value, str) and value.startswith(("http://", "https://", "file://", "local://")):
        raise ValueError(f"non_local_reference:{path}")


def main() -> None:
    validation_dir = Path(__file__).resolve().parents[1] / "evidence" / "validation"
    files = sorted(validation_dir.glob("*.json"))
    if len(files) < 2:
        raise ValueError("two_validation_logs_required")
    for artifact in files:
        _check_value(json.loads(artifact.read_text(encoding="utf-8")), artifact.name)
    print(f"validation artifacts verified: {len(files)}")


if __name__ == "__main__":
    main()
