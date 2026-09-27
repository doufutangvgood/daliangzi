"""把一次 run 的完整结果导成可读报告。"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RID = sys.argv[1] if len(sys.argv) > 1 else "20260927-174925-DeepSeek-拟人形象之争-eefa"
BASE = "http://127.0.0.1:8770"
OUT = Path("data/raw/分析结果.md")

with httpx.Client(timeout=60) as c:
    d = c.get(f"{BASE}/api/runs/{RID}").json()
    lab = c.get(f"{BASE}/api/runs/{RID}/labels?limit=1").json()

L: list[str] = []
add = L.append

meta = d.get("meta") or {}
stats = d.get("stats") or {}
axis = (d.get("axis") or {}).get("axis") or {}
jury = d.get("jury") or {}
stances = stats.get("stances") or []

add(f"# DeepSeek 拟人形象之争 · 立场分析\n")
add(f"- 事件：{meta.get('event_name')}")
add(f"- 来源：{meta.get('platform')}（B站 10 个视频 + LINUX DO 讨论帖）")
add(f"- 评论：{d.get('comment_total')} 条")
add(f"- 提炼出观点：{lab.get('with_labels')} 条，"
    f"无观点：{lab.get('empty')} 条，"
    f"不同观点：{lab.get('distinct_opinions')}")
add(f"- 归纳出立场：{len(stances)} 个")
add(f"- 清洗：{d.get('clean_report')}\n")

add(f"## 坐标轴\n")
add(f"- 名称：**{axis.get('name')}**")
add(f"- 左端：{axis.get('left_pole')} —— {axis.get('left_desc')}")
add(f"- 右端：{axis.get('right_pole')} —— {axis.get('right_desc')}")
add(f"- 说明：{axis.get('note')}\n")

add(f"## 各立场（按占比）\n")
add("| # | 类别 | 条数 | 占比 | 构成 | 点赞加权 | 轴位 | 核心逻辑 |")
add("|---|---|---|---|---|---|---|---|")
for i, s in enumerate(stances, 1):
    add(f"| {i} | {s['canonical']} | {s['count']} | {s['pct']}% | {s.get('share',0)}% | "
        f"{s.get('weighted_pct',0)}% | {s.get('x')} | {s.get('core_logic','')[:56]} |")

add(f"\n## 各立场明细\n")
for i, s in enumerate(stances, 1):
    add(f"### {i}. {s['canonical']} · {s['pct']}%（{s['count']} 条）")
    add(f"{s.get('core_logic','')}")
    add(f"- 轴位：{s.get('x')}"
        + (f"（左端贴合 {s['left_affinity']}／右端贴合 {s['right_affinity']}）"
           if s.get('left_affinity') is not None else ""))
    add(f"- 点赞加权占比：{s.get('weighted_pct')}%")
    if s.get("terms"):
        add(f"- 圈内词：{'、'.join(s['terms'][:10])}")
    if s.get("aliases"):
        add(f"- 归入的观点（共 {len(s['aliases'])} 条）：")
        for a in s["aliases"][:14]:
            add(f"    - {a}")
        if len(s["aliases"]) > 14:
            add(f"    - ……另有 {len(s['aliases']) - 14} 条")
    if s.get("evidence"):
        add(f"- 典型原文：")
        for e in s["evidence"][:3]:
            add(f"    > {e}")
    add("")

add(f"## 共识与撕裂点（模拟陪审团）\n")
add(f"### 共识（所有立场都认同）\n")
for p in jury.get("consensus") or []:
    add(f"- **{p['text']}**  均值 {p['mean']}／区间 {p['lowest']}~{p['highest']}")
if not jury.get("consensus"):
    add("- （无）")

add(f"\n### 撕裂点（立场间分歧最大）\n")
for p in jury.get("cleavage") or []:
    add(f"- **{p['text']}**  均值 {p['mean']}／标准差 {p['stdev']}／区间 {p['lowest']}~{p['highest']}")
    scores = "、".join(f"{k} {v}" for k, v in sorted(p["scores"].items(), key=lambda x: -x[1])[:5])
    add(f"    - 最高几个：{scores}")
    low = "、".join(f"{k} {v}" for k, v in sorted(p["scores"].items(), key=lambda x: x[1])[:4])
    add(f"    - 最低几个：{low}")
if not jury.get("cleavage"):
    add("- （无）")

for n in jury.get("notes") or []:
    add(f"\n> 陪审团备注：{n}")

lsnotes = (d.get("canonical") or {}).get("notes") or []
if lsnotes:
    add(f"\n## 归纳阶段备注\n")
    for n in lsnotes:
        add(f"- {n}")
mn = (d.get("canonical") or {}).get("merge_notes")
if mn:
    add(f"\n**模型自述的合并说明：** {mn}")

add(f"\n## 统计备注\n")
for n in stats.get("notes") or []:
    add(f"- {n}")
for n in ((d.get("axis") or {}).get("notes") or []):
    add(f"- {n}")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(L), encoding="utf-8")
print(f"已写出 {OUT}（{OUT.stat().st_size} bytes）")

# 报告原文另存
if d.get("report"):
    rp = OUT.with_name("立场一览报告.md")
    rp.write_text(d["report"], encoding="utf-8")
    print(f"已写出 {rp}（{rp.stat().st_size} bytes）")
