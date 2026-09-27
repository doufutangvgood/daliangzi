"""阶段二：观点归纳。

「大量子」的灵魂一步。输入不是评论，是**去重后的观点清单** ——
每条评论提炼出的一句标准化观点，加上它出现的次数、倾向分布、代表原文。

注意这里聚类的是**观点**，不是标签词。评论区的价值在于人们在主张什么，
不在于他们用了哪些圈内术语。标签词只作为「这一派常说的词」附带展示。

给每个观点附上代表原文很重要：只看观点短句，「男版形象缺乏辨识度」和
「男版形象像其他角色」该不该合并很难判断；看了原文就清楚了。
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable

from ..config import THINKING_BY_STAGE, Config
from ..ingest.model import Comment, Label, Stance
from ..llm import DeepSeekClient, TruncatedError, run_sync
from ..prompts_loader import load_prompt
from .stage1_labels import LabelResult

# 一次喂给模型的观点上限。
#
# 关掉思考模式之后，一次调用装得下很多观点（输入走 1M 上下文，
# 输出只要 budget 给够就不截断）。**能一次合完就一次合完** ——
# 分两轮会丢东西：观点在 A 组和 B 组各出现一次时，两轮之间没有机会合并，
# 而第二轮只回抄「中间类别名」，漏掉的中间类别会让整片观点掉进兜底桶。
# 所以这个值故意给得大，真截断了 _merge_adaptive 还会自动拆半。
MAX_OPINIONS_PER_CALL = 1400
MIN_OPINIONS_PER_CALL = 25      # 拆到这个规模还失败就不再拆了
MAX_SPLIT_DEPTH = 4
EVIDENCE_PER_OPINION = 3
TERMS_PER_OPINION = 4

# 最终立场数的上限。
#
# 只喂去重后的观点时，模型很容易**过度拆分** —— 实测 936 个观点会拆出 32 个类别，
# 其中「批评男版形象缺乏辨识度」「批评男版形象是小圈子产物」这类本该是一类。
# 一份「立场一览」有三十多条没人读得下去。
# 所以最后再压一道：只喂类别（几十条），很便宜，目标是压到能读的数量。
MAX_FINAL_STANCES = 16
CONSOLIDATE_ROUNDS = 2


@dataclass
class OpinionStat:
    """一个去重后的观点，以及它的统计。"""

    opinion: str
    count: int = 0
    stances: Counter = field(default_factory=Counter)
    targets: Counter = field(default_factory=Counter)
    terms: Counter = field(default_factory=Counter)
    evidences: list[str] = field(default_factory=list)
    weight: int = 0                     # 点赞加权，用于挑代表原文

    def to_prompt_line(self) -> str:
        stance_desc = "、".join(f"{n}{c}" for n, c in self.stances.most_common(3)) or "?"
        term_desc = "、".join(t for t, _ in self.terms.most_common(TERMS_PER_OPINION))
        evidence = " / ".join(self.evidences[:EVIDENCE_PER_OPINION]) or "（无）"
        line = f"{self.opinion} ({self.count}次) 倾向:{stance_desc}"
        if term_desc:
            line += f" 圈内词:{term_desc}"
        return line + f" | 代表: {evidence}"


@dataclass
class CanonResult:
    stances: list[Stance] = field(default_factory=list)
    alias_map: dict[str, str] = field(default_factory=dict)   # 原始观点 -> 类别名
    opinion_stats: list[OpinionStat] = field(default_factory=list)
    merge_notes: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "stances": [s.to_dict() for s in self.stances],
            "alias_map": self.alias_map,
            "opinion_stats": [
                {
                    "opinion": o.opinion,
                    "count": o.count,
                    "stances": dict(o.stances),
                    "targets": dict(o.targets),
                    "terms": dict(o.terms),
                    "evidences": o.evidences,
                }
                for o in self.opinion_stats
            ],
            "merge_notes": self.merge_notes,
            "notes": self.notes,
        }


def build_opinion_stats(
    comments: list[Comment],
    label_result: LabelResult,
) -> list[OpinionStat]:
    """把「评论 → 观点」的映射反转成「观点 → 统计」。"""
    by_id = {c.id: c for c in comments}
    stats: dict[str, OpinionStat] = {}

    for cid, labels in label_result.labels.items():
        comment = by_id.get(cid)
        if comment is None:
            continue
        # 同一条评论里同一个观点只算一次，避免刷屏的评论把权重刷高
        seen: set[str] = set()

        for label in labels:
            opinion = label.opinion.strip()
            if not opinion or opinion in seen:
                continue
            seen.add(opinion)

            stat = stats.get(opinion)
            if stat is None:
                stat = OpinionStat(opinion=opinion)
                stats[opinion] = stat

            stat.count += 1
            stat.weight += comment.likes
            if label.stance:
                stat.stances[label.stance] += 1
            if label.target:
                stat.targets[label.target] += 1
            if label.term:
                stat.terms[label.term] += 1

            snippet = (label.evidence or comment.text).strip().replace("\n", " ")
            if len(snippet) > 60:
                snippet = snippet[:60] + "…"
            if snippet and snippet not in stat.evidences:
                # 优先保留点赞高的评论作为代表
                if len(stat.evidences) < EVIDENCE_PER_OPINION:
                    stat.evidences.append(snippet)
                elif comment.likes > 0:
                    stat.evidences[-1] = snippet

    return sorted(stats.values(), key=lambda s: (-s.count, s.opinion))


def _parse_stances(data) -> tuple[list[Stance], str]:
    raw_list = []
    if isinstance(data, dict):
        for key in ("stances", "categories", "clusters", "classes", "groups"):
            if isinstance(data.get(key), list):
                raw_list = data[key]
                break
    elif isinstance(data, list):
        raw_list = data

    stances: list[Stance] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        canonical = str(
            item.get("canonical") or item.get("name") or item.get("category") or ""
        ).strip()
        if not canonical:
            continue
        aliases_raw = item.get("aliases") or item.get("opinions") or item.get("terms") or []
        aliases = [str(a).strip() for a in aliases_raw if str(a).strip()]
        terms_raw = item.get("terms") or item.get("slang") or []
        terms = [str(t).strip() for t in terms_raw if str(t).strip()]
        stances.append(
            Stance(
                canonical=canonical,
                core_logic=str(item.get("core_logic") or item.get("logic") or "").strip(),
                aliases=aliases,
                pole=str(item.get("pole") or "").strip(),
                terms=terms,
            )
        )

    notes = ""
    if isinstance(data, dict):
        notes = str(data.get("merge_notes") or data.get("notes") or "").strip()
    return stances, notes


def _render_inventory(stats: list[OpinionStat]) -> str:
    return "\n".join(s.to_prompt_line() for s in stats)


def _consolidate_indexed(
    stances: list[Stance],
    *,
    event_name: str,
    counts: dict[str, int],
    client: DeepSeekClient,
    label: str = "压缩",
) -> tuple[list[Stance], str, list[str]]:
    """把过细的类别压缩成能读的数量。

    **按编号合并，不按类别名回抄。** 这是关键 —— 早先让模型原样回抄类别名，
    名字只要有一个字对不上，`别名→类别` 的映射就断了，那一整片观点会掉进兜底桶
    （实测兜底桶因此从 1.6% 反弹到 18%）。用编号则是纯机械映射，
    而且可以程序化校验覆盖度，从根上不可能丢。
    """
    system = load_prompt("stage2_压缩")

    inventory = "\n".join(
        f"[{i}] {s.canonical} ({counts.get(s.canonical, 0)}条)"
        + (f" 圈内词:{'、'.join(s.terms[:4])}" if s.terms else "")
        for i, s in enumerate(stances, 1)
    )
    user = (
        f"事件：{event_name or '（未命名事件）'}\n\n"
        f"当前有 {len(stances)} 个立场类别：\n\n{inventory}\n\n"
        f"请把主张相同或高度相似的类别合并，压缩到 8~{MAX_FINAL_STANCES} 个。\n\n"
        "只输出 JSON。"
    )

    res = run_sync(client.complete(
        system, user,
        label=f"语义压缩·{label}",
        max_tokens=min(32000, 2000 + len(stances) * 120),
        thinking=THINKING_BY_STAGE["canonical"],
    ))

    data = res.data if isinstance(res.data, dict) else {}
    raw = data.get("stances") or data.get("categories") or []
    notes = str(data.get("merge_notes") or "").strip()

    n = len(stances)
    out: list[Stance] = []
    covered: set[int] = set()

    for item in raw:
        if not isinstance(item, dict):
            continue
        canonical = str(item.get("canonical") or "").strip()
        if not canonical:
            continue
        members = item.get("members") or item.get("indices") or []
        idxs: list[int] = []
        for m in members:
            try:
                k = int(m)
            except (TypeError, ValueError):
                continue
            if 1 <= k <= n and k not in covered:
                idxs.append(k)
                covered.add(k)
        if not idxs:
            continue

        aliases: list[str] = []
        for k in idxs:
            for a in stances[k - 1].aliases:
                if a not in aliases:
                    aliases.append(a)
        out.append(Stance(
            canonical=canonical,
            core_logic=str(item.get("core_logic") or "").strip(),
            pole=str(item.get("pole") or "").strip(),
            aliases=aliases,
            terms=[str(t).strip() for t in (item.get("terms") or []) if str(t).strip()],
        ))

    # 兜底：模型漏掉的编号，原样保留为独立类别。宁可类别多一个，也不丢观点。
    leftovers = [k for k in range(1, n + 1) if k not in covered]
    for k in leftovers:
        src = stances[k - 1]
        out.append(Stance(
            canonical=src.canonical,
            core_logic=src.core_logic,
            pole=src.pole,
            aliases=list(src.aliases),
            terms=list(src.terms),
        ))

    warn = []
    if leftovers:
        warn.append(f"压缩时模型漏掉了 {len(leftovers)} 个类别，已原样保留，未丢观点。")
    return out, notes, warn


def _dedupe_stances(stances: list[Stance]) -> list[Stance]:
    """按类别名合并重名类别。

    「补合」那一步会把新归纳出来的类别直接接在列表后面，很容易和已有的撞名。
    重名不合并的话，列表里会出现两条一模一样的类别 —— 更糟的是统计阶段
    按类别名查计数，两条会显示成同样的数字，看起来像重复计了一遍。
    """
    merged: dict[str, Stance] = {}
    order: list[str] = []

    for stance in stances:
        key = stance.canonical.strip()
        if not key:
            continue
        target = merged.get(key)
        if target is None:
            merged[key] = Stance(
                canonical=key,
                core_logic=stance.core_logic,
                aliases=list(dict.fromkeys(stance.aliases)),
                pole=stance.pole,
                terms=list(dict.fromkeys(stance.terms)),
                evidence=list(dict.fromkeys(stance.evidence)),
            )
            order.append(key)
            continue

        for alias in stance.aliases:
            if alias not in target.aliases:
                target.aliases.append(alias)
        for term in stance.terms:
            if term not in target.terms:
                target.terms.append(term)
        for ev in stance.evidence:
            if ev not in target.evidence:
                target.evidence.append(ev)
        if not target.core_logic:
            target.core_logic = stance.core_logic
        if not target.pole:
            target.pole = stance.pole

    return [merged[k] for k in order]


def merge_labels(
    comments: list[Comment],
    label_result: LabelResult,
    cfg: Config,
    client: DeepSeekClient,
    *,
    event_name: str = "",
    progress: Callable[[str, float], None] | None = None,
) -> CanonResult:
    """把观点归纳成立场类别。"""
    result = CanonResult()
    stats = build_opinion_stats(comments, label_result)
    result.opinion_stats = stats

    if not stats:
        result.notes.append("没有提炼出任何观点，无法归纳。请检查评论内容或调整提示词。")
        return result

    if progress:
        progress(f"共 {len(stats)} 个不同的观点，开始归纳立场", 0.68)

    system = load_prompt("stage2_合并")

    if len(stats) <= MAX_OPINIONS_PER_CALL:
        stances, notes = _merge_adaptive(system, stats, event_name, client, label="归纳")
        result.stances = stances
        result.merge_notes = notes
    else:
        # 观点太多，分两轮：先分组粗合，再把粗合结果合一次
        chunks = [
            stats[i : i + MAX_OPINIONS_PER_CALL]
            for i in range(0, len(stats), MAX_OPINIONS_PER_CALL)
        ]
        if progress:
            progress(f"观点 {len(stats)} 个，先分 {len(chunks)} 组粗合", 0.68)

        mid_stances: list[Stance] = []
        for idx, chunk in enumerate(chunks):
            stances, _ = _merge_adaptive(
                system, chunk, event_name, client, label=f"粗合{idx + 1}"
            )
            mid_stances.extend(stances)
            if progress:
                progress(
                    f"粗合 {idx + 1}/{len(chunks)} 完成（累计 {len(mid_stances)} 个中间类别）",
                    0.68 + 0.10 * (idx + 1) / len(chunks),
                )

        # 把中间类别当成新的观点清单再合一次
        synth_stats = [
            OpinionStat(
                opinion=s.canonical,
                count=sum(t.count for t in stats if t.opinion in set(s.aliases)) or 1,
                stances=Counter({"综合": 1}),
            )
            for s in mid_stances
        ]
        if progress:
            progress(f"第二轮：把 {len(synth_stats)} 个中间类别合成最终立场", 0.79)

        final, notes = _merge_adaptive(
            system, synth_stats, event_name, client, label="终合"
        )

        # 覆盖度兜底。第二轮只回抄「中间类别名」，模型很容易漏掉几个 ——
        # 而一个中间类别背后是几十条观点，漏一个就是整片观点掉进兜底桶。
        # 实测这个疏漏会让「其他零散观点」膨胀到 20%+，所以必须补。
        covered = {a for s in final for a in s.aliases}
        missed = [s for s in mid_stances if s.canonical not in covered]
        if missed:
            if progress:
                progress(f"第二轮漏掉了 {len(missed)} 个中间类别，正在补合", 0.82)
            missed_stats = [
                OpinionStat(
                    opinion=s.canonical,
                    count=sum(t.count for t in stats if t.opinion in set(s.aliases)) or 1,
                    stances=Counter({"综合": 1}),
                )
                for s in missed
            ]
            try:
                extra, extra_notes = _merge_adaptive(
                    system, missed_stats, event_name, client, label="补合"
                )
                final.extend(extra)
                if extra_notes:
                    notes = "；".join(n for n in (notes, extra_notes) if n)
            except Exception as exc:  # noqa: BLE001 - 补合失败不该拖垮整轮
                notes = "；".join(n for n in (notes, f"补合失败：{exc}") if n)

        result.merge_notes = notes

        # 统一展开一次：final 里的 aliases 目前是「中间类别名」，换回原始观点。
        # 补合出来的那批也是同一套中间类别名，所以走同一个映射，不会重复展开。
        mid_map = {s.canonical: s.aliases for s in mid_stances}
        for stance in final:
            expanded: list[str] = []
            for alias in stance.aliases:
                expanded.extend(mid_map.get(alias, [alias]))
            stance.aliases = expanded
        result.stances = final

    # 建别名映射表（观点 -> 类别）
    #
    # 先按类别名去重：分轮 + 补合会产生重名类别，不去重的话列表里会出现
    # 两条一模一样的立场，统计阶段还会显示出两个相同的条数。
    before = len(result.stances)
    result.stances = _dedupe_stances(result.stances)
    if len(result.stances) < before:
        result.notes.append(
            f"合并了 {before - len(result.stances)} 个重名类别（分轮归纳时产生的重复）。"
        )

    # ---- 最终压缩 ----
    # 只喂「类别」而不是原始观点，所以这一道很便宜（几十条输入）。
    # 用编号合并，覆盖度可以程序化校验，不会丢观点。
    counts_for_consolidate = {
        s.canonical: sum(t.count for t in stats if t.opinion in set(s.aliases))
        for s in result.stances
    }

    rounds = 0
    while len(result.stances) > MAX_FINAL_STANCES and rounds < CONSOLIDATE_ROUNDS:
        rounds += 1
        if progress:
            progress(f"第 {rounds} 轮压缩：{len(result.stances)} 类 → 目标 8~{MAX_FINAL_STANCES} 类", 0.80)
        try:
            new_stances, notes, warns = _consolidate_indexed(
                result.stances,
                event_name=event_name,
                counts=counts_for_consolidate,
                client=client,
                label=str(rounds),
            )
        except Exception as exc:  # noqa: BLE001 - 压缩失败就保留上一轮结果
            result.notes.append(f"压缩失败，保留上一轮的 {len(result.stances)} 个类别：{exc}")
            break

        result.notes.extend(warns)
        if notes:
            result.merge_notes = "；".join(n for n in (result.merge_notes, notes) if n)

        new_stances = _dedupe_stances(new_stances)
        if not new_stances:
            break
        if len(new_stances) >= len(result.stances):
            # 没压下去，说明模型认为已经够精简，别硬逼
            result.notes.append(
                f"压缩后类别数没有减少（{len(new_stances)} 个），已停止 —— "
                "这个事件的立场确实比较分散。"
            )
            break

        result.stances = new_stances
        counts_for_consolidate = {
            s.canonical: sum(t.count for t in stats if t.opinion in set(s.aliases))
            for s in result.stances
        }

    alias_map: dict[str, str] = {}
    for stance in result.stances:
        for alias in stance.aliases:
            alias_map[alias] = stance.canonical

    # 兜底：模型漏掉的观点进「其他零散观点」
    known = {s.opinion for s in stats}
    unmapped = [o for o in known if o not in alias_map]
    if unmapped:
        result.notes.append(f"有 {len(unmapped)} 个观点没被归入任何类别，已放入「其他零散观点」。")
        other = next((s for s in result.stances if s.canonical == "其他零散观点"), None)
        if other is None:
            other = Stance(
                canonical="其他零散观点",
                core_logic="出现频次低、或无法归入任何主要立场的零散观点",
                pole="零散",
            )
            result.stances.append(other)
        for opinion in unmapped:
            other.aliases.append(opinion)
            alias_map[opinion] = other.canonical

    result.alias_map = alias_map

    # 确定性地收集每个类别的代表原文 + 圈内词（不靠模型生成）
    stance_evidence: dict[str, list[tuple[int, str]]] = defaultdict(list)
    stance_terms: dict[str, Counter] = defaultdict(Counter)
    for stat in stats:
        canonical = alias_map.get(stat.opinion)
        if not canonical:
            continue
        for ev in stat.evidences:
            stance_evidence[canonical].append((stat.weight, ev))
        stance_terms[canonical].update(stat.terms)

    for stance in result.stances:
        pool = sorted(stance_evidence.get(stance.canonical, []), key=lambda x: -x[0])
        seen_ev: list[str] = []
        for _w, ev in pool:
            if ev not in seen_ev:
                seen_ev.append(ev)
            if len(seen_ev) >= 6:
                break
        stance.evidence = seen_ev

        if not stance.terms:
            stance.terms = [t for t, _ in stance_terms[stance.canonical].most_common(8)]

    if progress:
        progress(f"归纳出 {len(result.stances)} 个立场类别", 0.76)
    return result


def _merge_adaptive(
    system: str,
    stats: list[OpinionStat],
    event_name: str,
    client: DeepSeekClient,
    *,
    label: str = "归纳",
    depth: int = 0,
    extra_hint: str = "",
) -> tuple[list[Stance], str]:
    """归纳一批观点。被 max_tokens 截断就自动拆半重试。

    截断是**重试解决不了**的 —— 同样的输入、同样的输出预算，只会再截断一次。
    唯一的出路是把输入拆小，让输出短到装得下。
    """
    try:
        return _merge_once(system, stats, event_name, client, label=label, extra_hint=extra_hint)
    except TruncatedError:
        if len(stats) <= MIN_OPINIONS_PER_CALL or depth >= MAX_SPLIT_DEPTH:
            raise
        mid = len(stats) // 2
        left, notes_l = _merge_adaptive(
            system, stats[:mid], event_name, client,
            label=f"{label}.{depth + 1}a", depth=depth + 1, extra_hint=extra_hint,
        )
        right, notes_r = _merge_adaptive(
            system, stats[mid:], event_name, client,
            label=f"{label}.{depth + 1}b", depth=depth + 1, extra_hint=extra_hint,
        )
        note = "；".join(n for n in (notes_l, notes_r) if n)
        return left + right, note


def _merge_once(
    system: str,
    stats: list[OpinionStat],
    event_name: str,
    client: DeepSeekClient,
    *,
    label: str = "归纳",
    extra_hint: str = "",
) -> tuple[list[Stance], str]:
    header = f"事件：{event_name or '（未命名事件）'}\n\n观点清单（共 {len(stats)} 个）：\n\n"
    user = (header + _render_inventory(stats)
            + "\n\n请把以上观点归纳成立场类别，只输出 JSON。"
            + extra_hint)
    # 输出要把所有 aliases 原样回抄，给得宽一点；真截断了还会自动拆半。
    # 注意这里必然是关闭思考模式的（见 THINKING_BY_STAGE）—— 否则思维链
    # 会把这个预算吃光，正文一个字都出不来，拆半也没用。
    # DeepSeek flash 单次输出上限 384K，所以给到 64K 是安全的。
    budget = min(64000, 2000 + len(stats) * 45)
    res = run_sync(client.complete(
        system, user,
        label=f"语义合并·{label}",
        max_tokens=budget,
        thinking=THINKING_BY_STAGE["canonical"],
    ))
    return _parse_stances(res.data)
