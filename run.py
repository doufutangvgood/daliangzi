"""大量子 —— 启动入口。

    python run.py              # 启动网页工具
    python run.py --port 8765  # 指定端口
    python run.py --check      # 只做自检，不起服务
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

    from liangdazi.config import Config, ensure_dirs

    ensure_dirs()
    print("[ok]   数据目录就绪")

    cfg = Config.load()
    if cfg.has_key:
        print(f"[ok]   API Key 已配置：{cfg.masked_key()}")
    else:
        print("[warn] 还没配置 DeepSeek API Key（启动后在网页里填）")

    try:
        from liangdazi.prompts_loader import list_prompts

        prompts = list_prompts()
        print(f"[ok]   提示词 {len(prompts)} 个：" + "、".join(p["name"] for p in prompts))
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 提示词加载失败：{exc}")
        problems += 1

    try:
        from liangdazi.ingest.parse import load_from_text, records_to_comments

        sample = 'content,like_count\n"这家店服务太差了，服务员爱答不理",12\n"味道还行就是太贵",3\n'
        result = load_from_text(sample, "test.csv")
        clean = records_to_comments(result.records, result.mapping)
        assert len(clean.comments) == 2, clean.summary()
        print("[ok]   解析与清洗链路正常")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 解析链路异常：{exc}")
        problems += 1

    try:
        from liangdazi.web.server import create_app

        app = create_app()
        routes = [r.rule for r in app.url_map.iter_rules() if r.rule.startswith("/api")]
        print(f"[ok]   Web 服务可创建，{len(routes)} 个 API 路由")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] Web 服务创建失败：{exc}")
        problems += 1

    print("-" * 46)
    print("自检通过，可以启动。" if problems == 0 else f"有 {problems} 项问题需要处理。")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="大量子 —— 网络观点分析工具")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--check", action="store_true", help="只做自检，不启服务")
    args = parser.parse_args()

    if args.check:
        return self_check()

    if self_check() != 0:
        print("\n自检未通过。加 --check 可单独运行自检。")
        return 1

    from liangdazi.web.server import create_app

    app = create_app()
    url = f"http://{args.host}:{args.port}"
    print()
    print(f"  大量子已启动 →  {url}")
    print("  按 Ctrl+C 停止")
    print()

    try:
        app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
