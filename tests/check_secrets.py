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

# 这些文件本身允许出现「形状像密钥」的内容：占位符、说明文档、扫描器自己的正则
ALLOWLIST = {
    ".env.example",
    "tests/check_secrets.py",
    "tests/verify_remote_clean.py",
    "README.md",
    "docs/架构设计.md",
}

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".vendor"}
SKIP_SUFFIX = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".zip", ".gz"}

# 这些路径根本不该进版本库，扫到直接算失败
MUST_BE_IGNORED = [".env", "data"]

# 看起来像「采集数据导出」的文件 —— 里面是真实网友的发言和用户名。
# 这类文件常常直接躺在仓库根目录上（浏览器/表格工具导出的默认位置），
# `git add -A` 会一把把它们搂进来。
DATA_FILE_PATTERNS = [
    re.compile(r"评论导出"),
    re.compile(r"comment", re.I),
    re.compile(r"^_xls_tmp/"),
]
DATA_FILE_SUFFIX = {".csv", ".xlsx", ".xls", ".tsv", ".jsonl"}


def staged_or_untracked() -> list[str]:
    """列出「如果现在 commit，会被带进去」的文件（已暂存 + 未忽略的未跟踪）。"""
    out: list[str] = []
    try:
        proc = __import__("subprocess").run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except Exception:  # noqa: BLE001
        return out
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        status, path = line[:2], line[3:].strip()
        if status.strip() == "D":
            continue
        # git 对含非 ASCII 的路径会加引号并转义，这里还原一下
        if path.startswith('"') and path.endswith('"'):
            try:
                path = path[1:-1].encode("latin-1").decode("unicode_escape").encode(
                    "latin-1").decode("utf-8")
            except (UnicodeDecodeError, UnicodeEncodeError):
                path = path[1:-1]
        out.append(path)
    return out


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

    # 3) 拦「会被提交的数据导出文件」
    #    这一步是补上真实踩过的坑：`git add -A` 把根目录上一个 96KB 的
    #    「xxx_评论导出.csv」（含真实网友用户名）一把搂进了提交。
    #    密钥扫描抓不到它 —— 它不是密钥，是隐私。
    print("\n== 即将提交的文件里有没有数据导出 ==")
    pending = staged_or_untracked()
    suspicious = []
    for path in pending:
        normalized = path.replace("\\", "/")
        suffix = Path(normalized).suffix.lower()
        if suffix in DATA_FILE_SUFFIX or any(
            p.search(normalized) for p in DATA_FILE_PATTERNS
        ):
            suspicious.append(normalized)

    if pending:
        print(f"  待提交文件共 {len(pending)} 个")
    if suspicious:
        for s in suspicious:
            problems.append(f"{s} 像是采集数据导出（含真实网友发言），不该提交")
            print(f"  [FAIL] {s}")
        print("         如果是误报，把它加进 .gitignore 或用 git add 精确挑选文件。")
    else:
        print("  [ok] 没有数据导出混进来")

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
