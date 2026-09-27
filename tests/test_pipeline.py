"""管道测试。用 mock LLM 验证接线，不花一分钱。

跑法：
    python tests/test_pipeline.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from daliangzi.config import Config                      # noqa: E402
from daliangzi.ingest.model import Comment               # noqa: E402
from daliangzi.ingest.parse import (                     # noqa: E402
    load_from_text,
    records_to_comments,
)
from daliangzi.llm import LLMResult                      # noqa: E402
from daliangzi.pipeline import analyze                   # noqa: E402
from daliangzi.store import Run, new_run_id              # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [ok]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  → {detail}" if detail else ""))


# ---------------------------------------------------------------- 测试数据

RAW_CSV = """content,like_count,nickname
这女的典型捞女，结婚要房要车，男的图什么,1200,用户A
动不动就骂人普信男，那你们小仙女又是什么好东西,890,用户B
支持女生，偷拍就是侵犯隐私，跟穿什么没关系,3400,用户C
两边都有问题，男的偷拍不对，女的网暴也不对,760,用户D
哈哈哈笑死,12,用户E
加微信 abc12345 领取福利,0,广告狗
支持女生，偷拍就是侵犯隐私，跟穿什么没关系,0,用户F
理性讨论，这事证据还不充分，别急着站队,450,用户G
小仙女就是这样，一点事就上纲上线,2300,用户H
偷拍违法，必须严惩，支持受害者,1800,用户I
普信男真的多,560,用户J
这波我站女生,890,用户K
"""

NESTED_JSON = json.dumps([
    {
        "comment_id": "c1", "content": "捞女就是捞女", "like_count": 100,
        "nickname": "张三",
        "sub_comments": [
            {"comment_id": "c1-1", "content": "同意，现在太多了", "like_count": 5, "nickname": "李四"},
            {"comment_id": "c1-2", "content": "你才是捞男", "like_count": 2, "nickname": "王五"},
        ],
    },
    {"comment_id": "c2", "content": "支持女生维权", "like_count": 50, "nickname": "赵六"},
], ensure_ascii=False)

JSONL = "\n".join([
    json.dumps({"content": "第一条评论内容", "like_count": 3}, ensure_ascii=False),
    json.dumps({"content": "第二条评论内容", "like_count": 7}, ensure_ascii=False),
])

PLAIN = "这条评论没有字段结构\n第二条纯文本评论\n\n第三条"


# ---------------------------------------------------------------- mock LLM

MOCK_OPINIONS = {
    "捞女": ("认为部分女性在婚恋中索取物质", "捞女"),
    "普信男": ("认为男性普遍盲目自信", "普信男"),
    "小仙女": ("认为部分女性遇事上纲上线", "小仙女"),
    "偷拍": ("认为偷拍侵犯隐私应严惩", "偷拍"),
    "支持女生": ("支持当事女性维权", ""),
    "理性讨论": ("认为证据不足不应站队", ""),
}


def _fake_labels_for(text: str) -> list[dict]:
    """按关键词给观点，模拟真实模型的行为。

    注意提炼的是**观点**；term（圈内词）可能是空的。
    """
    out = []
    for keyword, (opinion, term) in MOCK_OPINIONS.items():
        if keyword in text:
            out.append({
                "opinion": opinion,
                "stance": "反对",
                "target": "事件本身",
                "term": term,
                "evidence": text[:30],
            })
    return out


CALL_LOG: list[str] = []


async def fake_complete(self, system, user, *, json_mode=True, temperature=None,
                        max_tokens=None, label="", **kw):
    """替换 DeepSeekClient.complete。按 label 判断当前是哪一步。"""
    CALL_LOG.append(label)

    # ① 捞观点：从 user 里解析出评论，逐条提炼
    # 注意实际 label 形如「捞标签 #1」（map_concurrent 会补序号）
    if "捞标签" in label:
        start = user.find("[")
        payload = json.loads(user[start:]) if start != -1 else []
        results = [
            {"id": item["id"], "opinions": _fake_labels_for(item["text"])}
            for item in payload
        ]
        return LLMResult(text="{}", data={"results": results})

    # ② 归纳
    if "语义合并" in label:
        return LLMResult(text="{}", data={
            "stances": [
                {"canonical": "批评物质化婚恋观",
                 "core_logic": "认为部分女性在婚恋中以感情为筹码索取物质",
                 "pole": "反物质化", "aliases": ["认为部分女性在婚恋中索取物质"],
                 "terms": ["捞女"]},
                {"canonical": "批评男性盲目自信",
                 "core_logic": "认为男性普遍缺乏自省、过度自信",
                 "pole": "反普信", "aliases": ["认为男性普遍盲目自信"],
                 "terms": ["普信男"]},
                {"canonical": "批评女性上纲上线",
                 "core_logic": "认为部分女性遇事容易扩大化",
                 "pole": "反小仙女", "aliases": ["认为部分女性遇事上纲上线"],
                 "terms": ["小仙女"]},
                {"canonical": "主张严惩偷拍",
                 "core_logic": "认为偷拍侵犯隐私、应当加重处罚",
                 "pole": "维权", "aliases": ["认为偷拍侵犯隐私应严惩", "支持当事女性维权"],
                 "terms": ["偷拍"]},
                {"canonical": "呼吁审慎待证据",
                 "core_logic": "认为事实未清前不应站队",
                 "pole": "审慎", "aliases": ["认为证据不足不应站队"],
                 "terms": []},
            ],
            "merge_notes": "测试用归纳说明。",
        })

    # ④ 坐标轴：模型只给两极贴合度，位置由代码算
    if "坐标轴" in label:
        return LLMResult(text="{}", data={
            "axis": {
                "name": "两性对立坐标轴",
                "left_pole": "传统性别秩序",
                "left_desc": "认为女性应当承担更多",
                "right_pole": "性别平权",
                "right_desc": "认为偷拍与穿着无关",
                "note": "测试用画轴说明。",
            },
            "alignments": [
                {"canonical": "批评女性上纲上线", "left_affinity": 95, "right_affinity": 5},
                {"canonical": "批评物质化婚恋观", "left_affinity": 80, "right_affinity": 10},
                {"canonical": "批评男性盲目自信", "left_affinity": 60, "right_affinity": 55},
                {"canonical": "呼吁审慎待证据", "left_affinity": 20, "right_affinity": 30},
                {"canonical": "主张严惩偷拍", "left_affinity": 5, "right_affinity": 95},
            ],
        })

    # ⑤ 陪审团
    if "陪审团" in label:
        names = ["批评物质化婚恋观", "批评男性盲目自信", "批评女性上纲上线",
                 "主张严惩偷拍", "呼吁审慎待证据"]
        return LLMResult(text="{}", data={
            "propositions": [
                {"text": "偷拍是违法行为，应当受到法律制裁",
                 "scores": {n: 90 for n in names}},
                {"text": "网络暴力受害者也应当被追究责任",
                 "scores": dict(zip(names, [95, 20, 15, 85, 60]))},
            ]
        })

    # ⑥ 报告
    if label == "报告":
        return LLMResult(text="# 测试报告\n\n## 一、事件背景\n\n这是一个测试。\n")

    raise AssertionError(f"mock 没覆盖的调用：{label}")


# ---------------------------------------------------------------- 测试

def test_parse() -> None:
    print("\n[解析与清洗]")

    r = load_from_text(RAW_CSV, "test.csv")
    check("CSV 识别正文字段", r.mapping.get("text") == "content", str(r.mapping))

    clean = records_to_comments(r.records, r.mapping)
    check("CSV 记录全收", clean.total_in == 12, str(clean.total_in))
    check("广告被过滤", clean.dropped_ad == 1, str(clean.summary()))
    check("重复被合并", clean.dropped_duplicate == 1, str(clean.summary()))
    check("清洗后 10 条", clean.total_out == 10, str(clean.summary()))

    # 去重时点赞应累加
    deduped = [c for c in clean.comments if "支持女生" in c.text]
    check("重复评论点赞累加", len(deduped) == 1 and deduped[0].likes == 3400, str(
        [(c.text[:10], c.likes) for c in deduped]))

    # 嵌套 JSON：二级评论不能丢
    r2 = load_from_text(NESTED_JSON, "test.json")
    clean2 = records_to_comments(r2.records, r2.mapping)
    check("嵌套 JSON 摊平出 4 条（含二级）", clean2.total_in == 4, str(clean2.total_in))
    check("JSON 字段识别", r2.mapping.get("likes") == "like_count", str(r2.mapping))
    check("父记录里不再保留 sub_comments（避免落盘翻倍）",
          all("sub_comments" not in r for r in r2.records),
          str([list(r.keys()) for r in r2.records]))

    r3 = load_from_text(JSONL, "test.jsonl")
    check("JSONL 识别", len(r3.records) == 2, str(len(r3.records)))

    r4 = load_from_text(PLAIN, "test.txt")
    clean4 = records_to_comments(r4.records, r4.mapping)
    check("纯文本按行解析", clean4.total_out == 3, str(clean4.summary()))

    # 纯表情/太短/灌水应被丢掉
    r5 = load_from_text("content\n哈哈哈\n这个事件我觉得问题很大\n😀😀😀\n666\n", "t.csv")
    clean5 = records_to_comments(r5.records, r5.mapping)
    check("纯表情与超短被过滤", clean5.total_out == 1, str(clean5.summary()))
    check("灌水评论被单独计数", clean5.dropped_filler == 2, str(clean5.summary()))
    check("灌水不计入「太短」", clean5.dropped_short == 1, str(clean5.summary()))

    # 「确实」这类短但可能有信息量的词不该被灌水规则误杀
    r7 = load_from_text("content\n这事的核心其实是证据不足\n支持严惩偷拍\n", "t.csv")
    clean7 = records_to_comments(r7.records, r7.mapping)
    check("有信息量的短评论不被误杀", clean7.total_out == 2, str(clean7.summary()))

    # 万/k 后缀
    r6 = load_from_text('content,like_count\n这是一条足够长的测试评论,1.2万\n', "t.csv")
    c6 = records_to_comments(r6.records, r6.mapping)
    check("点赞「1.2万」解析为 12000", c6.comments[0].likes == 12000, str(c6.comments[0].likes))


def test_counting() -> None:
    """单独验证确定性统计：LLM 不参与数数。"""
    print("\n[确定性统计]")

    from daliangzi.ingest.model import Label, Stance
    from daliangzi.pipeline.stage1_labels import LabelResult
    from daliangzi.pipeline.stage2_canon import CanonResult
    from daliangzi.pipeline.stage3_count import count_stances

    comments = [
        Comment(id=f"c{i}", text=f"评论{i}", likes=likes)
        for i, likes in enumerate([10, 20, 30, 40])
    ]
    # 主键是观点，term 只是附带
    label_result = LabelResult(labels={
        "c0": [Label(opinion="观点甲", term="黑话A"), Label(opinion="观点乙")],
        "c1": [Label(opinion="观点甲")],
        "c2": [Label(opinion="观点丙")],
        "c3": [],
    })
    canon = CanonResult(
        stances=[
            Stance(canonical="类别A", aliases=["观点甲"]),
            Stance(canonical="类别B", aliases=["观点乙"]),
            Stance(canonical="类别C", aliases=["观点丙"]),
        ],
        alias_map={"观点甲": "类别A", "观点乙": "类别B", "观点丙": "类别C"},
    )

    stats = count_stances(comments, label_result, canon)

    by_name = {s.canonical: s for s in stats.stances}
    check("类别A 计 2 条", by_name["类别A"].count == 2, str(by_name["类别A"].count))
    check("类别B 计 1 条", by_name["类别B"].count == 1, str(by_name["类别B"].count))
    check("无标签评论被统计", stats.unarmed_comments == 1, str(stats.unarmed_comments))
    check("多标签评论被统计", stats.multi_label_comments == 1, str(stats.multi_label_comments))
    check("归属总数为 4", stats.total_assignments == 4, str(stats.total_assignments))
    check("圈内词被汇总到类别上",
          by_name["类别A"].terms == ["黑话A"], str(by_name["类别A"].terms))

    # 占比：A=2/4=50%, B=1/4=25%
    check("类别A 占比 50%", abs(by_name["类别A"].pct - 50.0) < 0.01, str(by_name["类别A"].pct))
    # 构成占比：A=2/4=50%
    check("构成占比自洽", abs(by_name["类别A"].__dict__["share"] - 50.0) < 0.01,
          str(by_name["类别A"].__dict__.get("share")))

    # 点赞加权：A = c0(10) + c1(20) = 30，总点赞 100
    check("点赞加权正确", abs(by_name["类别A"].weighted_count - 30) < 0.01,
          str(by_name["类别A"].weighted_count))
    check("加权占比 30%", abs(by_name["类别A"].weighted_pct - 30.0) < 0.1,
          str(by_name["类别A"].weighted_pct))

    # 同一条评论重复同一个观点只算一次
    lr2 = LabelResult(labels={"c0": [Label(opinion="观点甲"), Label(opinion="观点甲")]})
    stats2 = count_stances([comments[0]], lr2, canon)
    check("同评论同观点不重复计数", stats2.stances[0].count == 1, str(stats2.stances[0].count))

    # 只有标签词、没有观点的旧数据也要能统计（向后兼容）
    lr3 = LabelResult(labels={"c0": [Label(opinion="", term="观点甲")]})
    stats3 = count_stances([comments[0]], lr3, canon)
    check("旧格式（只有 term）仍可统计",
          any(s.canonical == "类别A" and s.count == 1 for s in stats3.stances),
          str([(s.canonical, s.count) for s in stats3.stances]))


def test_pipeline_end_to_end() -> None:
    print("\n[端到端管道（mock LLM）]")

    import daliangzi.llm as llm_module

    original = llm_module.DeepSeekClient.complete
    CALL_LOG.clear()
    llm_module.DeepSeekClient.complete = fake_complete  # type: ignore[method-assign]

    try:
        r = load_from_text(RAW_CSV, "test.csv")
        clean = records_to_comments(r.records, r.mapping)
        comments = clean.comments

        run_id = new_run_id("测试事件")
        run = Run(run_id)
        run.save("input", {
            "meta": {"event_name": "测试事件"},
            "comments": [c.to_dict() for c in comments],
        })

        cfg = Config(api_key="sk-test", batch_size=5, concurrency=2)

        result = analyze(run, comments, cfg, event_name="测试事件")

        check("阶段一跑通", result.labels is not None and len(result.labels.labels) == len(comments))
        check("阶段二产出 5 个立场", len(result.canon.stances) == 5,
              str([s.canonical for s in result.canon.stances]))
        check("阶段三有统计", result.stats is not None and len(result.stats.stances) > 0)
        check("阶段四有坐标轴", result.axis is not None and result.axis.axis.name == "两性对立坐标轴",
              result.axis.axis.name if result.axis else "None")
        check("阶段五有陪审团", result.jury is not None and len(result.jury.consensus) >= 1,
              str(len(result.jury.consensus) if result.jury else 0))
        check("报告已生成", bool(result.report.strip()))

        # 圈内词应当被汇总到类别上，而且只作为点缀（不是统计主键）
        with_terms = [s for s in result.stats.stances if s.terms]
        check("圈内词汇总到类别", len(with_terms) >= 3,
              str([(s.canonical, s.terms) for s in result.stats.stances]))

        # 坐标轴每个类别都要有位置
        missing_x = [s.canonical for s in result.axis.stances
                     if s.count > 0 and s.x is None]
        check("所有非空类别都有轴位", not missing_x, str(missing_x))

        # 轴位必须是「两极贴合度」推导出来的，不是模型随口给的
        by_name = {s.canonical: s for s in result.axis.stances}
        check("轴位由贴合度推导（最左）",
              abs(by_name["批评女性上纲上线"].x - 5 / 100) < 0.01,
              str(by_name["批评女性上纲上线"].x))
        check("轴位由贴合度推导（最右）",
              abs(by_name["主张严惩偷拍"].x - 95 / 100) < 0.01,
              str(by_name["主张严惩偷拍"].x))
        check("骑墙立场落在中间",
              abs(by_name["批评男性盲目自信"].x - 55 / 115) < 0.01,
              str(by_name["批评男性盲目自信"].x))
        check("保留贴合度作为推导依据（可追溯）",
              by_name["批评物质化婚恋观"].left_affinity == 80
              and by_name["批评物质化婚恋观"].right_affinity == 10,
              f"{by_name['批评物质化婚恋观'].left_affinity}/{by_name['批评物质化婚恋观'].right_affinity}")
        check("轴位单调：左端类别 x 更小",
              by_name["批评女性上纲上线"].x < by_name["批评物质化婚恋观"].x < by_name["主张严惩偷拍"].x,
              f"{by_name['批评女性上纲上线'].x} / {by_name['批评物质化婚恋观'].x} / {by_name['主张严惩偷拍'].x}")

        # 占比必须自洽：按构造，捞到标签的评论数应等于各归属之和
        total = sum(s.count for s in result.stats.stances)
        check("归属总数与统计一致", total == result.stats.total_assignments,
              f"{total} vs {result.stats.total_assignments}")

        # 落盘完整性
        for stage in ("input", "labels", "canonical", "stats", "axis", "jury", "report"):
            check(f"产物已落盘：{stage}", run.has(stage))

        # ---- 断点续跑 ----
        calls_before = len(CALL_LOG)
        result2 = analyze(run, comments, cfg, event_name="测试事件")
        calls_after = len(CALL_LOG)
        check("第二次运行复用产物（0 次 LLM 调用）", calls_after == calls_before,
              f"{calls_before} → {calls_after}")
        check("复用后统计仍然一致",
              len(result2.stats.stances) == len(result.stats.stances))

        # 抽样跑一遍：报告必须知道自己在写抽样的结果
        sampled = analyze(run, comments, cfg, event_name="测试事件",
                          sample_limit=4, redo=["stats", "report"])
        check("抽样被记录", sampled.sampling.get("sampled") is True, str(sampled.sampling))
        check("抽样说明进了统计",
              bool((sampled.stats.extra.get("sampling") or {}).get("sampled")),
              str(sampled.stats.extra.get("sampling")))
        check("抽样说明也进了统计备注",
              any("随机抽样" in n for n in sampled.stats.notes),
              str(sampled.stats.notes)[:80])

        # ---- 强制重跑单阶段 ----
        result3 = analyze(run, comments, cfg, event_name="测试事件", redo=["canonical"])
        check("强制重跑 canonical 会再调用一次", len(CALL_LOG) > calls_after,
              str(len(CALL_LOG)))

        # 清理
        run.delete()

    finally:
        llm_module.DeepSeekClient.complete = original  # type: ignore[method-assign]


def test_prompt_coverage() -> None:
    """提示词里提到的必填字段，解析器要能认。"""
    print("\n[提示词一致性]")

    from daliangzi.prompts_loader import load_prompt

    p1 = load_prompt("stage1_标签")
    check("阶段一提示词要求逐条输出", "一条都不能漏" in p1)
    check("阶段一提示词强调提炼观点而非黑话",
          "观点" in p1 and "有观点就必须提炼" in p1)
    check("阶段一提示词要求观点措辞标准化", "完全相同的措辞" in p1)
    check("阶段一提示词把圈内词降级为可选", "可选" in p1)
    check("阶段一提示词含 json 字样（JSON Output 必需）", "json" in p1.lower())

    p2 = load_prompt("stage2_合并")
    check("阶段二提示词要求 aliases 逐字完整", "逐字完整" in p2)
    check("阶段二提示词要求反立场不能合并", "立场相反" in p2 and "绝对不能合并" in p2)
    check("阶段二提示词说明聚类对象是观点", "观点" in p2 and "不是标签词" in p2)

    p4 = load_prompt("stage4_坐标轴")
    check("阶段四提示词要求不漏类别", "一个都不能漏" in p4)
    check("阶段四提示词改为贴合度格式", "left_affinity" in p4 and "right_affinity" in p4)
    check("阶段四提示词不再让模型直接给坐标", '"x"' not in p4)

    p5 = load_prompt("stage5_报告")
    check("阶段五提示词禁止编造数字", "不许编造" in p5)
    check("阶段五提示词要求声明样本分母", "分母" in p5 or "样本量" in p5)
    check("阶段五提示词要求披露抽样", "抽样说明" in p5 and "全量民意" in p5)


def test_thinking_config() -> None:
    """思考模式必须按阶段显式设置。

    DeepSeek 默认打开思考模式且 effort=high。阶段一是几千条评论的机械抽取，
    开着它会白烧输出 token（思维链按输出价计费），而且 temperature 会静默失效。
    """
    print("\n[思考模式配置]")

    from daliangzi.config import THINKING_BY_STAGE
    from daliangzi.llm import build_payload

    check("五个阶段都有思考模式设置",
          set(THINKING_BY_STAGE) == {"labels", "canonical", "axis", "jury", "report"},
          str(sorted(THINKING_BY_STAGE)))
    check("大批量机械抽取阶段关掉思考（省钱关键）",
          THINKING_BY_STAGE["labels"] == "disabled",
          THINKING_BY_STAGE["labels"])
    check("需要判断的阶段保留思考",
          THINKING_BY_STAGE["jury"] in ("low", "high", "max")
          and THINKING_BY_STAGE["report"] in ("low", "high", "max"),
          f"jury={THINKING_BY_STAGE['jury']} report={THINKING_BY_STAGE['report']}")

    # 各阶段确实把设置传下去了（而不是用默认值）
    import inspect

    import daliangzi.pipeline.stage1_labels as s1
    import daliangzi.pipeline.stage2_canon as s2
    import daliangzi.pipeline.stage4_axis as s4
    import daliangzi.pipeline.stage5_report as s5

    for module, name in ((s1, "stage1"), (s2, "stage2"), (s4, "stage4"), (s5, "stage5")):
        src = inspect.getsource(module)
        check(f"{name} 显式传了 thinking", "THINKING_BY_STAGE" in src)

    # 关掉思考时 temperature 才会被传（否则是静默失效的假象）
    cfg = Config(api_key="sk-x", temperature=0.3)
    off = build_payload(cfg, "s", "u", thinking="disabled")
    on = build_payload(cfg, "s", "u", thinking="high")
    check("关思考 → 传 temperature 且生效", "temperature" in off)
    check("开思考 → 不传 temperature（避免假象）", "temperature" not in on)


def test_fail_fast() -> None:
    """阶段一整体失败时必须立刻停下，而不是静默穿过空阶段。"""
    print("\n[失败快速上报]")

    import daliangzi.llm as llm_module
    from daliangzi.pipeline import AnalysisError

    original = llm_module.DeepSeekClient.complete

    async def always_fail(self, system, user, **kw):
        from daliangzi.llm import LLMError
        raise LLMError("模拟的调用失败")

    # 注意：map_concurrent 用 gather(return_exceptions=True) 会吞掉单批异常，
    # 所以这里替换的是 complete，让每一批都失败。
    llm_module.DeepSeekClient.complete = always_fail  # type: ignore[method-assign]

    try:
        r = load_from_text(RAW_CSV, "test.csv")
        comments = records_to_comments(r.records, r.mapping).comments
        run = Run(new_run_id("失败测试"))
        run.save("input", {"meta": {"event_name": "失败测试"},
                           "comments": [c.to_dict() for c in comments]})

        cfg = Config(api_key="sk-test", batch_size=5, concurrency=2, max_retries=1)

        raised = None
        try:
            analyze(run, comments, cfg, event_name="失败测试")
        except AnalysisError as exc:
            raised = exc

        check("全部失败时抛出 AnalysisError", raised is not None)
        check("错误信息指明了排查方向",
              raised is not None and "API Key" in str(raised),
              str(raised)[:80] if raised else "None")
        check("没有产生报告产物（没有静默走完）", not run.has("report"))

        run.delete()

    finally:
        llm_module.DeepSeekClient.complete = original  # type: ignore[method-assign]


def test_sampling() -> None:
    """抽样：上限为 0 时不动，有上限时均匀随机抽样且可复现，并如实记录。"""
    print("\n[抽样]")

    from daliangzi.pipeline import sample_comments

    comments = [
        Comment(id=f"c{i}", text=f"评论内容{i}", likes=i)
        for i in range(500)
    ]

    same, info = sample_comments(comments, 0)
    check("上限为 0 时不抽样", len(same) == 500 and not info["sampled"], str(info))

    same2, info2 = sample_comments(comments, 800)
    check("上限大于总量时不抽样", len(same2) == 500 and not info2["sampled"], str(info2))

    picked, info3 = sample_comments(comments, 100)
    check("按上限抽样", len(picked) == 100, str(len(picked)))
    check("抽样被标记", info3["sampled"] is True, str(info3))
    check("记录了比例", abs(info3["ratio"] - 20.0) < 0.01, str(info3.get("ratio")))
    check("说明里写明了是随机抽样",
          "随机抽样" in info3["note"] and "小众立场" in info3["note"],
          info3["note"][:60])

    # 固定种子 → 同样输入抽到同一批（重跑结果可复现）
    again, _ = sample_comments(comments, 100)
    check("固定种子可复现", [c.id for c in picked] == [c.id for c in again])

    # 均匀随机：抽到的点赞分布应当大致反映总体，而不是只挑高赞
    all_likes = [c.likes for c in comments]
    picked_likes = [c.likes for c in picked]
    check("不是只挑高赞（抽到了低赞评论）",
          min(picked_likes) < 50, f"最低赞 {min(picked_likes)}")
    check("点赞均值接近总体均值",
          abs(sum(picked_likes) / len(picked_likes) - sum(all_likes) / len(all_likes)) < 60,
          f"样本均值 {sum(picked_likes)/len(picked_likes):.0f} vs 总体 {sum(all_likes)/len(all_likes):.0f}")


def test_incremental_labels() -> None:
    """试跑 / 断点续跑：已有部分标签时，只补跑缺的，不重跑全部。

    这是「先花几分钱试跑 30 条，再跑全量」这个用法的正确性基础。
    如果复用逻辑不做覆盖度检查，试跑之后跑全量会把没标签的评论当成「本来就无标签」，
    占比就全错了。
    """
    print("\n[标签增量补跑]")

    import daliangzi.llm as llm_module
    from daliangzi.pipeline import analyze

    original = llm_module.DeepSeekClient.complete
    CALL_LOG.clear()
    llm_module.DeepSeekClient.complete = fake_complete  # type: ignore[method-assign]

    try:
        r = load_from_text(RAW_CSV, "test.csv")
        comments = records_to_comments(r.records, r.mapping).comments   # 10 条
        run = Run(new_run_id("增量测试"))
        run.save("input", {"meta": {"event_name": "增量测试"},
                           "comments": [c.to_dict() for c in comments]})
        # batch_size=3 是刻意的：缺 7 条 → 3 批；若重跑全部 10 条 → 4 批。
        # 这样批次数本身就能区分「只补缺的」和「重跑全部」。
        cfg = Config(api_key="sk-test", batch_size=3, concurrency=2)

        # --- 第一次：模拟「试跑」，只跑前 3 条 ---
        partial = analyze(run, comments[:3], cfg, event_name="增量测试",
                          stop_after="labels")
        first_labels = run.load("labels") or {}
        check("试跑只保存了 3 条的标签",
              len(first_labels.get("labels") or {}) == 3,
              str(len(first_labels.get("labels") or {})))

        calls_after_trial = len(CALL_LOG)

        # --- 第二次：全量跑。应当只补跑缺的 7 条（3 批），而不是重跑 10 条（4 批） ---
        summarize_only = analyze(run, comments, cfg, event_name="增量测试",
                                 stop_after="labels")
        full_labels = run.load("labels") or {}
        check("全量跑后覆盖全部 10 条",
              len(full_labels.get("labels") or {}) == 10,
              str(len(full_labels.get("labels") or {})))

        # 试跑那一批的标签应当原样保留（同一批 id 的结果没变）
        kept = sum(1 for cid in (first_labels.get("labels") or {})
                   if cid in (full_labels.get("labels") or {}))
        check("试跑已有结果被保留", kept == 3, str(kept))

        new_calls = CALL_LOG[calls_after_trial:]
        check("补跑只送了缺的 7 条（3 批），没有重跑全部 10 条（4 批）",
              len(new_calls) == 3, f"实际 {len(new_calls)} 批：{new_calls}")

        # 第三次：完全覆盖后应当零调用
        before = len(CALL_LOG)
        analyze(run, comments, cfg, event_name="增量测试", stop_after="labels")
        check("覆盖完整后不再调用 LLM", len(CALL_LOG) == before,
              f"{before} → {len(CALL_LOG)}")

        run.delete()
    finally:
        llm_module.DeepSeekClient.complete = original  # type: ignore[method-assign]


def main() -> int:
    print("=" * 56)
    print("大量子 管道测试")
    print("=" * 56)

    test_parse()
    test_counting()
    test_prompt_coverage()
    test_thinking_config()
    test_sampling()
    test_pipeline_end_to_end()
    test_incremental_labels()
    test_fail_fast()

    print("\n" + "=" * 56)
    print(f"通过 {PASS} · 失败 {FAIL}")
    print("=" * 56)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
