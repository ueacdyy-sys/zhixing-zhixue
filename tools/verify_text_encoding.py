from __future__ import annotations

import subprocess
import sys
from pathlib import Path


TEXT_SUFFIXES = {
    ".css", ".gradle", ".html", ".java", ".js", ".json", ".kts", ".kt",
    ".md", ".mjs", ".properties", ".ps1", ".py", ".toml", ".ts", ".tsx",
    ".txt", ".xml", ".yaml", ".yml",
}
FORBIDDEN_MARKERS = ("\ufeff", "\ufffd", "\u951f\u65a4\u62f7", "\u00ef\u00bf\u00bd")


def candidate_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [root / item for item in result.stdout.splitlines() if (root / item).suffix.lower() in TEXT_SUFFIXES]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    sys.stderr.reconfigure(encoding="utf-8", errors="strict")
    root = Path(__file__).resolve().parents[1]
    failures: list[str] = []

    files = candidate_files(root)
    for path in files:
        if not path.exists():
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as error:
            failures.append(f"{path.relative_to(root)}: 非 UTF-8 字节，{error}")
            continue
        markers = [marker for marker in FORBIDDEN_MARKERS if marker in text]
        if markers:
            failures.append(f"{path.relative_to(root)}: 疑似乱码标记 {markers!r}")

    if failures:
        print("文本编码校验失败：")
        print("\n".join(failures))
        return 1

    print(f"文本编码校验通过：{len(files)} 个文本文件均为 UTF-8，未发现常见乱码标记。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
