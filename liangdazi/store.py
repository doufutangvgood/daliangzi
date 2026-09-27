"""运行产物持久化。

跑一次要花钱，所以每一阶段的产物都落盘，支持断点续跑：
改了提示词想重跑第二步？第一步的标签结果直接复用，不重复花钱。
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import RUNS_DIR, CN_TZ, ensure_dirs

STAGE_FILES = {
    "input": "00_input.json",
    "labels": "01_labels.json",
    "canonical": "02_canonical.json",
    "stats": "03_stats.json",
    "axis": "04_axis.json",
    "jury": "05_jury.json",
    "report": "06_report.json",
}


def _slugify(name: str, limit: int = 24) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", name).strip("-")
    return (cleaned[:limit] or "run")


def new_run_id(event_name: str) -> str:
    stamp = datetime.now(CN_TZ).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{_slugify(event_name)}-{uuid.uuid4().hex[:4]}"


class Run:
    """一次分析的运行目录。

    注意：构造时**不创建目录**。否则「查询一个不存在的 run」这个只读操作
    也会凭空造出一个空目录，把运行列表搞脏。
    目录在第一次写入时才真正创建。
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.dir = RUNS_DIR / run_id

    def _ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------- 写

    def save(self, stage: str, payload: Any) -> Path:
        self._ensure_dir()
        filename = STAGE_FILES.get(stage, f"{stage}.json")
        path = self.dir / filename
        data = _to_jsonable(payload)
        if isinstance(data, dict):
            data.setdefault("_meta", {})
            data["_meta"].update({
                "stage": stage,
                "saved_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
                "run_id": self.run_id,
            })
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)  # 原子写，避免中途崩了留下半个文件
        return path

    def save_text(self, name: str, text: str) -> Path:
        self._ensure_dir()
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    # -------------------------------------------------- 读

    def load(self, stage: str) -> Any | None:
        filename = STAGE_FILES.get(stage, f"{stage}.json")
        path = self.dir / filename
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def has(self, stage: str) -> bool:
        filename = STAGE_FILES.get(stage, f"{stage}.json")
        path = self.dir / filename
        return path.exists() and path.stat().st_size > 2

    def mtime(self, stage: str) -> float:
        filename = STAGE_FILES.get(stage, f"{stage}.json")
        path = self.dir / filename
        return path.stat().st_mtime if path.exists() else 0.0

    # -------------------------------------------------- 列表

    def summary(self) -> dict[str, Any]:
        info = self.load("input") or {}
        meta = info.get("meta") or {}
        stages = {stage: self.has(stage) for stage in STAGE_FILES}
        # input 是导入产物，不算「分析阶段」。列表里只看 6 个分析阶段。
        analysis_stages = [s for s in STAGE_FILES if s != "input"]
        return {
            "run_id": self.run_id,
            "event_name": meta.get("event_name", self.run_id),
            "platform": meta.get("platform", ""),
            "comment_count": len(info.get("comments") or []),
            "created_at": meta.get("created_at", ""),
            "stages": stages,
            "stage_done": sum(1 for s in analysis_stages if stages.get(s)),
            "stage_total": len(analysis_stages),
            "is_demo": bool(meta.get("demo")),
            "updated_at": max(
                (self.mtime(s) for s in STAGE_FILES), default=0.0
            ),
        }

    def delete(self) -> None:
        import shutil

        if self.dir.exists():
            shutil.rmtree(self.dir, ignore_errors=True)


def list_runs() -> list[dict[str, Any]]:
    ensure_dirs()
    runs = []
    for path in RUNS_DIR.iterdir():
        if path.is_dir():
            try:
                runs.append(Run(path.name).summary())
            except Exception:  # noqa: BLE001 - 坏目录不该拖垮列表
                continue
    runs.sort(key=lambda r: r.get("updated_at") or 0, reverse=True)
    return runs


def get_run(run_id: str) -> Run:
    # 防止 ../ 穿越
    safe = Path(run_id).name
    if safe != run_id:
        raise ValueError("非法的 run_id")
    return Run(run_id)


def _to_jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if is_dataclass(obj) and not isinstance(obj, type):
        return _to_jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)
