"""大量子 —— 启动入口。

    python run.py              # 启动网页工具
    python run.py --open       # 启动并自动打开浏览器
    python run.py --port 8765  # 指定端口
    python run.py --check      # 只做自检，不起服务

Windows 上双击 `启动.bat` 即可，等价于 `python run.py --open`。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Windows 控制台默认不是 UTF-8，中文会糊成乱码
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def self_check() -> int:
    """起服务之前先自检：依赖、提示词、导入链路。"""
    problems = 0

    print("大量子 自检")
    print("-" * 46)

    try:
        import flask  # noqa: F401
        import httpx  # noqa: F401
        print("[ok]   依赖 flask / httpx")
    except ImportError as exc:
        print(f"[FAIL] 缺少依赖：{exc}")
        problems += 1

    from daliangzi.config import Config, ensure_dirs

    ensure_dirs()
    print("[ok]   数据目录就绪")

    cfg = Config.load()
    if cfg.has_key:
        print(f"[ok]   API Key 已配置：{cfg.masked_key()}")
    else:
        print("[warn] 还没配置 DeepSeek API Key（启动后在网页里填）")

    try:
        from daliangzi.prompts_loader import list_prompts

        prompts = list_prompts()
        print(f"[ok]   提示词 {len(prompts)} 个：" + "、".join(p["name"] for p in prompts))
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 提示词加载失败：{exc}")
        problems += 1

    try:
        from daliangzi.ingest.parse import load_from_text, records_to_comments

        sample = 'content,like_count\n"这家店服务太差了，服务员爱答不理",12\n"味道还行就是太贵",3\n'
        result = load_from_text(sample, "test.csv")
        clean = records_to_comments(result.records, result.mapping)
        assert len(clean.comments) == 2, clean.summary()
        print("[ok]   解析与清洗链路正常")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 解析链路异常：{exc}")
        problems += 1

    try:
        from daliangzi.web.server import create_app

        app = create_app()
        routes = [r.rule for r in app.url_map.iter_rules() if r.rule.startswith("/api")]
        print(f"[ok]   Web 服务可创建，{len(routes)} 个 API 路由")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] Web 服务创建失败：{exc}")
        problems += 1

    print("-" * 46)
    print("自检通过，可以启动。" if problems == 0 else f"有 {problems} 项问题需要处理。")
    return problems


def is_already_running(url: str, timeout: float = 1.5) -> bool:
    """这个端口上是不是已经跑着一个「大量子」。

    只认自家 /api/status 的字段形状，所以别的程序占了端口不会被误判成
    「已经在运行」—— 那种情况应该走正常的启动失败路径。
    """
    import json
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{url}/api/status", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return isinstance(data, dict) and "stages" in data and "stage_labels" in data


def open_browser_when_ready(url: str, host: str, port: int, timeout: float = 30.0) -> None:
    """后台线程：等端口真的能连上，再打开浏览器。

    直接 open 会撞上「服务还没起来」的白页，固定 sleep 几秒在慢机器上又不保险，
    所以这里真的去连一下端口。
    """
    import socket
    import threading
    import time
    import webbrowser

    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host

    def _wait() -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((probe_host, port), timeout=0.3):
                    webbrowser.open(url)
                    return
            except OSError:
                time.sleep(0.2)

    threading.Thread(target=_wait, daemon=True, name="open-browser").start()


def check_port(host: str, port: int) -> str | None:
    """先自己绑一次端口，绑不上就返回错误说明。

    Flask 在 bind 失败时只会吐一句「以一种访问权限不允许的方式做了一个访问套接字的尝试」，
    而且那句「已启动」已经先印出去了 —— 报错和事实正好相反。所以这里提前探一次。
    """
    import socket

    probe_host = host or "0.0.0.0"
    family = socket.AF_INET6 if ":" in probe_host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.bind((probe_host, port))
    except OSError as exc:
        return str(exc)
    finally:
        sock.close()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="大量子 —— 网络观点分析工具")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--check", action="store_true", help="只做自检，不启服务")
    parser.add_argument("--open", action="store_true", help="起服务后自动打开浏览器")
    args = parser.parse_args()

    if args.check:
        return self_check()

    url = f"http://{args.host}:{args.port}"

    # 已经开着一个了就别再启第二个（端口会撞，报一串 traceback 很难看）。
    if is_already_running(url):
        print(f"\n  大量子已经在运行了 →  {url}")
        print("  要重启的话，先关掉原来那个窗口（Ctrl+C）。\n")
        if args.open:
            import webbrowser

            webbrowser.open(url)
        return 0

    if self_check() != 0:
        print("\n自检未通过。加 --check 可单独运行自检。")
        return 1

    bind_error = check_port(args.host, args.port)
    if bind_error:
        print(f"\n  {args.host}:{args.port} 绑不上：{bind_error}")
        print("  多半是已经被别的程序占着了。换个端口再试：")
        print(f"    python run.py --port {args.port + 1}")
        print("  如果占着它的就是另一个「大量子」，直接用它就行，不用再起一个。\n")
        return 1

    from daliangzi.web.server import create_app

    app = create_app()
    print()
    print(f"  大量子已启动 →  {url}")
    print("  按 Ctrl+C 停止")
    print()

    if args.open:
        open_browser_when_ready(url, args.host, args.port)

    try:
        app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
