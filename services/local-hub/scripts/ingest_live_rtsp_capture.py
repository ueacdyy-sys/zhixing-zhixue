"""Create Local-Hub evidence records from one completed authorized RTSP capture."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from zhixingzhixue_hub.adapters.live_rtsp_capture import register_live_rtsp_capture  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--recorded-at", default=datetime.now(timezone.utc).astimezone().isoformat())
    args = parser.parse_args()
    result = register_live_rtsp_capture(
        capture_dir=Path(args.capture_dir),
        session_id=args.session_id,
        recorded_at=args.recorded_at,
    )
    output = Path(args.capture_dir) / "local_hub" / "ingress_record.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
