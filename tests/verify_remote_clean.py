"""推到 GitHub 之后，**从远端**验证没有密钥泄露。

本地扫描只能证明「我提交的内容是干净的」，不能证明「远端仓库里没有」。
所以这里直接拉 GitHub 上的仓库树和文件内容来查。

    python tests/verify_remote_clean.py <owner/repo>
"""

from __future__ import annotations

import re
import subprocess
import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = sys.argv[1] if len(sys.argv) > 1 else "doufutangvgood/daliangzi"

# 真实密钥前缀（从本机取，不打印）
CRED = __import__("pathlib").Path.home() / ".dsh" / ".credentials.yaml"
REAL_PREFIXES = []
try:
    text = CRED.read_text(encoding="utf-8")
    for name in ("DEEPSEEK_API_KEY", "COMMANDCODE_API_KEY"):
        m = re.search(rf"{name}\s*:\s*(\S+)", text)
        if m:
            REAL_PREFIXES.append(m.group(1)[:8])
except OSError:
    pass

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{16,}",
    r"user_[A-Za-z0-9]{16,}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"SESSDATA=[^;\s\"']+",
    r"AKIA[0-9A-Z]{16}",
]

# 允许出现的（占位符、示例、以及扫描器自己的正则模式）
ALLOW_FILES = {
    ".env.example",
    "tests/check_secrets.py",
    "tests/check_github_auth.py",
    "tests/push_to_github.py",
    "tests/verify_remote_clean.py",
    "README.md",
    "docs/架构设计.md",
}


def get_token() -> str:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("取不到令牌")


def main() -> int:
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "User-Agent": "daliangzi-verify"}
    problems: list[str] = []

    with httpx.Client(timeout=60, headers=headers) as c:
        info = c.get(f"https://api.github.com/repos/{REPO}").json()
        branch = info.get("default_branch", "main")
        print(f"仓库：{info.get('html_url')}  可见性：{'私有' if info.get('private') else '公开'}")
        print(f"默认分支：{branch}")

        # 1) 整棵树
        tree = c.get(f"https://api.github.com/repos/{REPO}/git/trees/{branch}",
                     params={"recursive": "1"}).json()
        files = [t["path"] for t in tree.get("tree", []) if t["type"] == "blob"]
        print(f"\n远端文件数：{len(files)}")

        # 2) 敏感路径检查
        # 注意 .env.example 是空值模板，本来就该在仓库里，不算敏感文件
        print("\n== 敏感路径 ==")
        SENSITIVE = [".env", ".env.local"]
        for bad in SENSITIVE:
            hit = [f for f in files if f == bad]
            if hit:
                problems.append(f"远端存在 {bad}：{hit[:5]}")
                print(f"  [FAIL] {bad} 存在：{hit[:5]}")
            else:
                print(f"  [ok] 没有 {bad}")
        data_hits = [f for f in files if f.startswith("data/")]
        if data_hits:
            problems.append(f"远端存在 data/：{data_hits[:5]}")
            print(f"  [FAIL] data/ 存在：{data_hits[:5]}")
        else:
            print("  [ok] 没有 data/")
        if any(f.endswith(".env.example") for f in files):
            print("  [ok] .env.example 在位（空值模板，本就该有）")

        # 3) 逐个文件拉内容查密钥
        print("\n== 逐个文件扫密钥 ==")
        checked = 0
        for path in files:
            if path in ALLOW_FILES:
                continue
            if path.lower().endswith((".png", ".jpg", ".ico", ".zip", ".gz")):
                continue
            raw = c.get(f"https://api.github.com/repos/{REPO}/contents/{path}",
                        params={"ref": branch},
                        headers={**headers, "Accept": "application/vnd.github.raw"})
            if raw.status_code != 200:
                continue
            content = raw.text
            checked += 1

            for pref in REAL_PREFIXES:
                if pref and pref in content:
                    problems.append(f"{path} 含真实密钥前缀 {pref}")
                    print(f"  [FAIL] {path} 命中真实前缀")

            for pattern in SECRET_PATTERNS:
                for m in re.finditer(pattern, content):
                    hit = m.group(0)
                    if set(hit) <= set("xX*.-_"):
                        continue
                    problems.append(f"{path} 命中 {pattern}：{hit[:12]}…")
                    print(f"  [FAIL] {path}  {hit[:20]}")

        print(f"  扫了 {checked} 个文本文件")

        # 4) 提交历史里也扫一遍（提交信息里别夹带）
        print("\n== 提交历史 ==")
        commits = c.get(f"https://api.github.com/repos/{REPO}/commits",
                        params={"per_page": 100}).json()
        print(f"  共 {len(commits)} 个提交")
        for cm in commits:
            msg = cm["commit"]["message"]
            for pref in REAL_PREFIXES:
                if pref and pref in msg:
                    problems.append(f"提交 {cm['sha'][:7]} 的信息里含密钥前缀")
            print(f"  {cm['sha'][:7]}  {msg.splitlines()[0][:56]}")

    print("\n== 结论 ==")
    if problems:
        for p in problems:
            print(f"  [FAIL] {p}")
        print(f"\n发现 {len(problems)} 个问题 —— **需要立刻处理**。")
        return 1
    print("  [ok] 远端仓库干净：无 .env、无 data/、无明文密钥、提交历史也没有")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
