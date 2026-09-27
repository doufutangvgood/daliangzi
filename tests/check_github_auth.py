"""用已保存的 git 凭据验证 GitHub 身份。只打印非敏感信息，绝不回显 token。

    python tests/check_github_auth.py
"""

from __future__ import annotations

import subprocess
import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def get_credential() -> tuple[str, str] | None:
    """从 git 凭据助手取 github.com 的账号和令牌。"""
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, timeout=60,
    )
    username = password = ""
    for line in proc.stdout.splitlines():
        if line.startswith("username="):
            username = line.split("=", 1)[1]
        elif line.startswith("password="):
            password = line.split("=", 1)[1]
    if not password:
        print("  凭据助手没有返回令牌。")
        print("  stdout:", proc.stdout[:200].replace(password, "<redacted>") if password else proc.stdout[:200])
        print("  stderr:", proc.stderr[:200])
        return None
    return username, password


def main() -> int:
    cred = get_credential()
    if not cred:
        return 1
    username, token = cred

    print(f"取到凭据：用户 {username}，令牌长度 {len(token)}，前缀 {token[:4]}…")
    print()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "daliangzi-check",
    }
    with httpx.Client(timeout=30, headers=headers) as c:
        r = c.get("https://api.github.com/user")
        if r.status_code != 200:
            print(f"  [FAIL] GET /user -> HTTP {r.status_code}")
            print("  ", r.text[:200])
            return 1
        me = r.json()
        print(f"  [ok] 身份验证通过：{me.get('login')}（{me.get('name') or '未填昵称'}）")
        print(f"       公开仓库数：{me.get('public_repos')}")

        # 检查令牌的权限范围
        scopes = r.headers.get("x-oauth-scopes", "")
        print(f"       令牌 scopes：{scopes or '（未列出，可能是细粒度令牌）'}")

        # 能不能建仓库，看权限即可，不真建
        can_create = "repo" in scopes or "public_repo" in scopes or not scopes
        print(f"       能否创建仓库：{'看起来可以' if can_create else 'scope 里没有 repo，可能不行'}")

        # 列出已有仓库里名字带 daliangzi / 大量子 的，避免重名
        r2 = c.get("https://api.github.com/user/repos", params={"per_page": 100, "sort": "updated"})
        if r2.status_code == 200:
            names = [x["name"] for x in r2.json()]
            hits = [n for n in names if "daliangzi" in n.lower() or "daliangzi" in n.lower()]
            print(f"       最近 100 个仓库里相关的：{hits or '无'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
