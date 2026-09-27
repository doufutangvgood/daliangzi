"""阶段四：立场坐标轴。

把各立场排到一条 0~1 的谱系上。这是「混乱粉笔」那套呈现的核心，
也是所有现成开源工具都没有的一环（它们只有饼图和嵌套树）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from ..config import THINKING_BY_STAGE
from ..ingest.model import Axis, Stance
from ..llm import DeepSeekClient, LLMError, run_sync
from ..prompts_loader import load_prompt
from .stage3_count import StatsResult


@dataclass
class AxisResult:
    axis: Axis = field(default_factory=Axis)
    stances: list[Stance] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "axis": self.axis.to_dict(),
            "stances": [s.to_dict() for s in self.stances],
            "positions": [
                {"canonical": s.canonical, "x": s.x}
                for s in self.stances
            ],
            "alignments": [
                {
                    "canonical": s.canonical,
                    "left_affinity": s.left_affinity,
                    "right_affinity": s.right_affinity,
                }
                for s in self.stances
                if s.left_affinity is not None
            ],
            "notes": self.notes,
        }


def build_axis(
    stances: list[Stance],
    *,
    event_name: str,
    client: DeepSeekClient,
    progress: Callable[[str, float], None] | None = None,
) -> AxisResult:
    result = AxisResult()
    usable = [s for s in stances if s.count > 0]
    if not usable:
        result.stances = list(stances)
        result.notes.append("没有有效立场，跳过坐标轴。")
        return result

    if progress:
        progress("正在排布立场坐标轴", 0.82)

    system = load_prompt("stage4_坐标轴")
    payload = [
        {
            "canonical": s.canonical,
            "core_logic": s.core_logic,
            "pole": s.pole,
            "count": s.count,
        }
        for s in usable
    ]
    user = (
        f"事件：{event_name or '（未命名事件）'}\n\n"
        f"立场类别（共 {len(payload)} 个）：\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n请排出立场坐标轴，只输出 JSON。"
    )

    positions: dict[str, float] = {}
    affinities: dict[str, tuple[float, float]] = {}
    try:
        res = run_sync(client.complete(
            system, user,
            label="坐标轴",
            max_tokens=8192,
            thinking=THINKING_BY_STAGE["axis"],
        ))
        data = res.data if isinstance(res.data, dict) else {}

        raw_axis = data.get("axis") if isinstance(data.get("axis"), dict) else {}
        result.axis = Axis(
            name=str(raw_axis.get("name") or "立场坐标轴").strip(),
            left_pole=str(raw_axis.get("left_pole") or "").strip(),
            left_desc=str(raw_axis.get("left_desc") or "").strip(),
            right_pole=str(raw_axis.get("right_pole") or "").strip(),
            right_desc=str(raw_axis.get("right_desc") or "").strip(),
            note=str(raw_axis.get("note") or "").strip(),
        )

        # 首选格式：模型给两极贴合度，位置由代码算 —— 这样 x 是推导出来的，
        # 可复现、可追溯，也不会因为「让模型把立场摊开」而凭空制造对立。
        for item in data.get("alignments") or []:
            if not isinstance(item, dict):
                continue
            canonical = str(item.get("canonical") or "").strip()
            if not canonical:
                continue
            left = _score(item.get("left_affinity"))
            right = _score(item.get("right_affinity"))
            if left is None or right is None:
                continue
            total = left + right
            x = 0.5 if total <= 0 else right / total
            positions[canonical] = min(1.0, max(0.0, x))
            affinities[canonical] = (left, right)

        # 兼容旧格式：模型直接给了 x（老版本提示词的产物，或模型擅自输出）
        if not positions:
            for item in data.get("positions") or []:
                if not isinstance(item, dict):
                    continue
                canonical = str(item.get("canonical") or "").strip()
                try:
                    x = float(item.get("x"))
                except (TypeError, ValueError):
                    continue
                if canonical:
                    positions[canonical] = min(1.0, max(0.0, x))
            if positions:
                result.notes.append(
                    "坐标轴用的是模型直接给的位置，不是由贴合度推导的。"
                    "建议勾选「④ 立场坐标轴」重跑一次，让位置可复现。"
                )

    except (LLMError, Exception) as exc:  # noqa: BLE001 - 坐标轴失败不该拖垮整个流程
        result.notes.append(f"坐标轴生成失败，已降级为按占比排列：{exc}")

    # 模型漏掉的类别，或整体降级：用确定性兜底
    missing = [s for s in usable if s.canonical not in positions]
    if missing:
        if result.axis.name in ("", "立场坐标轴") and not positions:
            _fallback_axis(result, usable)
            if progress:
                progress("坐标轴已用降级方案生成", 0.84)
            return result
        result.notes.append(f"{len(missing)} 个类别未被排布，已自动插空。")

    merged: list[Stance] = []
    used_x: list[float] = sorted(positions.values())
    for stance in stances:
        if stance.count == 0:
            merged.append(stance)
            continue
        x = positions.get(stance.canonical)
        if x is None:
            x = _free_slot(used_x)
            used_x.append(x)
            used_x.sort()
        stance.x = round(x, 3)
        if stance.canonical in affinities:
            stance.left_affinity, stance.right_affinity = affinities[stance.canonical]
        merged.append(stance)

    result.stances = merged
    if progress:
        progress(f"坐标轴：「{result.axis.name}」", 0.84)
    return result


def _score(value) -> float | None:
    """把模型给的贴合度解析成 0~100 的数。"""
    if value is None:
        return None
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def _free_slot(used: list[float]) -> float:
    """在一维空间里找一个离已有点最远的空位。"""
    if not used:
        return 0.5
    candidates = [0.0] + used + [1.0]
    best, best_gap = 0.5, -1.0
    for a, b in zip(candidates, candidates[1:]):
        gap = b - a
        if gap > best_gap:
            best_gap = gap
            best = (a + b) / 2
    return round(best, 3)


def _fallback_axis(result: AxisResult, stances: list[Stance]) -> None:
    """LLM 失败时的降级方案：按 pole 分组，组间均匀铺开。

    不追求准确，但要保证界面能用、顺序不荒谬。
    """
    result.axis = Axis(
        name="立场分布（自动排列）",
        left_pole="较少见立场",
        left_desc="按出现频次自动排布，未经过语义轴判断",
        right_pole="主流立场",
        right_desc="按出现频次自动排布，未经过语义轴判断",
        note="坐标轴生成失败，这是按占比自动排的降级结果，不代表真实的立场对立关系。",
    )
    # 按 pole 归组，让同 pole 的挨在一起
    groups: dict[str, list[Stance]] = {}
    for s in stances:
        groups.setdefault(s.pole or "未分类", []).append(s)

    ordered = sorted(groups.values(), key=lambda g: -sum(s.count for s in g))
    flat = [s for group in ordered for s in group]

    n = len(flat)
    for index, stance in enumerate(flat):
        stance.x = round(index / max(1, n - 1), 3) if n > 1 else 0.5
    result.stances = flat + [s for s in stances if s not in flat]
    result.notes.append("已使用降级坐标轴，建议检查 API 配置后重跑第四步。")
