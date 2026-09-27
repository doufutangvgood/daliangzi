"""DeepSeek 客户端。

自己用 httpx 打 OpenAI 兼容 REST，不引入 openai SDK。

三个要点：
1. JSON Output 模式，保证输出可解析。
2. 提示词按「稳定前缀 + 变化后缀」组织，吃满 DeepSeek 的上下文硬盘缓存
   （缓存命中输入价 0.02 元/M，未命中 1 元/M，差 50 倍）。
3. 官方承认 JSON Output 有概率返回空 content，所以空响应必须重试。
"""

from __future__ import annotations

import asyncio
import json
import random
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, TypeVar

import httpx

from .config import Config

T = TypeVar("T")

# 全进程共用的 token 计数，方便随时看花了多少钱。
_usage_lock = threading.Lock()
_usage = {"cache_hit": 0, "cache_miss": 0, "output": 0, "calls": 0, "failed": 0}


def reset_usage() -> None:
    with _usage_lock:
        for k in _usage:
            _usage[k] = 0


def get_usage() -> dict[str, int]:
    with _usage_lock:
        return dict(_usage)


def _add_usage(hit: int, miss: int, out: int) -> None:
    with _usage_lock:
        _usage["cache_hit"] += hit
        _usage["cache_miss"] += miss
        _usage["output"] += out
        _usage["calls"] += 1


def _add_failure() -> None:
    with _usage_lock:
        _usage["failed"] += 1


class LLMError(RuntimeError):
    """LLM 调用最终失败。"""


class TruncatedError(LLMError):
    """输出被 max_tokens 截断，JSON 因此不完整。

    这类失败**重试没有用** —— 同样的输入还是会被截断。
    调用方应该把输入拆小一点再来。
    """


@dataclass
class LLMResult:
    text: str
    data: Any = None
    usage: dict[str, int] = field(default_factory=dict)


def build_payload(
    cfg: Config,
    system: str,
    user: str,
    *,
    json_mode: bool = True,
    temperature: float | None = None,
    max_tokens: int | None = None,
    thinking: str | None = None,
) -> dict[str, Any]:
    """构造请求体。

    真实调用和「发出前先看」的干跑都走这一个函数，
    避免预览和实际发出去的东西不一致。
    """
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": [
            # 稳定前缀放最前，命中的就是这一段
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens or cfg.max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    # 思考模式。DeepSeek 默认是打开的（且 effort=high），必须显式关掉才省钱。
    # 注意：思考模式下 temperature 会被**静默忽略**，所以只在关掉思考时才传
    # temperature，免得给出「设了但没生效」的错觉。
    if thinking == "disabled":
        payload["thinking"] = {"type": "disabled"}
        payload["temperature"] = cfg.temperature if temperature is None else temperature
    elif thinking:
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = thinking
    else:
        payload["temperature"] = cfg.temperature if temperature is None else temperature

    return payload


class DeepSeekClient:
    """异步 DeepSeek 客户端，带并发控制、重试与用量统计。"""

    def __init__(self, cfg: Config, on_progress: Callable[[str], None] | None = None):
        if not cfg.has_key:
            raise LLMError("未配置 DeepSeek API Key。请在网页右上角「设置」里填入。")
        self.cfg = cfg
        self._on_progress = on_progress
        self._sem = asyncio.Semaphore(max(1, cfg.concurrency))

    def _log(self, message: str) -> None:
        if self._on_progress:
            self._on_progress(message)

    async def _post_once(
        self,
        client: httpx.AsyncClient,
        system: str,
        user: str,
        *,
        json_mode: bool,
        temperature: float | None,
        max_tokens: int | None,
        thinking: str | None,
    ) -> tuple[str, dict[str, int]]:
        payload = build_payload(
            self.cfg, system, user,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking=thinking,
        )

        resp = await client.post(
            f"{self.cfg.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.cfg.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if resp.status_code == 401:
            raise LLMError("DeepSeek 认证失败（401）。请检查 API Key 是否正确、是否有余额。")
        if resp.status_code == 402:
            raise LLMError("DeepSeek 余额不足（402）。请到 platform.deepseek.com 充值。")
        if resp.status_code == 429:
            raise httpx.HTTPStatusError("限流 429", request=resp.request, response=resp)
        resp.raise_for_status()

        body = resp.json()
        choice = (body.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        finish_reason = choice.get("finish_reason") or ""
        has_reasoning = bool((choice.get("message") or {}).get("reasoning_content"))

        raw_usage = body.get("usage") or {}
        usage = {
            "cache_hit": int(raw_usage.get("prompt_cache_hit_tokens") or 0),
            "cache_miss": int(raw_usage.get("prompt_cache_miss_tokens") or 0),
            "output": int(raw_usage.get("completion_tokens") or 0),
        }
        # 老接口只给 prompt_tokens，退化成全部算未命中
        if not usage["cache_hit"] and not usage["cache_miss"]:
            usage["cache_miss"] = int(raw_usage.get("prompt_tokens") or 0)
        return text, usage, finish_reason, has_reasoning

    async def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = True,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: str | None = None,
        label: str = "",
    ) -> LLMResult:
        """发一次请求，带重试。json_mode 下会把结果解析成对象。

        thinking: "disabled" 关掉思考模式；"low"/"high"/"max" 打开并指定强度；
                  None 表示不传，由服务端默认（默认是打开的且 effort=high）。
        """
        last_error: Exception | None = None

        async with self._sem:
            async with httpx.AsyncClient(timeout=self.cfg.request_timeout) as client:
                for attempt in range(self.cfg.max_retries):
                    try:
                        text, usage, finish_reason, has_reasoning = await self._post_once(
                            client, system, user,
                            json_mode=json_mode,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            thinking=thinking,
                        )
                        _add_usage(usage["cache_hit"], usage["cache_miss"], usage["output"])

                        # 官方承认 JSON Output 有概率返回空 content
                        if json_mode and not text.strip():
                            # 思考模式把 max_tokens 全吃掉时也会这样，重试无用
                            if finish_reason == "length" or has_reasoning:
                                raise TruncatedError(
                                    f"{label or '调用'} 输出预算被思维链耗尽（finish_reason={finish_reason}），"
                                    "没有产出正文。请调大 max_tokens 或关掉思考模式。"
                                )
                            raise ValueError("返回了空 content")

                        if not json_mode:
                            return LLMResult(text=text, usage=usage)

                        # 被 max_tokens 截断的 JSON 一定不完整，重试也没用 —— 直接上报，
                        # 让调用方把输入拆小。硬解析只会得到一个难懂的 JSONDecodeError。
                        if finish_reason == "length":
                            raise TruncatedError(
                                f"{label or '调用'} 输出被 max_tokens 截断（finish_reason=length），"
                                f"已生成 {usage['output']} tokens。需要把输入拆小。"
                            )

                        data = _loads_lenient(text)
                        return LLMResult(text=text, data=data, usage=usage)

                    except TruncatedError:
                        # 截断不是偶发故障，重试同一个输入只会再截断一次
                        raise
                    except LLMError:
                        raise
                    except Exception as exc:  # noqa: BLE001 - 统一重试
                        last_error = exc
                        if attempt < self.cfg.max_retries - 1:
                            backoff = min(30.0, 2.0 ** attempt) + random.uniform(0, 1.5)
                            await asyncio.sleep(backoff)

        _add_failure()
        raise LLMError(f"{label or '调用'} 重试 {self.cfg.max_retries} 次后仍失败：{last_error}")

    async def map_concurrent(
        self,
        items: Iterable[T],
        build: Callable[[T, int], tuple[str, str]],
        *,
        label: str = "",
        json_mode: bool = True,
        max_tokens: int | None = None,
        thinking: str | None = None,
    ) -> list[tuple[T, LLMResult | None, Exception | None]]:
        """并发跑一批请求，单项失败不拖垮整批。"""
        item_list = list(items)
        tasks = []
        for index, item in enumerate(item_list):
            system, user = build(item, index)
            tasks.append(
                self.complete(
                    system, user,
                    json_mode=json_mode,
                    max_tokens=max_tokens,
                    thinking=thinking,
                    label=f"{label} #{index + 1}",
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: list[tuple[T, LLMResult | None, Exception | None]] = []
        for item, res in zip(item_list, results):
            if isinstance(res, BaseException):
                out.append((item, None, res if isinstance(res, Exception) else Exception(str(res))))
            else:
                out.append((item, res, None))
        return out


def _loads_lenient(text: str) -> Any:
    """尽量把模型输出解析成 JSON。先直接解析，失败再剥 ``` 围栏。"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if text.startswith("```"):
        body = text[3:]
        if body[:4].lower() == "json":
            body = body[4:]
        end = body.rfind("```")
        if end != -1:
            body = body[:end]
        try:
            return json.loads(body.strip())
        except json.JSONDecodeError:
            pass

    # 退一步：截取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法解析为 JSON：{text[:200]}")


def run_sync(coro):
    """在同步上下文里跑异步协程。管道运行在自己的线程里，可以安全新建事件循环。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # 已经在事件循环里（不该发生），另开线程兜底
    result: dict[str, Any] = {}

    def _worker() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result["value"]
