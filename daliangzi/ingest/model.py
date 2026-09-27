"""评论数据模型。

所有采集来源最终都要归一成 Comment。管道下游只认这个结构。
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Comment:
    id: str = ""
    text: str = ""
    likes: int = 0
    platform: str = ""
    author: str = ""
    created_at: str = ""
    url: str = ""
    parent_id: str = ""
    reply_to: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = make_id(self.text, self.author, self.platform)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def short(self) -> str:
        text = self.text.replace("\n", " ")
        return text if len(text) <= 60 else text[:60] + "…"


def make_id(text: str, author: str = "", platform: str = "") -> str:
    """稳定 ID。同样的文本+作者+平台，无论跑多少次都是同一个 ID。

    这一点很重要：stage1 的产物要能跨运行复用，ID 不稳定就复用不了。
    """
    raw = f"{platform}\x00{author}\x00{text}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class Label:
    """从单条评论里提炼出来的一个观点。

    注意主键是 **opinion（观点）**，不是 term（标签词）。
    标签词只是这一派常说的圈内术语，用来给类别增加质感，
    它可能是空的 —— 一条评论完全不用黑话也照样有观点。
    """

    opinion: str = ""      # 标准化的观点短句 —— 统计主键
    stance: str = ""       # 支持 / 反对 / 中立 / 其他
    target: str = ""       # 针对谁
    term: str = ""         # 圈内标签词（可选，可为空）
    evidence: str = ""     # 原文片段

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Label":
        # 兼容旧格式：早期版本用 term 当主键、claim 当主张。
        opinion = str(d.get("opinion") or d.get("claim") or "").strip()
        term = str(d.get("term") or "").strip()
        # 旧格式里 term 就是主键，claim 是主张 —— 迁移时把 term 当观点
        if not d.get("opinion") and not d.get("claim") and term:
            opinion, term = term, ""
        return cls(
            opinion=opinion,
            stance=str(d.get("stance") or "").strip(),
            target=str(d.get("target") or "").strip(),
            term=term,
            evidence=str(d.get("evidence") or "").strip(),
        )


@dataclass
class Stance:
    """合并后的一个立场类别。"""

    canonical: str                  # 类别名
    core_logic: str = ""            # 这一类在主张什么
    aliases: list[str] = field(default_factory=list)   # 它吞并了哪些原始观点
    pole: str = ""                  # 站在争论轴的哪一边
    count: int = 0                  # 条数（确定性算出来的）
    pct: float = 0.0                # 占比
    weighted_count: float = 0.0     # 按点赞加权
    weighted_pct: float = 0.0
    evidence: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)   # 这一派常说的圈内标签词
    x: float | None = None          # 坐标轴位置 0~1
    # 轴位是算出来的，不是模型直接给的。这两个是计算依据，保留下来便于追溯。
    left_affinity: float | None = None
    right_affinity: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["share"] = self.__dict__.get("share", 0.0)
        return d


@dataclass
class Axis:
    """立场坐标轴。"""

    name: str = ""
    left_pole: str = ""
    left_desc: str = ""
    right_pole: str = ""
    right_desc: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
