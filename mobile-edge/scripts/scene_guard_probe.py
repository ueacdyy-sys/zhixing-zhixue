from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class SceneGuardResult:
    file: str
    text_joined: str
    label: str
    allow_semantic_understanding: bool
    reason: str
    matched_terms: list[str]


RULES = [
    {
        "label": "blocked_sensitive_permission_dialog",
        "allow": False,
        "terms": ["是否允许USB调试", "RSA密钥", "始终允许使用这台计算机进行调试", "USB调试"],
        "reason": "系统权限/调试授权弹窗，不能作为视频内容理解对象。",
    },
    {
        "label": "blocked_lockscreen_or_system_overlay",
        "allow": False,
        "terms": ["上滑解锁", "正在充电", "点按停止以结束串流", "串流中", "ScreenStream刚"],
        "reason": "锁屏、通知或系统浮层，不属于短视频内容页。",
    },
    {
        "label": "blocked_screenstream_control_page",
        "allow": False,
        "terms": ["选择串流模式", "RTSP服务器地址", "停止流媒体", "服务器设置", "ScreenStream"],
        "reason": "ScreenStream控制页，只能用于采集链路测试，不能进入学习语义理解。",
    },
    {
        "label": "blocked_payment_or_private",
        "allow": False,
        "terms": ["付款", "支付", "密码", "相册", "消息", "聊天", "验证码"],
        "reason": "潜在隐私或支付场景，默认拦截。",
    },
]


def classify_text(texts: list[str], file: str) -> SceneGuardResult:
    joined = " | ".join(texts)
    for rule in RULES:
        matched = [term for term in rule["terms"] if term in joined]
        if matched:
            return SceneGuardResult(
                file=file,
                text_joined=joined,
                label=rule["label"],
                allow_semantic_understanding=bool(rule["allow"]),
                reason=rule["reason"],
                matched_terms=matched,
            )
    if len(joined.strip()) < 8:
        return SceneGuardResult(
            file=file,
            text_joined=joined,
            label="blocked_low_information",
            allow_semantic_understanding=False,
            reason="可用文字太少，不能可靠判断是否为视频内容页。",
            matched_terms=[],
        )
    return SceneGuardResult(
        file=file,
        text_joined=joined,
        label="unknown_needs_review",
        allow_semantic_understanding=False,
        reason="未命中安全准入规则；真实产品中需结合前台App、画面分类和用户授权场景复核。",
        matched_terms=[],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Rule-based scene guard for OCR probe output.")
    parser.add_argument("--ocr-report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report = json.loads(Path(args.ocr_report).read_text(encoding="utf-8"))
    results: list[SceneGuardResult] = []
    for item in report.get("results", []):
        results.append(classify_text(item.get("text", []), item.get("file", "")))

    counts: dict[str, int] = {}
    allowed = 0
    for item in results:
        counts[item.label] = counts.get(item.label, 0) + 1
        if item.allow_semantic_understanding:
            allowed += 1

    output: dict[str, Any] = {
        "ocr_report": str(args.ocr_report),
        "frame_count": len(results),
        "allowed_count": allowed,
        "blocked_count": len(results) - allowed,
        "label_counts": counts,
        "results": [asdict(item) for item in results],
        "notes": [
            "This is a conservative guardrail probe, not final classification.",
            "Unknown scenes are blocked until foreground app, visual category, and consent boundary are checked.",
            "The next implementation layer should fuse OCR rules with ADB foreground-app state and visual scene classification.",
        ],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "out": str(args.out),
        "frame_count": output["frame_count"],
        "allowed_count": allowed,
        "blocked_count": output["blocked_count"],
        "label_counts": counts,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
