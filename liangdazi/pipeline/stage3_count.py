"""阶段三：确定性统计。

**这一步没有 LLM。** 大模型数数不准，让它「统计每个类别多少条」它会给你一个
看起来合理但编出来的数字。所以：LLM 只负责给评论打标签，计数全部在这里用
Python 完成。这样占比一定自洽，也一定能回溯到具体评论。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable

from ..ingest.model import Comment, Stance
from .stage1_labels import LabelResult
from .stage2_canon import CanonResult


@dataclass
class StatsResult:
    stances: list[Stance] = field(default_factory=list)
    total_comments: int = 0
    armed_comments: int = 0        # 捞到至少一个标签的评论数
    unarmed_comments: int = 0      # 完全没捞到标签的
    total_assignments: int = 0     # 标签归属总数（一条评论多个标签算多次）
    multi_label_comments: int = 0  # 一条评论带多个标签的条数
    extra: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "stances": [s.to_dict() for s in self.stances],
            "total_comments": self.total_comments,
            "armed_comments": self.armed_comments,
            "unarmed_comments": self.unarmed_comments,
            "total_assignments": self.total_assignments,
            "multi_label_comments": self.multi_label_comments,
            "extra": self.extra,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StatsResult":
        stances = []
        for raw in d.get("stances") or []:
            stance = Stance(
                canonical=raw.get("canonical", ""),
                core_logic=raw.get("core_logic", ""),
                aliases=list(raw.get("aliases") or []),
                pole=raw.get("pole", ""),
                count=int(raw.get("count") or 0),
                pct=float(raw.get("pct") or 0.0),
                weighted_count=float(raw.get("weighted_count") or 0.0),
                weighted_pct=float(raw.get("weighted_pct") or 0.0),
                evidence=list(raw.get("evidence") or []),
                terms=list(raw.get("terms") or []),
                x=raw.get("x"),
                left_affinity=raw.get("left_affinity"),
                right_affinity=raw.get("right_affinity"),
            )
            stances.append(stance)
        result = cls(
            stances=stances,
            total_comments=int(d.get("total_comments") or 0),
            armed_comments=int(d.get("armed_comments") or 0),
            unarmed_comments=int(d.get("unarmed_comments") or 0),
            total_assignments=int(d.get("total_assignments") or 0),
            multi_label_comments=int(d.get("multi_label_comments") or 0),
            extra=dict(d.get("extra") or {}),
            notes=list(d.get("notes") or []),
        )
        # 构成占比是算出来的，反序列化时要还原
        for stance, raw in zip(result.stances, d.get("stances") or []):
            stance.__dict__["share"] = float(raw.get("share") or 0.0)
        return result


def count_stances(
    comments: list[Comment],
    label_result: LabelResult,
    canon: CanonResult,
    *,
    progress: Callable[[str, float], None] | None = None,
) -> StatsResult:
    """把评论按别名映射表归到立场类别，然后数数。"""
    result = StatsResult()
    result.total_comments = len(comments)
    if not comments:
        return result

    alias_map = canon.alias_map
    counts: dict[str, int] = defaultdict(int)
    weighted: dict[str, float] = defaultdict(float)
    terms_by_stance: dict[str, Counter] = defaultdict(Counter)

    armed = 0
    multi = 0
    total_assignments = 0

    for comment in comments:
        labels = label_result.labels.get(comment.id) or []
        hit: set[str] = set()
        terms_hit: dict[str, list[str]] = defaultdict(list)
        for label in labels:
            # 主键是观点；标签词只作为这一派常说的词被汇总
            canonical = alias_map.get(label.opinion.strip())
            if canonical:
                hit.add(canonical)
                if label.term:
                    terms_hit[canonical].append(label.term)
                if label.opinion in canon.alias_map:
                    pass
        # 旧数据兼容：万一 opinion 为空但 term 命中，也认
        if not hit:
            for label in labels:
                term = (label.term or "").strip()
                canonical = alias_map.get(term)
                if canonical:
                    hit.add(canonical)
                    terms_hit[canonical].append(term)

        if not labels:
            continue
        armed += 1
        if len(hit) > 1:
            multi += 1

        # 一条评论对同一个类别只算一次，避免刷屏词把权重刷高
        for canonical in hit:
            counts[canonical] += 1
            weighted[canonical] += max(0, comment.likes)
            total_assignments += 1
            for t in terms_hit.get(canonical, []):
                terms_by_stance[canonical][t] += 1

    result.armed_comments = armed
    result.unarmed_comments = len(comments) - armed
    result.total_assignments = total_assignments
    result.multi_label_comments = multi

    total = len(comments)
    total_weight = sum(max(0, c.likes) for c in comments) or 1

    stances: list[Stance] = []
    for stance in canon.stances:
        count = counts.get(stance.canonical, 0)
        w = weighted.get(stance.canonical, 0.0)
        # 圈内词按实际出现次数排序，模型给的那几个作为兜底
        observed = [t for t, _ in terms_by_stance[stance.canonical].most_common(10)]
        merged_terms = observed + [t for t in stance.terms if t not in observed]
        updated = Stance(
            canonical=stance.canonical,
            core_logic=stance.core_logic,
            aliases=list(stance.aliases),
            pole=stance.pole,
            count=count,
            # 口径一：占全部评论的百分比（「有多少比例的评论持有这一观点」）
            pct=round(100.0 * count / total, 1) if total else 0.0,
            weighted_count=round(w, 1),
            weighted_pct=round(100.0 * w / total_weight, 1),
            evidence=list(stance.evidence),
            terms=merged_terms[:10],
        )
        stances.append(updated)

    stances.sort(key=lambda s: (-s.count, s.canonical))
    result.stances = stances

    # 构成占比：在所有标签归属里的份额，这个加起来正好 100%
    if total_assignments:
        for stance in stances:
            stance_share = round(100.0 * stance.count / total_assignments, 1)
            stance.__dict__["share"] = stance_share
    for stance in stances:
        stance.__dict__.setdefault("share", 0.0)

    result.extra = {
        "total_comments": total,
        "total_assignments": total_assignments,
        "armed": armed,
        "unarmed": result.unarmed_comments,
        "multi_label": multi,
        "unarmed_pct": round(100.0 * result.unarmed_comments / total, 1) if total else 0.0,
    }

    # 如实汇报prompt可能的问题
    if total and result.unarmed_comments / total > 0.25:
        result.notes.append(
            f"有 {result.unarmed_comments} 条评论（{result.extra['unarmed_pct']}%）没有捞到任何标签。"
            "比例偏高，说明这些评论可能是纯情绪、纯提问，或者提示词需要调整。"
        )
    if multi > total * 0.5:
        result.notes.append(
            f"超过一半的评论（{multi} 条）带有多个立场标签，「占比」之和会明显超过 100%，"
            "这是正常的 —— 说明很多人同时持有多个立场。"
        )
    if total_assignments and total and total_assignments / total > 1.5:
        result.notes.append(
            "平均每条评论携带的标签数较高，建议结合「构成占比」而不是「条数占比」来看。"
        )

    if progress:
        top = stances[0].canonical if stances else "（无）"
        progress(f"统计完成，最大立场：「{top}」", 0.80)
    return result
