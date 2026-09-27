"""阶段一：逐条捞取标签。

最贵的一步，所以：
- 分批并发
- 批次按「稳定前缀 + 变化后缀」拼，吃满 DeepSeek 的缓存命中价
- 严格校验输出覆盖了输入的全部 id，防止模型偷懒合并
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from ..config import THINKING_BY_STAGE, Config
from ..ingest.model import Comment, Label
from ..llm import DeepSeekClient, LLMError, LLMResult, run_sync
from ..prompts_loader import load_prompt


@dataclass
class LabelResult:
    labels: dict[str, list[Label]] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    failed_batches: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def covered(self) -> int:
        return sum(1 for v in self.labels.values() if v)

    def to_dict(self) -> dict:
        return {
            "labels": {
                cid: [lab.to_dict() for lab in labs]
                for cid, labs in self.labels.items()
            },
            "missing": self.missing,
            "failed_batches": self.failed_batches,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LabelResult":
        labels = {
            cid: [Label.from_dict(x) for x in labs]
            for cid, labs in (d.get("labels") or {}).items()
        }
        return cls(
            labels=labels,
            missing=list(d.get("missing") or []),
            failed_batches=int(d.get("failed_batches") or 0),
            notes=list(d.get("notes") or []),
        )


def _chunk(items: list, size: int) -> list[list]:
    size = max(1, size)
    return [items[i : i + size] for i in range(0, len(items), size)]


def _build_user_prompt(comments: list[Comment]) -> str:
    """变化的这一段放最后，前面全是稳定的系统提示词。"""
    payload = [
        {"id": c.id, "text": c.text} for c in comments
    ]
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        f"以下 {len(comments)} 条评论，请逐条提取标签。"
        f"必须输出 {len(comments)} 条结果，id 与输入一一对应，一条都不能漏。\n\n"
        f"{body}"
    )


def _extract_records(data) -> list[dict]:
    """从模型输出里取出 results 数组，容忍几种常见外壳。"""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("results", "data", "items", "comments", "output"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        # 单条结果也被包了一层的情况
        if "id" in data and "labels" in data:
            return [data]
    return []


def extract_labels(
    comments: list[Comment],
    cfg: Config,
    client: DeepSeekClient,
    *,
    progress: Callable[[str, float], None] | None = None,
) -> LabelResult:
    """对每条评论捞取标签。"""
    result = LabelResult()
    if not comments:
        return result

    system = load_prompt("stage1_标签")
    batches = _chunk(comments, cfg.batch_size)
    total_batches = len(batches)

    if progress:
        progress(f"分 {total_batches} 批捞取标签（每批 {cfg.batch_size} 条，并发 {cfg.concurrency}）", 0.02)

    def _build(batch: list[Comment], index: int):
        return system, _build_user_prompt(batch)

    outcomes = run_sync(
        client.map_concurrent(
            list(enumerate(batches)),
            lambda item, _i: _build(item[1], item[0]),
            label="捞标签",
            thinking=THINKING_BY_STAGE["labels"],
        )
    )

    done = 0
    retry_ids: list[str] = []
    by_id = {c.id: c for c in comments}

    for (batch_index, batch), _res, error in outcomes:
        done += 1
        if progress:
            progress(f"标签批次 {done}/{total_batches} 完成", 0.02 + 0.6 * done / total_batches)

        if error is not None:
            result.failed_batches += 1
            result.notes.append(f"批次 {batch_index + 1} 失败：{error}")
            retry_ids.extend(c.id for c in batch)
            continue

        assert _res is not None
        records = _extract_records(_res.data)
        got: dict[str, list[Label]] = {}

        for record in records:
            cid = str(record.get("id") or "").strip()
            if not cid or cid not in by_id:
                continue
            # 新格式叫 opinions，旧格式叫 labels
            raw_items = record.get("opinions")
            if raw_items is None:
                raw_items = record.get("labels")
            labels: list[Label] = []
            if isinstance(raw_items, list):
                for item in raw_items:
                    if isinstance(item, dict):
                        label = Label.from_dict(item)
                        # 主键是观点。观点为空的记录丢掉。
                        if label.opinion:
                            labels.append(label)
            got[cid] = labels

        for comment in batch:
            if comment.id in got:
                result.labels[comment.id] = got[comment.id]
            else:
                retry_ids.append(comment.id)

    # 补漏：模型偷懒漏掉的 id，单独重跑（小批，成功率高）
    if retry_ids:
        result.notes.append(f"有 {len(retry_ids)} 条评论未被覆盖，正在补跑。")
        if progress:
            progress(f"补跑 {len(retry_ids)} 条漏掉的评论", 0.64)
        result = _retry_missing(result, retry_ids, by_id, cfg, client, system)

    for comment in comments:
        result.labels.setdefault(comment.id, [])

    if progress:
        empty = sum(1 for c in comments if not result.labels.get(c.id))
        pct = 100.0 * (len(comments) - empty) / len(comments)
        progress(f"捞标签完成：{len(comments) - empty}/{len(comments)} 条捞到标签（{pct:.0f}%）", 0.64)
    return result


def _retry_missing(
    result: LabelResult,
    retry_ids: list[str],
    by_id: dict[str, Comment],
    cfg: Config,
    client: DeepSeekClient,
    system: str,
) -> LabelResult:
    """对漏掉的评论用更小的批次重跑一次。"""
    small = max(10, cfg.batch_size // 4)
    pending = [by_id[i] for i in retry_ids if i in by_id]
    batches = _chunk(pending, small)

    def _build(batch: list[Comment], _index: int):
        return system, _build_user_prompt(batch)

    try:
        outcomes = run_sync(
            client.map_concurrent(
                list(enumerate(batches)),
                lambda item, _i: _build(item[1], item[0]),
                label="补漏",
                thinking=THINKING_BY_STAGE["labels"],
            )
        )
    except LLMError as exc:
        result.notes.append(f"补跑整体失败：{exc}")
        return result

    still_missing: list[str] = []
    for (_idx, batch), _res, error in outcomes:
        if error is not None or _res is None:
            still_missing.extend(c.id for c in batch)
            continue
        records = _extract_records(_res.data)
        found = set()
        for record in records:
            cid = str(record.get("id") or "").strip()
            if cid in by_id:
                raw = record.get("opinions")
                if raw is None:
                    raw = record.get("labels")
                labels = []
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            lab = Label.from_dict(item)
                            if lab.opinion:
                                labels.append(lab)
                result.labels[cid] = labels
                found.add(cid)
        still_missing.extend(c.id for c in batch if c.id not in found)

    if still_missing:
        for cid in still_missing:
            result.labels.setdefault(cid, [])
        result.missing = still_missing
        result.notes.append(
            f"仍有 {len(still_missing)} 条评论没能捞到标签，已按「无标签」处理。"
            "这会让占比略微偏低，但不影响其他类别的相对关系。"
        )
    return result
