"""阶段五：共识/撕裂点（模拟陪审团）+ 最终报告。

「共识与撕裂点」不靠模型拍脑袋，用**模拟陪审团**：
模型先提出若干命题，再扮演每一派立场的持有者分别打分。
然后由 Python 算均值和方差 —— 全员高分的是共识，方差大的是撕裂点。
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from typing import Callable

from ..config import THINKING_BY_STAGE
from ..ingest.model import Axis, Stance
from ..llm import DeepSeekClient, LLMError, run_sync
from ..prompts_loader import load_prompt

CONSENSUS_MIN = 70.0    # 所有立场都 ≥ 这个分，算共识
CLEAVAGE_STDEV = 18.0   # 标准差 ≥ 这个值，算撕裂点


@dataclass
class Proposition:
    text: str
    scores: dict[str, int] = field(default_factory=dict)
    mean: float = 0.0
    stdev: float = 0.0
    lowest: int = 0
    highest: int = 0
    kind: str = ""          # 共识 / 撕裂 / 普通

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "scores": self.scores,
            "mean": round(self.mean, 1),
            "stdev": round(self.stdev, 1),
            "lowest": self.lowest,
            "highest": self.highest,
            "kind": self.kind,
        }


@dataclass
class JuryResult:
    propositions: list[Proposition] = field(default_factory=list)
    consensus: list[Proposition] = field(default_factory=list)
    cleavage: list[Proposition] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "propositions": [p.to_dict() for p in self.propositions],
            "consensus": [p.to_dict() for p in self.consensus],
            "cleavage": [p.to_dict() for p in self.cleavage],
            "notes": self.notes,
        }


def run_jury(
    stances: list[Stance],
    *,
    event_name: str,
    client: DeepSeekClient,
    progress: Callable[[str, float], None] | None = None,
) -> JuryResult:
    result = JuryResult()
    usable = [s for s in stances if s.count > 0]
    if len(usable) < 2:
        result.notes.append("有效立场少于两个，无法组成陪审团，已跳过共识分析。")
        return result

    if progress:
        progress("模拟陪审团正在给命题打分", 0.88)

    system = load_prompt("stage5_陪审团")
    payload = [
        {"canonical": s.canonical, "core_logic": s.core_logic, "count": s.count}
        for s in usable
    ]
    user = (
        f"事件：{event_name or '（未命名事件）'}\n\n"
        f"立场类别（共 {len(payload)} 个）：\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n请提出命题并让每一派立场分别打分，只输出 JSON。"
    )

    try:
        res = run_sync(client.complete(
            system, user,
            label="陪审团",
            # 思考模式下 max_tokens 会被思维链吃掉一部分，要留余量
            max_tokens=24576,
            thinking=THINKING_BY_STAGE["jury"],
        ))
        data = res.data if isinstance(res.data, dict) else {}
        raw = data.get("propositions") or []
    except LLMError as exc:
        result.notes.append(f"陪审团打分失败，已跳过共识与撕裂点分析：{exc}")
        return result

    names = [s.canonical for s in usable]
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        raw_scores = item.get("scores")
        if not isinstance(raw_scores, dict):
            continue

        scores: dict[str, int] = {}
        for name in names:
            value = raw_scores.get(name)
            if value is None:
                continue
            try:
                scores[name] = max(0, min(100, int(round(float(value)))))
            except (TypeError, ValueError):
                continue

        if len(scores) < 2:
            continue

        values = list(scores.values())
        prop = Proposition(
            text=text,
            scores=scores,
            mean=statistics.fmean(values),
            stdev=statistics.pstdev(values) if len(values) > 1 else 0.0,
            lowest=min(values),
            highest=max(values),
        )
        if prop.lowest >= CONSENSUS_MIN:
            prop.kind = "共识"
            result.consensus.append(prop)
        elif prop.stdev >= CLEAVAGE_STDEV:
            prop.kind = "撕裂"
            result.cleavage.append(prop)
        result.propositions.append(prop)

    result.consensus.sort(key=lambda p: (-p.lowest, -p.mean))
    result.cleavage.sort(key=lambda p: -p.stdev)

    if not result.consensus:
        result.notes.append(f"没有任何命题能让所有立场都打到 {CONSENSUS_MIN:.0f} 分以上 —— 这本身就是一个结论：这场争论几乎没有共识区。")
    if not result.cleavage:
        result.notes.append("没有检测到明显的撕裂点。")

    if progress:
        progress(f"陪审团完成：{len(result.consensus)} 条共识、{len(result.cleavage)} 条撕裂点", 0.90)
    return result


def generate_report(
    *,
    event_name: str,
    axis: Axis,
    stances: list[Stance],
    jury: JuryResult,
    stats_extra: dict,
    client: DeepSeekClient,
    platform_note: str = "",
    progress: Callable[[str, float], None] | None = None,
) -> str:
    """生成最终的「立场一览」报告（Markdown）。"""
    if progress:
        progress("正在撰写立场一览报告", 0.92)

    system = load_prompt("stage5_报告")

    stance_payload = [
        {
            "canonical": s.canonical,
            "pct": s.pct,
            "count": s.count,
            "share": s.__dict__.get("share", 0.0),
            "weighted_pct": s.weighted_pct,
            "pole": s.pole,
            "core_logic": s.core_logic,
            "x": s.x,
            "aliases": s.aliases[:12],
            "典型原文": s.evidence[:4],
        }
        for s in stances
        if s.count > 0
    ]

    payload = {
        "事件名": event_name,
        "样本量": {
            "分析评论条数": stats_extra.get("total_comments", 0),
            "捞到标签的条数": stats_extra.get("armed", 0),
            "没有标签的条数": stats_extra.get("unarmed", 0),
            "标签归属总数": stats_extra.get("total_assignments", 0),
        },
        # 抽样必须告诉写报告的人，否则它会宣称分母是全部评论
        "抽样说明": (
            stats_extra.get("sampling")
            if (stats_extra.get("sampling") or {}).get("sampled")
            else "未抽样，本次分析覆盖导入的全部评论。"
        ),
        "坐标轴": axis.to_dict(),
        "立场类别": stance_payload,
        "陪审团共识": [p.to_dict() for p in jury.consensus],
        "陪审团撕裂点": [p.to_dict() for p in jury.cleavage],
        "陪审团其他命题": [
            p.to_dict() for p in jury.propositions
            if p.kind not in ("共识", "撕裂")
        ][:8],
    }

    user = (
        "以下是本次分析的全部数据。所有条数、占比、陪审团得分都已经是最终值，"
        "请严格使用，不要修改任何数字。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    if platform_note:
        user += f"\n\n补充说明：{platform_note}"
    user += "\n\n请按系统提示的结构输出 Markdown 正文。"

    res = run_sync(
        client.complete(
            system, user,
            json_mode=False,
            # 思考模式 + 长文，给足余量。max_tokens 大不会多花钱，只按实际输出计费
            max_tokens=32768,
            thinking=THINKING_BY_STAGE["report"],
            label="报告",
        )
    )
    if progress:
        progress("报告生成完成", 0.98)
    return res.text.strip()
