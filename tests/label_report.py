"""把一次 run 的标签质量导成可读报告，便于人工核对。"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RID = sys.argv[1] if len(sys.argv) > 1 else "20260927-174925-DeepSeek-拟人形象之争-eefa"
BASE = "http://127.0.0.1:8770"
OUT = Path("data/raw/标签质量报告.md")

with httpx.Client(timeout=40) as c:
    d = c.get(f"{BASE}/api/runs/{RID}/labels?limit=2000").json()
    detail = c.get(f"{BASE}/api/runs/{RID}").json()

lines: list[str] = []
add = lines.append

add(f"# 标签质量报告 · {RID}\n")
add(f"- 评论总数：{d['total_comments']}")
add(f"- 已标注：{d['labelled']}")
add(f"- **有标签：{d['with_labels']}**（{100*d['with_labels']//max(1,d['labelled'])}%）")
add(f"- **无标签：{d['empty']}**（{100*d['empty']//max(1,d['labelled'])}%）")
add(f"- 不同标签词：{d['distinct_terms']}\n")

# 标签词频次
counter: Counter[str] = Counter()
stance_of: dict[str, Counter] = {}
for row in d["rows"]:
    for lab in row["labels"]:
        t = lab.get("term", "")
        if t:
            counter[t] += 1
            stance_of.setdefault(t, Counter())[lab.get("stance", "")] += 1

add(f"## 标签词频次（共 {len(counter)} 个）\n")
add("| 标签词 | 次数 | 倾向 | 一句话主张 |")
add("|---|---|---|---|")
claims = {}
for row in d["rows"]:
    for lab in row["labels"]:
        claims.setdefault(lab.get("term", ""), lab.get("claim", ""))

for term, n in counter.most_common(80):
    st = "、".join(f"{k}{v}" for k, v in stance_of[term].most_common(2))
    add(f"| {term} | {n} | {st} | {claims.get(term,'')[:40]} |")

add("\n## 有标签的评论（抽样 40 条）\n")
n = 0
for row in d["rows"]:
    if not row["labels"]:
        continue
    labs = " / ".join(f"**{l['term']}**（{l.get('stance','')}）— {l.get('claim','')}" for l in row["labels"])
    add(f"- [{row['likes']}赞] {row['text'][:110]}")
    add(f"  - → {labs}")
    n += 1
    if n >= 40:
        break

add("\n## 没捞到标签的评论（抽样 40 条）— 检查是不是误判\n")
n = 0
for row in d["rows"]:
    if row["labels"]:
        continue
    add(f"- [{row['likes']}赞] {row['text'][:110]}")
    n += 1
    if n >= 40:
        break

add("\n## 清洗明细\n")
add("```")
add(str(detail.get("clean_report")))
add("```")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"已写出 {OUT}  ({OUT.stat().st_size} bytes)")
print(f"有标签 {d['with_labels']} / 无标签 {d['empty']} / 标签词 {d['distinct_terms']}")
