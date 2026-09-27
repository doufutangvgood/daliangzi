"""端到端走一遍真实 HTTP 路径：预览 → 导入 → 估算 → 读回 → 导出。

只碰不花钱的部分（不调 LLM）。跑法：
    python tests/test_web_api.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8770"
PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [ok]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  → {detail}" if detail else ""))


NESTED = """[
 {"comment_id":"c1","content":"这女的典型捞女，结婚要房要车","like_count":1200,
  "nickname":"张三","sub_comments":[
    {"comment_id":"c1-1","content":"同意，现在这种人太多了","like_count":33,"nickname":"李四"},
    {"comment_id":"c1-2","content":"你凭什么这么说人家","like_count":8,"nickname":"王五"}]},
 {"comment_id":"c2","content":"偷拍就是侵犯隐私，跟穿什么没关系","like_count":3400,"nickname":"赵六"},
 {"comment_id":"c3","content":"加微信 abc12345 领资料","like_count":0,"nickname":"广告"},
 {"comment_id":"c4","content":"哈哈哈哈哈","like_count":2,"nickname":"路人"},
 {"comment_id":"c5","content":"理性讨论，证据还不充分，别急着站队","like_count":450,"nickname":"钱七"}
]"""


def main() -> int:
    print("=" * 58)
    print("大量子 Web API 端到端测试")
    print("=" * 58)

    created_runs: list[str] = []

    with httpx.Client(timeout=30) as c:
        try:
            status = c.get(f"{BASE}/api/status").json()
        except Exception as exc:  # noqa: BLE001
            print(f"\n连不上 {BASE}：{exc}")
            print("请先运行：python run.py")
            return 1

        try:
            _run_checks(c, created_runs, status)
        finally:
            # 崩了也要清干净，别在运行列表里留脏数据
            for rid in created_runs:
                try:
                    c.delete(f"{BASE}/api/runs/{rid}")
                except Exception:  # noqa: BLE001
                    pass

    print("\n" + "=" * 58)
    print(f"通过 {PASS} · 失败 {FAIL}")
    print("=" * 58)
    return 1 if FAIL else 0


def _run_checks(c: httpx.Client, created_runs: list[str], status: dict) -> None:
    if True:

        print("\n[服务状态]")
        check("status 可用", "model" in status)
        check("定价表里有缓存命中价", status["price"]["cache_hit"] > 0,
              str(status["price"]))
        check("阶段标签齐全", len(status.get("stage_labels", {})) == 6,
              str(len(status.get("stage_labels", {}))))

        print("\n[解析预览]")
        preview = c.post(f"{BASE}/api/preview", json={"text": NESTED, "filename": "t.json"}).json()
        check("识别为 json", preview.get("source_format") == "json", str(preview.get("source_format")))
        check("正文字段识别为 content",
              preview["mapping"].get("text") == "content", str(preview.get("mapping")))
        check("点赞字段识别为 like_count",
              preview["mapping"].get("likes") == "like_count", str(preview.get("mapping")))
        # c1 + 两条楼中楼 + c2..c5 = 7 条原始记录
        check("摊平出 7 条（父评论 1 + 楼中楼 2 + 其余 4）",
              preview.get("total_records") == 7,
              str(preview.get("total_records")))
        clean = preview.get("clean", {})
        check("广告被过滤", clean.get("去广告") == 1, str(clean))
        check("灌水被过滤", clean.get("去灌水") == 1, str(clean))
        check("保留 5 条", clean.get("保留") == 5, str(clean))
        check("返回可用字段清单", "content" in preview.get("available_fields", []),
              str(preview.get("available_fields")))

        print("\n[导入]")
        imp = c.post(f"{BASE}/api/import", json={
            "text": NESTED, "filename": "t.json",
            "event_name": "API 测试事件", "platform": "bilibili",
        })
        check("导入成功", imp.status_code == 200, imp.text[:200])
        run_id = imp.json().get("run_id", "")
        if run_id:
            created_runs.append(run_id)
        check("拿到 run_id", bool(run_id))
        check("导入计数正确", imp.json().get("count") == 5, str(imp.json().get("count")))

        print("\n[运行列表与读回]")
        runs = c.get(f"{BASE}/api/runs").json()["runs"]
        entry = next((r for r in runs if r["run_id"] == run_id), None)
        check("出现在运行列表", entry is not None)
        if entry:
            check("阶段计数是 x/6 而不是 x/7", entry.get("stage_total") == 6,
                  str(entry.get("stage_total")))
            check("只有 input 已落盘", entry.get("stage_done") == 0,
                  str(entry.get("stage_done")))
            check("评论数正确", entry.get("comment_count") == 5,
                  str(entry.get("comment_count")))

        detail = c.get(f"{BASE}/api/runs/{run_id}").json()
        check("读回事件名", detail["meta"].get("event_name") == "API 测试事件",
              str(detail.get("meta")))
        check("读回评论原文", len(detail.get("comments") or []) == 5,
              str(len(detail.get("comments") or [])))
        check("读回平台", detail["meta"].get("platform") == "bilibili",
              str(detail["meta"].get("platform")))

        print("\n[成本预估]")
        est = c.post(f"{BASE}/api/estimate", json={"run_id": run_id}).json()
        check("有预估合计", "total" in est, str(est)[:200])
        check("有分阶段明细", len(est.get("rows") or []) == 5,
              str(len(est.get("rows") or [])))
        check("空闲/高峰提示存在", bool(est.get("note")))
        check("缓存说明存在", bool(est.get("cache_note")), str(est.get("cache_note"))[:80])
        check("每阶段标了思考模式",
              all(r.get("thinking") for r in est.get("rows") or []),
              str([(r["stage"], r.get("thinking")) for r in est.get("rows") or []]))
        check("批量抽取阶段思考模式是关的",
              next(r["thinking"] for r in est["rows"] if r["stage"] == "labels") == "disabled",
              str([(r["stage"], r["thinking"]) for r in est["rows"]]))
        total_first = est.get("total", 0)
        check("首次跑预估大于 0", total_first > 0, str(total_first))
        check("没要求抽样时不标抽样", est.get("sampled") is False, str(est.get("sampled")))

        print("\n[抽样]")
        est_all = c.post(f"{BASE}/api/estimate",
                         json={"run_id": run_id, "sample_limit": 0}).json()
        est_s = c.post(f"{BASE}/api/estimate",
                       json={"run_id": run_id, "sample_limit": 2, "redo": ["labels"]}).json()
        check("上限 0 = 全部", est_all.get("sampled") is False
              and est_all.get("comment_count") == 5,
              f"sampled={est_all.get('sampled')} n={est_all.get('comment_count')}")
        check("设了上限就标抽样", est_s.get("sampled") is True, str(est_s.get("sampled")))
        check("抽样后分析条数等于上限", est_s.get("comment_count") == 2,
              str(est_s.get("comment_count")))
        check("抽样后预估小于全量",
              0 < est_s.get("total", 0) < est_all.get("total", 0),
              f"抽样 {est_s.get('total')} vs 全量 {est_all.get('total')}")
        check("抽样时返回导入总量", est_s.get("imported_count") == 5,
              str(est_s.get("imported_count")))

        print("\n[提示词]")
        prompts = c.get(f"{BASE}/api/prompts").json()["prompts"]
        names = {p["name"] for p in prompts}
        check("五个提示词都在", names == {
            "stage1_标签", "stage2_合并", "stage4_坐标轴",
            "stage5_陪审团", "stage5_报告"}, str(names))
        one = c.get(f"{BASE}/api/prompts/stage1_标签").json()
        check("能读到提示词内容", "只允许使用评论原文" in one.get("content", ""))

        print("\n[报告导出（还没有报告，应当优雅报 404）]")
        exp = c.get(f"{BASE}/api/export/{run_id}.md")
        check("没报告时返回 404 而不是崩", exp.status_code == 404, str(exp.status_code))

        print("\n[干跑预览]")
        dry = c.post(f"{BASE}/api/dry-run", json={"run_id": run_id, "stage": "labels"})
        check("干跑返回 200", dry.status_code == 200, dry.text[:200])
        d = dry.json()
        check("干跑给了真实 URL", d.get("url", "").endswith("/chat/completions"),
              d.get("url"))
        check("干跑里思考模式是关的", d.get("thinking") == "disabled", str(d.get("thinking")))
        check("干跑请求体带 thinking.disabled",
              d["payload"].get("thinking") == {"type": "disabled"},
              str(d["payload"].get("thinking")))
        check("干跑请求体是 JSON 模式",
              d["payload"].get("response_format") == {"type": "json_object"})
        auth = d.get("headers", {}).get("Authorization", "")
        check("干跑不回显完整 Key（要么未配置，要么中间打码）",
              ("未配置" in auth) or ("..." in auth),
              auth)
        check("干跑 system 段字符数与提示词一致",
              d["payload"]["messages"][0].get("字符数", 0) > 500,
              str(d["payload"]["messages"][0].get("字符数")))
        bad_stage = c.post(f"{BASE}/api/dry-run", json={"run_id": run_id, "stage": "nope"})
        check("不支持的阶段返回 400", bad_stage.status_code == 400, str(bad_stage.status_code))

        print("\n[标签核对（试跑后看捞取质量用）]")
        lab = c.get(f"{BASE}/api/runs/{run_id}/labels?limit=10")
        check("标签接口返回 200", lab.status_code == 200, lab.text[:200])
        lj = lab.json()
        check("还没跑过时 rows 为空", lj.get("rows") == [], str(lj.get("rows")))
        check("字段齐全",
              all(k in lj for k in ("labelled", "total_comments", "distinct_terms",
                                    "with_labels", "empty", "coverage_complete")),
              str(sorted(lj.keys())))
        check("还没跑过时覆盖不完整", lj.get("coverage_complete") is False,
              str(lj.get("coverage_complete")))
        check("返回评论总数", lj.get("total_comments") == 5, str(lj.get("total_comments")))

        print("\n[错误处理]")
        bad = c.post(f"{BASE}/api/import", json={"text": "   "})
        check("空内容返回 400", bad.status_code == 400, str(bad.status_code))
        bad2 = c.post(f"{BASE}/api/analyze", json={"run_id": run_id})
        check("没有 API Key 时分析被拒绝且提示清楚",
              bad2.status_code == 400 and "API Key" in bad2.text, bad2.text[:200])
        bad3 = c.get(f"{BASE}/api/runs/../../etc/passwd")
        check("run_id 路径穿越被挡住", bad3.status_code in (400, 404), str(bad3.status_code))
        bad4 = c.post(f"{BASE}/api/estimate", json={"run_id": "不存在的run"})
        check("不存在的 run 返回 404", bad4.status_code == 404, str(bad4.status_code))

        # 只读查询不能凭空造出目录，否则运行列表会被搞脏
        runs_after = c.get(f"{BASE}/api/runs").json()["runs"]
        check("查询不存在的 run 没有创建目录",
              not any(r["run_id"] == "不存在的run" for r in runs_after),
              str([r["run_id"] for r in runs_after if "不存在" in r["run_id"]]))
        check("运行列表里没有 0 条的坏条目",
              all(r["comment_count"] > 0 for r in runs_after),
              str([(r["run_id"], r["comment_count"]) for r in runs_after]))

        print("\n[清理]")
        dele = c.delete(f"{BASE}/api/runs/{run_id}")
        check("删除测试 run", dele.status_code == 200, str(dele.status_code))
        if dele.status_code == 200:
            created_runs.remove(run_id)


if __name__ == "__main__":
    raise SystemExit(main())
