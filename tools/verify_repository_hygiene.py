from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


FORBIDDEN_TRACKED = re.compile(
    r"(^|/)(node_modules|\.gradle|env|\.venv|captures|tools/android-sdk|build)/|"
    r"\.apk$|local\.properties$|progress_docx_render|追加前备份"
)
OLD_ROOT = "HuaweiCup_PhoneCaptureLab"
OLD_ROOT_ALLOWLIST = {"tools/Clean-LocalArtifacts.ps1", "tools/verify_repository_hygiene.py"}


def tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.splitlines()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    for relative in tracked_files(root):
        if FORBIDDEN_TRACKED.search(relative):
            failures.append(f"不应追踪的本地制品：{relative}")
            continue
        path = root / relative
        if not path.exists():
            continue
        if path.suffix.lower() in {".md", ".ps1", ".py", ".kt", ".kts", ".toml", ".xml", ".json"}:
            if OLD_ROOT in path.read_text(encoding="utf-8", errors="strict") and relative not in OLD_ROOT_ALLOWLIST:
                failures.append(f"遗留旧项目路径：{relative}")

    if failures:
        print("仓库卫生校验失败：")
        print("\n".join(failures))
        return 1
    print("仓库卫生校验通过：未追踪本地制品，未发现遗留运行路径。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
