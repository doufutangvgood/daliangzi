"""生成一个完整的演示运行，用于在浏览器里检查界面。

用 mock LLM 跑完整管道，产出一个真实结构的 run 目录。
不花一分钱，也不碰真实 API。

    python _research/make_demo_run.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from daliangzi.config import Config                       # noqa: E402
from daliangzi.ingest.model import Comment                # noqa: E402
from daliangzi.ingest.parse import load_from_text, records_to_comments  # noqa: E402
from daliangzi.llm import LLMResult                       # noqa: E402
from daliangzi.pipeline import analyze                    # noqa: E402
from daliangzi.store import Run, new_run_id               # noqa: E402

EVENT = "某地铁偷拍争议"

# 八种立场 + 各自的原生标签词，模拟真实的中文互联网讨论
LABEL_BANK = {
    "小仙女": ("嘲讽部分女性遇事上纲上线、双标", "反小仙女"),
    "打拳": ("认为部分人以性别议题为名无差别攻击男性", "反女权"),
    "普信男": ("嘲讽男性盲目自信、缺乏自省", "反普信"),
    "下头男": ("形容男性行为令人反感、瞬间失去好感", "反下头"),
    "捞女": ("认为部分女性在婚恋中索取物质", "反物质化"),
    "沸羊羊": ("嘲讽无底线付出的男性", "反舔狗"),
    "理中客": ("嘲讽以中立姿态拉偏架的人", "反理中客"),
    "受害者有罪论": ("批评把责任推给受害者的论调", "反责难受害者"),
    "偷拍入刑": ("主张加大对偷拍的处罚力度", "维权"),
    "隐私权": ("强调个人隐私不可侵犯", "维权"),
    "性别平权": ("主张两性权利对等", "平权"),
    "网络暴力": ("批评事件中的人肉与围攻行为", "反网暴"),
    "带节奏": ("认为有账号在刻意引导舆论", "反操控"),
    "境外势力": ("怀疑话题被外部力量推动", "反外部"),
    "吃瓜": ("纯粹围观、不表态", "围观"),
    "证据不足": ("认为事实尚未查清不应站队", "审慎"),
}

# 每个标签词配几条像样的评论
COMMENT_BANK = {
    "小仙女": [
        "小仙女就是这样，一点事就上纲上线，最后倒霉的还是普通人",
        "现在小仙女的操作真是看不懂，明明是自己的问题非要拉上全体女性",
        "动不动就小仙女，你们这套话术用了多少年了",
    ],
    "打拳": [
        "什么事都能打成性别对立，这拳法是真熟练",
        "又开始打拳了，证据都没有就开始带节奏",
        "打拳的能不能先看看事实再说话",
    ],
    "普信男": [
        "普信男真的多，一点本事没有还特别喜欢指点别人",
        "动不动就骂人普信男，那你们又是什么好东西",
        "普信男这个词用滥了，现在只要男的不同意就叫普信男",
    ],
    "下头男": [
        "这种行为真的是下头男本男了，恶心到我了",
        "一开始还觉得挺好，看完这个操作直接下头男",
    ],
    "捞女": [
        "这女的典型捞女，结婚要房要车，男的图什么",
        "现在捞女太多了，感情在她们眼里就是生意",
        "别动不动就说人捞女，你怎么知道人家图钱",
    ],
    "沸羊羊": [
        "一堆沸羊羊还在那舔，看着都替他们着急",
        "沸羊羊不得好死，这话我说了很多年了",
        "我是沸羊羊我骄傲，我乐意帮怎么了",
    ],
    "理中客": [
        "又是理中客来拉偏架了，两边各打五十大板就完事",
        "理中客最恶心，明明心里有立场还装客观",
        "我觉得做理中客没什么问题，凭什么不能中立",
    ],
    "受害者有罪论": [
        "又开始受害者有罪论了，穿什么都是她的自由",
        "典型的受害者有罪论，出了事就怪女生不检点",
        "这套受害者有罪论听了几十年了，烦不烦",
    ],
    "偷拍入刑": [
        "偷拍就应该入刑，现在这个处罚力度根本不够",
        "强烈支持偷拍入刑，必须让这些人付出代价",
        "偷拍违法，必须严惩，支持受害者",
    ],
    "隐私权": [
        "隐私权是基本权利，跟穿什么、在哪都没有关系",
        "讨论可以，人肉搜索就是侵犯隐私权",
        "支持女生，偷拍就是侵犯隐私，跟穿什么没关系",
    ],
    "性别平权": [
        "真正的性别平权是两边都不被刻板印象绑架",
        "我支持性别平权，但这不等于无条件站某一边",
    ],
    "网络暴力": [
        "不管怎么样网暴都是不对的，人肉和围攻太过分了",
        "现在就是网暴狂欢，当事人还没说话就被定罪了",
        "网络暴力入刑也该提上日程了",
    ],
    "带节奏": [
        "明显有人在带节奏，这个话题突然就爆了很奇怪",
        "一堆营销号在带节奏吃流量，能不能有点底线",
    ],
    "境外势力": [
        "这种话题背后有没有境外势力推波助澜，值得想想",
        "又开始境外势力了，自己人干的事非得赖别人",
    ],
    "吃瓜": [
        "纯路人吃瓜，两边都别拉我站队",
        "吃瓜看戏，这瓜有点大",
        "路过吃瓜，等一个后续",
    ],
    "证据不足": [
        "理性讨论，这事证据还不充分，别急着站队",
        "等一个完整的调查结果，现在说什么都太早",
        "两边都别急着下结论，事实还没查清",
    ],
    "两边都不对": [
        "两边都有问题，男的偷拍不对，女的网暴也不对",
        "说实话我觉得两边都挺离谱的",
    ],
}


def build_dataset(seed: int = 7, scale: int = 6):
    """按权重造一批评论，CSV 形式喂给真实解析链路。

    真实评论区不会整段复制粘贴，所以这里给每条评论加上随机的口语前缀/后缀，
    让语料有自然的多样性（也让去重逻辑不至于把所有东西都吃掉）。
    """
    rng = random.Random(seed)
    weights = {
        "小仙女": 9, "打拳": 7, "普信男": 8, "下头男": 4, "捞女": 6,
        "沸羊羊": 5, "理中客": 4, "受害者有罪论": 5, "偷拍入刑": 8,
        "隐私权": 10, "性别平权": 3, "网络暴力": 6, "带节奏": 4,
        "境外势力": 3, "吃瓜": 7, "证据不足": 5, "两边都不对": 6,
    }
    prefixes = ["", "", "", "说实话，", "不是，", "讲道理，", "我寻思",
                "评论区里", "说句公道话，", "有一说一，", "纯好奇，"]
    suffixes = ["", "", "", "。", "吧。", "啊这。", "，真的。", "，就这？",
                "，无语了。", "，你们觉得呢？", "，我反正是这么看的。"]

    rows = ["content,like_count,nickname"]
    n = 0
    for term, weight in weights.items():
        pool = COMMENT_BANK[term]
        for _ in range(weight * scale):
            text = rng.choice(prefixes) + rng.choice(pool) + rng.choice(suffixes)
            likes = int(abs(rng.gauss(0, 1)) * 1500 * (weight / 9) + rng.randint(0, 200))
            rows.append(f'"{text}",{likes},用户{n:04d}')
            n += 1

    # 掺一些噪声：广告、灌水、表情、以及真实存在的重复转发
    rows += [
        '"加微信 abc12345 领取考研资料",0,广告号',
        '"哈哈哈哈哈",3,路人甲',
        '"666",5,路人乙',
        '"😀😀😀",2,路人丙',
        '"这波我站女生",890,用户0001',
        '"这波我站女生",0,用户0002',
        '"偷拍违法，必须严惩，支持受害者",1800,用户0003',
        '"哈哈哈哈哈哈哈哈哈",1,路人丁',
    ]
    return "\n".join(rows)


# ---------------------------------------------------------------- mock LLM

def make_fake_complete():
    labels_by_term = {t: c for t, (c, _) in LABEL_BANK.items()}

    async def fake_complete(self, system, user, *, json_mode=True, temperature=None,
                            max_tokens=None, label="", **kw):
        if "捞标签" in label:
            start = user.find("[")
            payload = json.loads(user[start:]) if start != -1 else []
            results = []
            for item in payload:
                text = item["text"]
                labs = []
                for term, (claim, pole) in LABEL_BANK.items():
                    if term in text:
                        labs.append({"term": term, "claim": claim,
                                     "stance": "反对", "evidence": text[:34]})
                if not labs and ("两边都不对" in text or "两边都" in text):
                    labs.append({"term": "两边都不对", "claim": "认为双方都有问题",
                                 "stance": "中立", "evidence": text[:34]})
                results.append({"id": item["id"], "labels": labs})
            return LLMResult(text="{}", data={"results": results})

        if "语义合并" in label:
            return LLMResult(text="{}", data={
                "stances": [
                    {"canonical": "小仙女嘲讽", "core_logic": "嘲讽部分女性遇事上纲上线、双标",
                     "pole": "反小仙女", "aliases": ["小仙女"]},
                    {"canonical": "打拳指责", "core_logic": "认为部分人以性别议题为名无差别攻击男性",
                     "pole": "反女权", "aliases": ["打拳"]},
                    {"canonical": "普信男嘲讽", "core_logic": "嘲讽男性盲目自信、缺乏自省",
                     "pole": "反普信", "aliases": ["普信男"]},
                    {"canonical": "下头男批评", "core_logic": "形容男性行为令人反感",
                     "pole": "反下头", "aliases": ["下头男"]},
                    {"canonical": "捞女批判", "core_logic": "认为部分女性在婚恋中索取物质",
                     "pole": "反物质化", "aliases": ["捞女"]},
                    {"canonical": "舔狗嘲讽", "core_logic": "嘲讽无底线付出的男性",
                     "pole": "反舔狗", "aliases": ["沸羊羊"]},
                    {"canonical": "理中客嘲讽", "core_logic": "嘲讽以中立姿态拉偏架的人",
                     "pole": "反理中客", "aliases": ["理中客"]},
                    {"canonical": "反对受害者有罪论",
                     "core_logic": "批评把责任推给受害者的论调",
                     "pole": "维权", "aliases": ["受害者有罪论"]},
                    {"canonical": "偷拍入刑主张", "core_logic": "主张加大对偷拍的处罚力度",
                     "pole": "维权", "aliases": ["偷拍入刑"]},
                    {"canonical": "隐私权优先", "core_logic": "强调个人隐私不可侵犯",
                     "pole": "维权", "aliases": ["隐私权"]},
                    {"canonical": "性别平权", "core_logic": "主张两性权利对等、反对刻板印象",
                     "pole": "平权", "aliases": ["性别平权"]},
                    {"canonical": "反网络暴力", "core_logic": "批评事件中的人肉与围攻行为",
                     "pole": "反网暴", "aliases": ["网络暴力"]},
                    {"canonical": "警惕带节奏", "core_logic": "认为有账号在刻意引导舆论",
                     "pole": "反操控", "aliases": ["带节奏", "境外势力"]},
                    {"canonical": "纯围观吃瓜", "core_logic": "纯粹围观、不表态",
                     "pole": "围观", "aliases": ["吃瓜"]},
                    {"canonical": "审慎待证据", "core_logic": "认为事实尚未查清不应站队",
                     "pole": "审慎", "aliases": ["证据不足"]},
                    {"canonical": "双方都有责任", "core_logic": "认为当事人双方都有问题",
                     "pole": "中立", "aliases": ["两边都不对"]},
                ],
                "merge_notes": "「境外势力」并入「警惕带节奏」：两者都指向"
                               "「有人在刻意推动话题」，只是归因不同，暂作一类。",
            })

        if "坐标轴" in label:
            return LLMResult(text="{}", data={
                "axis": {
                    "name": "性别议题立场轴",
                    "left_pole": "传统性别秩序",
                    "left_desc": "认为女性应当回归传统角色期待",
                    "right_pole": "性别平权",
                    "right_desc": "认为身体自主与隐私权不可侵犯",
                    "note": "这条轴把「对女性的道德审判」和「对女性权利的主张」"
                            "放在两端。「理中客嘲讽」和「双方都有责任」跨在轴上，"
                            "因为它们同时批评两边。",
                },
                "alignments": [
                    {"canonical": "捞女批判", "left_affinity": 92, "right_affinity": 6},
                    {"canonical": "小仙女嘲讽", "left_affinity": 88, "right_affinity": 8},
                    {"canonical": "打拳指责", "left_affinity": 86, "right_affinity": 10},
                    {"canonical": "舔狗嘲讽", "left_affinity": 74, "right_affinity": 14},
                    {"canonical": "普信男嘲讽", "left_affinity": 52, "right_affinity": 58},
                    {"canonical": "下头男批评", "left_affinity": 44, "right_affinity": 62},
                    {"canonical": "理中客嘲讽", "left_affinity": 66, "right_affinity": 68},
                    {"canonical": "双方都有责任", "left_affinity": 70, "right_affinity": 74},
                    {"canonical": "审慎待证据", "left_affinity": 64, "right_affinity": 70},
                    {"canonical": "纯围观吃瓜", "left_affinity": 30, "right_affinity": 32},
                    {"canonical": "警惕带节奏", "left_affinity": 40, "right_affinity": 46},
                    {"canonical": "性别平权", "left_affinity": 22, "right_affinity": 84},
                    {"canonical": "反网络暴力", "left_affinity": 18, "right_affinity": 80},
                    {"canonical": "反对受害者有罪论", "left_affinity": 12, "right_affinity": 90},
                    {"canonical": "隐私权优先", "left_affinity": 8, "right_affinity": 94},
                    {"canonical": "偷拍入刑主张", "left_affinity": 5, "right_affinity": 95},
                ],
            })

        if "陪审团" in label:
            names = [
                "小仙女嘲讽", "打拳指责", "普信男嘲讽", "下头男批评", "捞女批判",
                "舔狗嘲讽", "理中客嘲讽", "反对受害者有罪论", "偷拍入刑主张",
                "隐私权优先", "性别平权", "反网络暴力", "警惕带节奏",
                "纯围观吃瓜", "审慎待证据", "双方都有责任",
            ]
            props = [
                ("偷拍是违法行为，应当受到法律制裁",
                 dict(zip(names, [72, 70, 88, 85, 74, 76, 80, 96, 98, 97, 94, 90, 82, 78, 92, 88]))),
                ("无论当事人有什么过错，网络暴力都不应该发生",
                 dict(zip(names, [78, 74, 90, 92, 80, 82, 88, 95, 93, 96, 96, 97, 85, 80, 90, 92]))),
                ("这件事上真正需要被追责的只有偷拍者一个人",
                 dict(zip(names, [40, 32, 30, 26, 34, 36, 58, 46, 62, 55, 50, 44, 52, 60, 48, 42]))),
                ("把个别行为归因为整个性别群体是不合理的",
                 dict(zip(names, [28, 22, 92, 90, 26, 24, 74, 88, 70, 82, 93, 86, 68, 76, 84, 80]))),
                ("当事女性在事件中的表现本身也值得讨论",
                 dict(zip(names, [92, 88, 40, 36, 95, 84, 62, 18, 34, 22, 26, 30, 58, 52, 46, 44]))),
                ("婚恋中索要彩礼和房车本质上是把感情明码标价",
                 dict(zip(names, [88, 82, 66, 60, 94, 78, 54, 24, 38, 28, 30, 34, 64, 50, 44, 40]))),
            ]
            return LLMResult(text="{}", data={
                "propositions": [{"text": t, "scores": s} for t, s in props]
            })

        if label == "报告":
            return LLMResult(text=(
                f"# 《{EVENT}全部立场一览：捞女、小仙女、普信男、"
                "偷拍入刑丨性别议题立场轴》\n\n"
                "## 一、事件背景\n\n"
                "这是一份**演示报告**，用来验证界面与排版，内容由 mock 数据生成，"
                "不代表任何真实事件或真实统计。\n\n"
                "本次分析基于 140 条评论，其中 12 条没有归入任何立场。"
                "需要说明的是，一条评论可以同时带有多个立场标签，"
                "因此各立场占比之和会超过 100%。\n\n"
                "## 二、立场坐标轴\n\n"
                "这条轴的一端是对女性的道德审判，另一端是对身体自主与隐私权的主张。\n\n"
                "## 三、各立场详解\n\n"
                "### 隐私权优先 · 占比 12.1%\n\n"
                "这一派的核心主张是个人隐私不可侵犯。\n\n"
                "> 隐私权是基本权利，跟穿什么、在哪都没有关系\n\n"
                "## 四、共识与撕裂点\n\n"
                "**共识**：偷拍违法、网暴不该发生。\n\n"
                "**撕裂点**：当事女性的表现是否值得讨论。\n"
            ))

        raise AssertionError(f"mock 未覆盖：{label}")

    return fake_complete


def main() -> int:
    csv_text = build_dataset()
    parsed = load_from_text(csv_text, "demo.csv")
    clean = records_to_comments(parsed.records, parsed.mapping)
    comments = clean.comments

    print(f"演示数据：原始 {clean.total_in} 条 → 清洗后 {len(comments)} 条")
    print(f"  清洗明细：{json.dumps(clean.summary(), ensure_ascii=False)}")

    run_id = new_run_id(EVENT)
    run = Run(run_id)
    run.save("input", {
        "meta": {
            "event_name": EVENT,
            "platform": "mixed",
            "created_at": "2026-09-27 12:00:00",
            "source_format": "csv",
            "filename": "demo.csv",
            "demo": True,
        },
        "mapping": parsed.mapping,
        "clean_report": clean.summary(),
        "comments": [c.to_dict() for c in comments],
    })

    import daliangzi.llm as llm_module

    original = llm_module.DeepSeekClient.complete
    llm_module.DeepSeekClient.complete = make_fake_complete()
    try:
        cfg = Config(api_key="sk-demo", batch_size=40, concurrency=4)
        result = analyze(run, comments, cfg, event_name=EVENT)
    finally:
        llm_module.DeepSeekClient.complete = original

    print(f"\n演示 run 已生成：{run_id}")
    print(f"  立场类别：{len(result.stats.stances)} 个")
    for s in result.stats.stances[:6]:
        aff = (f"  轴位 {s.x:.3f} ({s.left_affinity:.0f}/{s.right_affinity:.0f})"
               if s.left_affinity is not None else "")
        print(f"    {s.canonical:<16} {s.count:>4} 条  {s.pct:>5.1f}%"
              f"  构成 {s.__dict__.get('share', 0):>5.1f}%{aff}")
    print(f"  共识 {len(result.jury.consensus)} 条 / 撕裂点 {len(result.jury.cleavage)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
