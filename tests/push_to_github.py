"""创建 GitHub 仓库并推送。

用从 git 凭据助手取到的令牌调 API 建仓库，再用**一次性 URL** 推送，
这样令牌不会写进 .git/config 留在磁盘上。全程不回显令牌。

    python tests/push_to_github.py <repo名> [public|private]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent


def git(*args: str, check: bool = True, redact: str = "") -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    if check and proc.returncode != 0:
        out = (proc.stdout + proc.stderr).replace(redact, "<redacted>") if redact else (proc.stdout + proc.stderr)
        print(f"  git {' '.join(a for a in args if a != redact)} 失败：")
        print("  " + out[:600])
        raise SystemExit(1)
    return proc


def get_credential() -> tuple[str, str]:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, timeout=60,
    )
    user = token = ""
    for line in proc.stdout.splitlines():
        if line.startswith("username="):
            user = line.split("=", 1)[1]
        elif line.startswith("password="):
            token = line.split("=", 1)[1]
    if not token:
        print("取不到 GitHub 凭据。")
        print("用 stdio=inherit 再试一次……")
        subprocess.run(["git", "credential", "fill"],
                       input="protocol=https\nhost=github.com\n\n", text=True)
        raise SystemExit(1)
    return user, token


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "daliangzi"
    visibility = sys.argv[2] if len(sys.argv) > 2 else "public"

    user, token = get_credential()
    print(f"凭据：{user}（令牌 {token[:4]}…，长度 {len(token)}）")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "daliangzi-push",
    }

    with httpx.Client(timeout=60, headers=headers) as c:
        full = f"{user}/{name}"
        r = c.get(f"https://api.github.com/repos/{full}")
        if r.status_code == 200:
            print(f"仓库 {full} 已存在，跳过创建。")
            html_url = r.json()["html_url"]
        else:
            print(f"创建仓库 {full}（{visibility}）…")
            r = c.post("https://api.github.com/user/repos", json={
                "name": name,
                "description": "大量子 · 网络观点分析工具 —— 把网络事件下的评论归纳成带占比的立场类别，排布成立场坐标轴，生成「立场一览」报告。",
                "private": visibility == "private",
                "has_issues": True,
                "has_wiki": False,
                "auto_init": False,
            })
            if r.status_code not in (200, 201):
                print(f"  [FAIL] HTTP {r.status_code}")
                print("  " + r.text[:400])
                return 1
            html_url = r.json()["html_url"]
            print(f"  [ok] {html_url}")

    # 先确认本地干净
    status = git("status", "--porcelain").stdout.strip()
    if status:
        print("工作区还有未提交的改动：")
        print("  " + status[:400])
        return 1

    remote_url = f"https://github.com/{user}/{name}.git"
    push_url = f"https://{user}:{token}@github.com/{user}/{name}.git"

    print(f"\n推送 main（用一次性 URL，令牌不落盘）…")
    proc = subprocess.run(
        ["git", "push", push_url, "main:main"],
        cwd=ROOT, capture_output=True, text=True, timeout=900,
    )
    out = (proc.stdout + proc.stderr).replace(token, "<redacted>")
    print("  " + out.strip()[:800])
    if proc.returncode != 0:
        print("  [FAIL] 推送失败")
        return 1

    # 配一个不含令牌的 origin，方便以后用
    git("remote", "remove", "origin", check=False)
    git("remote", "add", "origin", remote_url)
    git("config", "branch.main.remote", "origin")
    git("config", "branch.main.merge", "refs/heads/main")

    print(f"\n完成：{html_url}")
    print("\n=== 最终核对 ===")
    print(git("status", "--short", "--branch").stdout.strip())
    print(git("remote", "-v").stdout.strip())
    print(git("log", "--oneline").stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
