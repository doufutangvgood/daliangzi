"""提交前的密钥扫描。

在推上 GitHub 之前跑一遍：扫全树，看有没有把密钥、令牌、cookie 写进文件。

    python tests/check_secrets.py

退出码 0 = 干净，1 = 发现问题。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

# 明文密钥的形状。宁可误报也不能漏报。
PATTERNS = [
    (r"sk-[A-Za-z0-9]{16,}", "疑似 OpenAI/DeepSeek 风格的密钥"),
    (r"user_[A-Za-z0-9]{16,}", "疑似 Command Code 风格的密钥"),
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "疑似 GitHub 令牌"),
    (r"SESSDATA=[^;\s\"']+", "疑似 B站 会话 cookie"),
    (r"bili_jct=[^;\s\"']+", "疑似 B站 csrf cookie"),
    (r"Bearer\s+[A-Za-z0-9_\-\.]{24,}", "疑似硬编码的 Bearer 令牌"),
    (r"AKIA[0-9A-Z]{16}", "疑似 AWS Access Key"),
    (r"DEEPSEEK_API_KEY\s*=\s*[A-Za-z0-9_\-]{12,}", "疑似 .env 里的真实 key"),
    (r"COMMANDCODE_API_KEY\s*[:=]\s*[A-Za-z0-9_\-]{12,}", "疑似真实 CC key"),
]

# 这些文件本身允许出现「形状像密钥」的内容（占位符、说明文档、扫描器自己）
ALLOWLIST = {
    ".env.example",
    "tests/check_secrets.py",
    "tests/check_commandcode.py",
    "tests/probe_commandcode.py",
    "tests/probe_alpha_generate.py",
    "README.md",
}

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".vendor"}
SKIP_SUFFIX = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".zip", ".gz"}

# 这些路径根本不该进版本库，扫到直接算失败
MUST_BE_IGNORED = [".env", "data"]


def main() -> int:
    problems: list[str] = []
    warnings: list[str] = []
    scanned = 0

    # 1) 敏感路径必须被 .gitignore 覆盖
    print("== 敏感路径检查 ==")
    gitignore = (ROOT / ".gitignore")
    ignored_text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    for rel in MUST_BE_IGNORED:
        p = ROOT / rel
        covered = any(
            line.strip().rstrip("/") == rel and line.strip() and not line.startswith("#")
            for line in ignored_text.splitlines()
        )
        exists = p.exists()
        mark = "ok  " if covered else "FAIL"
        print(f"  [{mark}] {rel}  （存在={exists}，已被 .gitignore 覆盖={covered}）")
        if not covered:
            problems.append(f"{rel} 没有被 .gitignore 覆盖")
        if rel == ".env" and exists and not covered:
            problems.append(".env 存在且未被忽略 —— 密钥会直接推上去")

    # 2) 全树扫描密钥形状
    print("\n== 全树扫描 ==")
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() in SKIP_SUFFIX:
                continue
            rel = str(path.relative_to(ROOT)).replace("\\", "/")

            # .env 和 data/ 本身是敏感区，单独报
            if rel == ".env" or rel.startswith("data/"):
                warnings.append(f"{rel} 含本地敏感数据（应被忽略，不该提交）")
                continue

            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            scanned += 1

            for pattern, desc in PATTERNS:
                for m in re.finditer(pattern, text):
                    hit = m.group(0)
                    # 占位符和文档示意放过
                    if set(hit) <= set("xX*.-_") or "your" in hit.lower():
                        continue
                    if rel in ALLOWLIST:
                        continue
                    line_no = text[: m.start()].count("\n") + 1
                    # 只报前 12 个字符，避免把密钥本身打进终端/日志
                    problems.append(
                        f"{rel}:{line_no}  {desc}（{hit[:12]}…）"
                    )

    print(f"  扫描了 {scanned} 个文本文件")

    if warnings:
        print("\n== 本地敏感数据（确认不会提交）==")
        for w in warnings:
            print(f"  [!] {w}")

    print("\n== 结论 ==")
    if problems:
        for p in problems:
            print(f"  [FAIL] {p}")
        print(f"\n发现 {len(problems)} 个问题，**不要提交**。")
        return 1

    print("  [ok] 没有发现明文密钥")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
