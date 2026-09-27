"""配置与密钥管理。

密钥优先级：环境变量 > .env 文件 > 空。
界面里填的 key 会写回 .env，不碰系统环境变量。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RUNS_DIR = DATA_DIR / "runs"
ENV_FILE = PROJECT_ROOT / ".env"

CN_TZ = timezone(timedelta(hours=8))

# 模型名。旧名 deepseek-chat / deepseek-reasoner 已下线。
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"

# 每百万 token 单价（人民币）。来源：DeepSeek 官方定价页。
# 空闲时段价格是高峰时段的一半。
PRICING = {
    "deepseek-flash": {
        "peak": {"cache_hit": 0.04, "cache_miss": 2.0, "output": 8.0},
        "off_peak": {"cache_hit": 0.02, "cache_miss": 1.0, "output": 4.0},
    },
    "deepseek-v4-pro": {
        "peak": {"cache_hit": 0.30, "cache_miss": 9.0, "output": 27.0},
        "off_peak": {"cache_hit": 0.15, "cache_miss": 4.5, "output": 13.5},
    },
}


def is_peak_now(now: datetime | None = None) -> bool:
    """当前是否处于 DeepSeek 高峰计费时段。

    高峰：北京时间周一至周五 9:00-12:00、14:00-18:00。
    其余（含周末与法定节假日）为空闲时段，价格减半。
    """
    now = now or datetime.now(CN_TZ)
    if now.weekday() >= 5:  # 周六周日
        return False
    minutes = now.hour * 60 + now.minute
    return (9 * 60 <= minutes < 12 * 60) or (14 * 60 <= minutes < 18 * 60)


# 思考模式（thinking）按阶段的开关。
#
# DeepSeek **默认打开思考模式且 effort=high**。思维链 token 按**输出价**计费，
# 而输出是最贵的一环；更要命的是它和正文**抢同一个 max_tokens 预算** ——
# 实测在阶段二上，「low」强度的思维链就能把整个预算吃光，
# finish_reason=length 而正文是空的，拆小输入也没用（每份照样被吃光）。
# 另外思考模式下 temperature 会**静默失效**。
#
# 所以判定标准是：这一步的输出里有没有**大量必须原样回抄的内容**。
# 有（阶段二要回抄几百条 aliases）→ 关掉，预算全留给正文。
# 纯粹做判断、输出很短（阶段四）→ 可以用低强度。
# 需要推理和写作（陪审团、报告）→ 保留高强度。
THINKING_BY_STAGE = {
    "labels": "disabled",    # 高并发机械抽取
    "canonical": "disabled",  # 要原样回抄几百条 aliases，思维链会吃光预算
    "axis": "low",           # 输出很短（十几个数字），低强度够用
    "jury": "high",          # 要扮演多派立场分别打分，需要推理
    "report": "high",        # 写深度评论文章，需要推理
}


def load_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """读取 .env。格式简单：KEY=VALUE，支持 # 注释。"""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def save_env_file(updates: dict[str, str], path: Path = ENV_FILE) -> None:
    """把若干键写回 .env，保留原有注释与顺序。"""
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}")
                continue
        out.append(line)

    if remaining:
        if out and out[-1].strip():
            out.append("")
        out.append("# 由大量子界面写入")
        for key, value in remaining.items():
            out.append(f"{key}={value}")

    path.write_text("\n".join(out) + "\n", encoding="utf-8")


@dataclass
class Config:
    """运行期配置。"""

    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL

    # 并发与分批
    batch_size: int = 200          # 每个请求塞多少条评论
    concurrency: int = 8           # 同时在跑的请求数
    max_retries: int = 3

    # 采样
    sample_limit: int = 0          # 0 = 不采样，全量跑

    # 生成参数
    temperature: float = 0.3       # 仅在关闭思考模式时生效
    max_tokens: int = 8192

    # 采集
    request_timeout: float = 300.0

    warnings: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Config":
        env = load_env_file()
        cfg = cls(
            api_key=env.get("DEEPSEEK_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=env.get("DEEPSEEK_BASE_URL", "") or os.environ.get("DEEPSEEK_BASE_URL", "") or DEFAULT_BASE_URL,
            model=env.get("DEEPSEEK_MODEL", "") or DEFAULT_MODEL,
        )
        for attr in ("batch_size", "concurrency", "sample_limit", "max_retries"):
            raw = env.get("DALIANGZI_" + attr.upper())
            if raw:
                try:
                    setattr(cfg, attr, int(raw))
                except ValueError:
                    pass
        return cfg

    @property
    def has_key(self) -> bool:
        return bool(self.api_key.strip())

    def price_table(self) -> dict[str, float]:
        table = PRICING.get(self.model) or PRICING[DEFAULT_MODEL]
        return table["peak" if is_peak_now() else "off_peak"]

    def cost_of(self, cache_hit_tokens: int, cache_miss_tokens: int, output_tokens: int) -> float:
        p = self.price_table()
        return (
            cache_hit_tokens / 1_000_000 * p["cache_hit"]
            + cache_miss_tokens / 1_000_000 * p["cache_miss"]
            + output_tokens / 1_000_000 * p["output"]
        )

    def masked_key(self) -> str:
        k = self.api_key.strip()
        if not k:
            return ""
        if len(k) <= 10:
            return k[:2] + "*" * (len(k) - 2)
        return f"{k[:6]}...{k[-4:]}"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
