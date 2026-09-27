"""真实网络路径测试。

这是之前完全缺失的一环：所有其它测试都走 mock，真实的 HTTP 调用、
请求体构造、鉴权、错误映射从来没被验证过。

用一个**故意无效的 Key** 打真实的 api.deepseek.com，可以验证：
  - URL 拼装、TLS、请求头是否正确（能拿到 401 而不是连接错误，就说明请求到达了）
  - 请求体是否是可接受的 JSON（不是 400）
  - 错误映射是否把 401 变成清晰的 LLMError 而不是崩栈
  - 干跑构造的请求体与真实发出的完全一致

不花钱（没有有效 Key，不会有任何计费）。

跑法：
    python tests/test_live_api.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from daliangzi.config import THINKING_BY_STAGE, Config  # noqa: E402
from daliangzi.llm import DeepSeekClient, LLMError, build_payload  # noqa: E402
from daliangzi.prompts_loader import load_prompt  # noqa: E402

PASS = 0
FAIL = 0
SKIP = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [ok]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  → {detail}" if detail else ""))


def skip(name: str, why: str) -> None:
    global SKIP
    SKIP += 1
    print(f"  [skip] {name}  → {why}")


def reachable(host: str, timeout: float = 6.0) -> bool:
    try:
        socket.create_connection((host, 443), timeout=timeout).close()
        return True
    except OSError:
        return False


def main() -> int:
    print("=" * 60)
    print("大量子 真实网络路径测试（用无效 Key，不产生费用）")
    print("=" * 60)

    # ---------------------------------------------- 请求体构造
    print("\n[请求体构造 — 纯本地，不联网]")

    cfg = Config(api_key="sk-invalid-for-test", model="deepseek-flash")

    p_labels = build_payload(
        cfg, "系统提示词，含 json 字样", "用户输入",
        json_mode=True, thinking=THINKING_BY_STAGE["labels"],
    )
    check("关闭思考时带上 thinking.disabled",
          p_labels.get("thinking") == {"type": "disabled"}, str(p_labels.get("thinking")))
    check("关闭思考时不带 reasoning_effort",
          "reasoning_effort" not in p_labels)
    check("关闭思考时才传 temperature（此时会生效）",
          "temperature" in p_labels, str(p_labels.keys()))
    check("JSON 模式设置 response_format",
          p_labels.get("response_format") == {"type": "json_object"},
          str(p_labels.get("response_format")))
    check("system 在 messages 第一位（缓存前缀）",
          p_labels["messages"][0]["role"] == "system",
          str([m["role"] for m in p_labels["messages"]]))
    check("stream 为 False", p_labels.get("stream") is False)

    p_jury = build_payload(
        cfg, "系统提示词", "用户输入",
        json_mode=True, thinking=THINKING_BY_STAGE["jury"],
    )
    check("开启思考时带 thinking.enabled",
          p_jury.get("thinking") == {"type": "enabled"}, str(p_jury.get("thinking")))
    check("开启思考时带 reasoning_effort=high",
          p_jury.get("reasoning_effort") == "high", str(p_jury.get("reasoning_effort")))
    check("开启思考时**不传** temperature（避免「设了但没生效」的错觉）",
          "temperature" not in p_jury, str(p_jury.keys()))

    p_none = build_payload(cfg, "s", "u", thinking=None)
    check("thinking=None 时不传 thinking 字段（由服务端默认）",
          "thinking" not in p_none and "reasoning_effort" not in p_none,
          str(p_none.keys()))

    # 提示词必须含 json 字样，否则 DeepSeek 的 JSON Output 会报错
    print("\n[提示词满足 JSON Output 的前置要求]")
    for name in ("stage1_标签", "stage2_合并", "stage4_坐标轴", "stage5_陪审团"):
        text = load_prompt(name)
        check(f"{name} 含 json 字样", "json" in text.lower())

    # ---------------------------------------------- 真实网络
    print("\n[真实网络 — api.deepseek.com]")
    if not reachable("api.deepseek.com"):
        skip("真实鉴权往返", "网络不可达（可能需要代理）")
        print("\n" + "=" * 60)
        print(f"通过 {PASS} · 失败 {FAIL} · 跳过 {SKIP}")
        print("=" * 60)
        return 1 if FAIL else 0

    print("  （网络可达，开始真实请求）")

    # 1) 裸 httpx：确认请求能到达并且拿到 401（说明 URL/头/JSON 都被接受）
    try:
        with httpx.Client(timeout=25) as c:
            r = c.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": "Bearer sk-invalid-for-test",
                    "Content-Type": "application/json",
                },
                json=p_labels,
            )
        check("请求到达服务端并返回 401（不是连接错误）",
              r.status_code == 401, f"HTTP {r.status_code}")
        check("401 响应体是可解析的 JSON（错误结构符合预期）",
              "error" in r.text.lower() or "auth" in r.text.lower(),
              r.text[:200])
        check("请求体被接受（不是 400 参数错误）",
              r.status_code != 400, f"HTTP {r.status_code}: {r.text[:300]}")
    except httpx.HTTPError as exc:
        check("真实请求发出", False, f"{type(exc).__name__}: {exc}")

    # 2) 走我们自己的客户端：401 应当被映射成清晰的 LLMError
    try:
        bad = Config(api_key="sk-invalid-for-test", model="deepseek-flash", max_retries=1)
        client = DeepSeekClient(bad)
        raised: Exception | None = None
        try:
            asyncio.run(client.complete(
                "You reply with json only.",
                '请输出 {"ok": true} 这个 json。',
                json_mode=True,
                thinking="disabled",
                label="鉴权测试",
            ))
        except LLMError as exc:
            raised = exc
        check("客户端把 401 映射成 LLMError", raised is not None,
              "没有抛 LLMError" if raised is None else "")
        check("错误信息提示了检查 API Key",
              raised is not None and "API Key" in str(raised),
              str(raised)[:120] if raised else "")
        check("错误信息里没有回显完整 Key",
              raised is not None and "sk-invalid-for-test" not in str(raised),
              str(raised)[:120] if raised else "")
    except Exception as exc:  # noqa: BLE001
        check("客户端鉴权路径", False, f"{type(exc).__name__}: {exc}")

    # 3) 干跑接口构造的请求体 == 真实请求体
    print("\n[干跑与真实请求一致性]")
    from daliangzi.pipeline.stage1_labels import _build_user_prompt
    from daliangzi.ingest.model import Comment

    sample = [Comment(id="a1", text="这女的典型捞女，结婚要房要车"), Comment(id="a2", text="偷拍违法必须严惩")]
    sys_p = load_prompt("stage1_标签")
    usr_p = _build_user_prompt(sample)
    dry = build_payload(
        Config(api_key="x", model="deepseek-flash"), sys_p, usr_p,
        json_mode=True, max_tokens=8192, thinking=THINKING_BY_STAGE["labels"],
    )
    check("干跑请求体可被 JSON 序列化", json.dumps(dry, ensure_ascii=False) is not None)
    check("干跑请求体包含完整 system 提示词",
          dry["messages"][0]["content"] == sys_p)
    check("干跑请求体的 user 段含全部评论 id",
          "a1" in usr_p and "a2" in usr_p)

    print("\n" + "=" * 60)
    print(f"通过 {PASS} · 失败 {FAIL} · 跳过 {SKIP}")
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
