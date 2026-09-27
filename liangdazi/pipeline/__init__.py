"""分析管道：把五个阶段串起来，并管理断点续跑。

跑一次要花钱，所以每一阶段的产物都落盘。改了第二步的提示词，
第一步已经花掉的标签结果可以直接复用。
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Callable, Iterable

from ..config import Config
from ..ingest.model import Comment
from ..llm import DeepSeekClient, get_usage
from ..prompts_loader import load_prompt
from ..store import Run
from .stage1_labels import LabelResult, extract_labels
from .stage2_canon import CanonResult, merge_labels
from .stage3_count import StatsResult, count_stances
from .stage4_axis import AxisResult, build_axis
from .stage5_report import JuryResult, generate_report, run_jury

ProgressFn = Callable[[str, float], None]

STAGE_ORDER = ["labels", "canonical", "stats", "axis", "jury", "report"]

STAGE_LABELS = {
    "labels": "① 捞标签",
    "canonical": "② 语义合并",
    "stats": "③ 统计占比",
    "axis": "④ 立场坐标轴",
    "jury": "⑤ 共识与撕裂点",
    "report": "⑥ 生成报告",
}


class AnalysisError(RuntimeError):
    """管道在某个阶段无法继续。消息要能让用户看懂该怎么办。"""


def prompt_fingerprint(name: str) -> str:
    try:
        return hashlib.sha1(load_prompt(name).encode("utf-8")).hexdigest()[:10]
    except FileNotFoundError:
        return ""


@dataclass
class AnalyzeResult:
    labels: LabelResult | None = None
    canon: CanonResult | None = None
    stats: StatsResult | None = None
    axis: AxisResult | None = None
    jury: JuryResult | None = None
    report: str = ""
    reused: list[str] = None          # type: ignore[assignment]
    recomputed: list[str] = None      # type: ignore[assignment]
    notes: list[str] = None           # type: ignore[assignment]
    sampling: dict = None             # type: ignore[assignment]
    cost: float = 0.0
    elapsed: float = 0.0

    def __post_init__(self) -> None:
        self.reused = self.reused or []
        self.recomputed = self.recomputed or []
        self.notes = self.notes or []
        self.sampling = self.sampling or {"sampled": False}


def sample_comments(
    comments: list[Comment],
    limit: int,
    *,
    seed: int = 20260101,
) -> tuple[list[Comment], dict]:
    """按上限随机抽样。

    评论量上万时，全量跑既慢又贵。抽样是必要的 —— 但**必须如实披露**，
    所以返回里带上抽样说明，最终会写进统计和报告。

    用固定种子，保证同样的输入和上限抽到同一批，重跑结果可复现。
    """
    if limit <= 0 or len(comments) <= limit:
        return comments, {"sampled": False, "total": len(comments), "used": len(comments)}

    import random

    rng = random.Random(seed)
    picked = rng.sample(comments, limit)
    # 按点赞降序展示时更像原始分布，但抽样本身是均匀的
    picked.sort(key=lambda c: -c.likes)

    return picked, {
        "sampled": True,
        "total": len(comments),
        "used": len(picked),
        "ratio": round(100.0 * len(picked) / len(comments), 1),
        "seed": seed,
        "note": (
            f"原始评论 {len(comments)} 条，按上限 {limit} 条做了**均匀随机抽样**，"
            f"实际分析 {len(picked)} 条（占 {round(100.0 * len(picked) / len(comments), 1)}%）。"
            "抽样用固定随机种子，同样输入重跑会抽到同一批。"
            "注意：这是随机抽样，不是按热度挑选，所以小众立场不会被系统性地剔除。"
        ),
    }


def analyze(
    run: Run,
    comments: list[Comment],
    cfg: Config,
    *,
    event_name: str,
    redo: Iterable[str] = (),
    stop_after: str | None = None,
    sample_limit: int | None = None,
    progress: ProgressFn | None = None,
) -> AnalyzeResult:
    """跑完整管道。redo 里的阶段强制重算，其余阶段有产物就复用。"""
    started = time.time()
    redo = set(redo)
    result = AnalyzeResult()

    def report(message: str, pct: float) -> None:
        if progress:
            progress(message, pct)

    input_payload = run.load("input") or {}
    saved_comments = input_payload.get("comments") or []
    if saved_comments and not comments:
        comments = [
            Comment(
                id=c.get("id", ""),
                text=c.get("text", ""),
                likes=int(c.get("likes") or 0),
                platform=c.get("platform", ""),
                author=c.get("author", ""),
            )
            for c in saved_comments
        ]

    # 抽样：控制成本用。抽了就要说清楚，所以结果记进 result.sampling
    effective_limit = cfg.sample_limit if sample_limit is None else sample_limit
    comments, sampling = sample_comments(comments, effective_limit)
    result.sampling = sampling
    if sampling.get("sampled"):
        report(
            f"已抽样：从 {sampling['total']} 条中随机抽 {sampling['used']} 条"
            f"（{sampling['ratio']}%）",
            0.01,
        )

    client = DeepSeekClient(cfg, on_progress=None)

    # ---------------------------------------------------------- ① 捞标签
    labels: LabelResult | None = None
    if "labels" not in redo and run.has("labels"):
        raw = run.load("labels") or {}
        labels = LabelResult.from_dict(raw)
        result.reused.append("labels")

        # 覆盖度检查。已有标签可能是**部分**的 —— 试跑只跑了 30 条、
        # 或者上次跑到一半断了。只补跑缺的那些，不重跑全部（那要重花钱）。
        covered = set(labels.labels)
        missing = [c for c in comments if c.id not in covered]
        if missing:
            report(
                f"复用已有标签（{len(covered)} 条），补跑缺失的 {len(missing)} 条",
                0.03,
            )
            extra = extract_labels(missing, cfg, client, progress=progress)
            for cid, labs in extra.labels.items():
                labels.labels[cid] = labs
            labels.missing = [m for m in labels.missing if m not in labels.labels]
            labels.notes.extend(extra.notes)
            labels.failed_batches += extra.failed_batches
            run.save("labels", {
                **labels.to_dict(),
                "prompt_fingerprint": prompt_fingerprint("stage1_标签"),
            })
        else:
            report(f"复用已有的标签结果（{len(covered)} 条，覆盖完整）", 0.05)
    else:
        report("开始捞取标签", 0.01)
        labels = extract_labels(comments, cfg, client, progress=progress)
        run.save("labels", {
            **labels.to_dict(),
            "prompt_fingerprint": prompt_fingerprint("stage1_标签"),
        })
        result.recomputed.append("labels")
    result.labels = labels

    # 失败要趁早说清楚。阶段一整批失败时，如果继续往下跑，
    # 后面每个阶段都会拿着空数据「正常」走完，最后在生成报告时才炸，
    # 用户看到的会是一个莫名其妙的晚期错误。
    armed = sum(1 for labs in labels.labels.values() if labs)
    if armed == 0:
        detail = ""
        if labels.failed_batches:
            detail = f"（{labels.failed_batches} 个批次调用失败）"
        elif labels.notes:
            detail = "（" + labels.notes[0] + "）"
        raise AnalysisError(
            "一条评论都没捞到标签" + detail + "。"
            "常见原因：API Key 无效或余额不足、网络不通、或者评论内容确实没有立场表达。"
            "可以先在「设置」里点「测试连通性」确认 Key 能用。"
        )
    if armed < max(1, len(comments)) * 0.02:
        if progress:
            progress(
                f"注意：只有 {armed}/{len(comments)} 条评论捞到了标签，比例异常低，"
                "后面的占比参考价值有限。",
                0.66,
            )

    if stop_after == "labels":
        return _finish(result, started, cfg, report)

    # ---------------------------------------------------------- ② 合并
    canon: CanonResult | None = None
    if "canonical" not in redo and run.has("canonical"):
        raw = run.load("canonical") or {}
        canon = _canon_from_dict(raw)
        result.reused.append("canonical")
        report(f"复用已有的合并结果（{len(canon.stances)} 个立场）", 0.66)
    else:
        canon = merge_labels(
            comments, labels, cfg, client, event_name=event_name, progress=progress
        )
        run.save("canonical", {
            **canon.to_dict(),
            "prompt_fingerprint": prompt_fingerprint("stage2_合并"),
        })
        result.recomputed.append("canonical")
    result.canon = canon

    if not canon.stances:
        raise AnalysisError(
            "标签合并后一个立场类别都没有。"
            "可能是阶段二返回了非法 JSON，或标签词太少无法归类。"
            "可以试试勾选「② 语义合并」重跑一次。"
        )

    if stop_after == "canonical":
        return _finish(result, started, cfg, report)

    # ---------------------------------------------------------- ③ 统计
    # 统计是纯计算，永远重算，因为它是确定性的、不花钱
    report("正在统计条数与占比", 0.78)
    stats = count_stances(comments, labels, canon, progress=None)
    if sampling.get("sampled"):
        # 抽样必须写进统计，最终会进报告 —— 读者有权知道占比是相对什么算的
        stats.extra["sampling"] = sampling
        stats.notes.append(sampling["note"])
    run.save("stats", stats.to_dict())
    result.recomputed.append("stats")
    result.stats = stats

    if stop_after == "stats":
        return _finish(result, started, cfg, report)

    # ---------------------------------------------------------- ④ 坐标轴
    axis: AxisResult | None = None
    if "axis" not in redo and run.has("axis"):
        raw = run.load("axis") or {}
        axis = AxisResult(
            axis=_axis_from_dict(raw.get("axis") or {}),
            stances=stats.stances,
            notes=list(raw.get("notes") or []),
        )
        # 用存下来的位置覆盖
        saved_x = {
            p.get("canonical"): p.get("x")
            for p in (raw.get("positions") or [])
            if isinstance(p, dict)
        }
        saved_aff = {
            a.get("canonical"): (a.get("left_affinity"), a.get("right_affinity"))
            for a in (raw.get("alignments") or [])
            if isinstance(a, dict)
        }
        for stance in axis.stances:
            if stance.canonical in saved_x:
                stance.x = saved_x[stance.canonical]
            if stance.canonical in saved_aff:
                stance.left_affinity, stance.right_affinity = saved_aff[stance.canonical]
        result.reused.append("axis")
        report("复用已有的坐标轴", 0.84)
    else:
        axis = build_axis(stats.stances, event_name=event_name, client=client, progress=progress)
        run.save("axis", {
            **axis.to_dict(),
            "prompt_fingerprint": prompt_fingerprint("stage4_坐标轴"),
        })
        result.recomputed.append("axis")
    result.axis = axis

    # 坐标轴阶段是在 stats 落盘之后跑的，x 是直接写在 Stance 对象上的。
    # 所以这里补存一次，让 03_stats.json 自身就是完整的（读回来不用再拼）。
    run.save("stats", stats.to_dict())

    if stop_after == "axis":
        return _finish(result, started, cfg, report)

    # ---------------------------------------------------------- ⑤ 陪审团
    jury: JuryResult | None = None
    if "jury" not in redo and run.has("jury"):
        jury = _jury_from_dict(run.load("jury") or {})
        result.reused.append("jury")
        report("复用已有的陪审团结果", 0.90)
    else:
        jury = run_jury(
            stats.stances, event_name=event_name, client=client, progress=progress
        )
        run.save("jury", {
            **jury.to_dict(),
            "prompt_fingerprint": prompt_fingerprint("stage5_陪审团"),
        })
        result.recomputed.append("jury")
    result.jury = jury

    if stop_after == "jury":
        return _finish(result, started, cfg, report)

    # ---------------------------------------------------------- ⑥ 报告
    if "report" not in redo and run.has("report"):
        raw = run.load("report") or {}
        result.report = str(raw.get("markdown") or "")
        result.reused.append("report")
        report("复用已有的报告", 0.99)
    else:
        if not result.report:
            markdown = generate_report(
                event_name=event_name,
                axis=axis.axis,
                stances=stats.stances,
                jury=jury,
                stats_extra=stats.extra,
                client=client,
                progress=progress,
            )
            result.report = markdown
            run.save("report", {
                "markdown": markdown,
                "prompt_fingerprint": prompt_fingerprint("stage5_报告"),
            })
            result.recomputed.append("report")

    return _finish(result, started, cfg, report)


def _finish(result: AnalyzeResult, started: float, cfg: Config, report: ProgressFn) -> AnalyzeResult:
    usage = get_usage()
    result.cost = cfg.cost_of(
        usage.get("cache_hit", 0), usage.get("cache_miss", 0), usage.get("output", 0)
    )
    result.elapsed = time.time() - started
    if result.reused:
        report(f"复用了 {len(result.reused)} 个已有阶段，省下一部分费用", 0.99)
    return result


# ---------------------------------------------------------------- 反序列化

def _canon_from_dict(raw: dict) -> CanonResult:
    from ..ingest.model import Stance

    stances = []
    for s in raw.get("stances") or []:
        stances.append(Stance(
            canonical=s.get("canonical", ""),
            core_logic=s.get("core_logic", ""),
            aliases=list(s.get("aliases") or []),
            pole=s.get("pole", ""),
            count=int(s.get("count") or 0),
            pct=float(s.get("pct") or 0.0),
            weighted_count=float(s.get("weighted_count") or 0.0),
            weighted_pct=float(s.get("weighted_pct") or 0.0),
            evidence=list(s.get("evidence") or []),
            terms=list(s.get("terms") or []),
            x=s.get("x"),
            left_affinity=s.get("left_affinity"),
            right_affinity=s.get("right_affinity"),
        ))
    canon = CanonResult(
        stances=stances,
        alias_map=dict(raw.get("alias_map") or {}),
        merge_notes=raw.get("merge_notes", ""),
        notes=list(raw.get("notes") or []),
    )
    return canon


def _axis_from_dict(raw: dict):
    from ..ingest.model import Axis

    return Axis(
        name=raw.get("name", ""),
        left_pole=raw.get("left_pole", ""),
        left_desc=raw.get("left_desc", ""),
        right_pole=raw.get("right_pole", ""),
        right_desc=raw.get("right_desc", ""),
        note=raw.get("note", ""),
    )


def _jury_from_dict(raw: dict) -> JuryResult:
    from .stage5_report import Proposition

    def _props(key: str) -> list:
        out = []
        for p in raw.get(key) or []:
            out.append(Proposition(
                text=p.get("text", ""),
                scores=dict(p.get("scores") or {}),
                mean=float(p.get("mean") or 0.0),
                stdev=float(p.get("stdev") or 0.0),
                lowest=int(p.get("lowest") or 0),
                highest=int(p.get("highest") or 0),
                kind=p.get("kind", ""),
            ))
        return out

    return JuryResult(
        propositions=_props("propositions"),
        consensus=_props("consensus"),
        cleavage=_props("cleavage"),
        notes=list(raw.get("notes") or []),
    )
