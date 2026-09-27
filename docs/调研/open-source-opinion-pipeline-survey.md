# Open-source survey: crawl → cluster/classify opinions → visualize

Researcher: delegated subagent. **Verification date: 2026-09-27.** All star/license/last-push numbers were read from the GitHub REST API (`https://api.github.com/repos/<owner>/<repo>` and `/search/repositories`) on that date; each row links its repo page. Excluded per instructions: BettaFish, BERTopic, polis, talk-to-the-city, sensemaking-tools, topicGPT, lloom.

**Verification limits (read this first)**
- `github.com` HTML, `raw.githubusercontent.com`, and `r.jina.ai` were **not reachable** from this session; only `api.github.com` was. So: stars/license/last-push/archived are API-verified; **tech-stack and feature claims come from search snippets of READMEs/topic pages and are marked "stated" where I could not open the README myself.**
- The unauthenticated core API rate limit (60/h, shared IP) was exhausted, so I could not list commits, contributors, or files. "Maintenance" below = `pushed_at` (last push) rounded to days before 2026-09-27, plus `archived`.
- No number below is guessed. Anything I could not verify is written "unverified".

---

## 1. Ranked shortlist (most reusable for this pipeline)

| # | Repo | Stars | License | Last push | Stage reusable | Verdict |
|---|------|-------|---------|-----------|----------------|---------|
| 1 | [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | 65,789 | Other / NOASSERTION (custom, non-OSI metadata) | 2026-09-19 (8d) | **crawl** | Best-in-class comment crawler: 小红书/抖音/快手/B站/微博/Tieba/知乎, notes **and comments**. Very alive. |
| 2 | [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar) | 62,551 | GPL-3.0 | 2026-09-13 (14d) | crawl/aggregate + summarize + report/push | Hot-topic aggregation + RSS + keyword filtering + AI digest pushed to WeChat/Feishu/DingTalk/Telegram/mail/ntfy/bark/Slack; MCP-capable. **No comment-level stance clustering.** GPL = copyleft. |
| 3 | [apache/echarts](https://github.com/apache/echarts) | 67,402 | Apache-2.0 | 2026-09-16 (11d) | **visualize** | Chart layer if you build the UI yourself. |
| 4 | [streamlit/streamlit](https://github.com/streamlit/streamlit) | 45,838 | Apache-2.0 | 2026-09-27 (0d) | visualize / report app | Fastest “percentages + counts” dashboard for a Python pipeline. |
| 5 | [plotly/dash](https://github.com/plotly/dash) | 24,431 | MIT | 2026-09-24 (3d) | visualize | Dashboard alternative, no JS needed. |
| 6 | [yangheng95/PyABSA](https://github.com/yangheng95/PyABSA) | 1,105 | MIT | 2026-09-27 (0d) | **classify / opinion-unit extraction** | Maintained ABSA framework (aspect term + polarity; instruction-tuned variants). Maps directly to “opinion categories with polarity”. |
| 7 | [ScalaConsultants/Aspect-Based-Sentiment-Analysis](https://github.com/ScalaConsultants/Aspect-Based-Sentiment-Analysis) | 583 | Apache-2.0 | 2026-09-07 (20d) | classify (ABSA) + explainability | TensorFlow transformer ABSA with explainable-ML reporting; active. |
| 8 | [argilla-io/argilla](https://github.com/argilla-io/argilla) | 5,123 | Apache-2.0 | 2026-09-21 (6d) | human-in-the-loop labeling/QA | Useful to validate opinion labels before publishing percentages. |
| 9 | [aicezam/trendsonar](https://github.com/aicezam/trendsonar) | 43 | MIT | 2026-08-26 (32d) | cluster (event dedup) + summarize + visualize | Closest *whole-pipeline* analogue: hot-spot detection, event de-duplication/aggregation, sentiment direction, timeline + report (stated). Young, small. |
| 10 | [PompeiiChan/VoxRadar-1.0](https://github.com/PompeiiChan/VoxRadar-1.0) | 7 | Other / NOASSERTION | 2026-06-24 (95d) | crawl (xhs) + clean + **cluster** | LLM-driven: auto-crawl xhs notes/high-heat comments, LLM filters marketing content, then opinion analysis + pain-point clustering + scenario extraction (stated). Demo-scale. |
| 11 | [RUIIIOVO/lingxi_sentiment](https://github.com/RUIIIOVO/lingxi_sentiment) | 5 | Apache-2.0 | 2026-09-14 (13d) | visualize + alerting | Django + Vue public-opinion platform (sentiment trends, hot-topic tracking, real-time alerts, visualization, stated). Upstream Gitee project 灵犀舆情: [gitee.com/RUIOVO/lingxi](https://gitee.com/RUIOVO/lingxi). Very small mirror. |
| 12 | [x-tabdeveloping/topicwizard](https://github.com/x-tabdeveloping/topicwizard) | 148 | MIT | 2025-03-19 (557d) | visualize (topic/cluster explorer) | Dash/Plotly interactive topic-model visualization incl. BERTopic-compatible models. Semi-stale but functional. |
| 13 | [x-stance / ZurichNLP/xstance](https://github.com/ZurichNLP/xstance) | 42 | MIT | 2024-06-17 (832d) | classify (stance) — data + baseline | Multilingual multi-target stance **dataset**. Reusable as training/eval data, not as a service. |
| 14 | [kevinscaria/InstructABSA](https://github.com/kevinscaria/InstructABSA) | 170 | MIT | 2024-07-05 (814d) | classify (ABSA via instructions) | Instruction-tuning recipes for aspect-sentiment tasks; useful prompts, stale code. |
| 15 | [yangheng95/ABSADatasets](https://github.com/yangheng95/ABSADatasets) | 246 | MIT | 2026-09-27 (0d) | classify (training data) | Community datasets for ABSA (incl. Chinese). |

Secondary/optional building blocks (all API-verified): [MaartenGr/KeyBERT](https://github.com/MaartenGr/KeyBERT) 4,221★ MIT, pushed 2026-08-25 — keyword/opinion-phrase extraction for cluster labels; [megagonlabs/opiniondigest](https://github.com/megagonlabs/opiniondigest) 55★ Apache-2.0, 2024-08-20 — opinion summarization framework; [abrazinskas/Copycat-abstractive-opinion-summarizer](https://github.com/abrazinskas/Copycat-abstractive-opinion-summarizer) 98★ MIT, 2023-07-06 — classic opinion summarizer; [Gitter09/sift](https://github.com/Gitter09/sift) 0★ MIT, 2026-05-29 — Reddit/G2 feedback: scrape → sentence embeddings + HDBSCAN clustering → LLM insights (a compact template for our cluster stage); [0ethel0zhang/reddit_llm_clustering](https://github.com/0ethel0zhang/reddit_llm_clustering) 0★ no license, 2024-04-11 — LLM clustering of Reddit threads (demo).

## 2. Mandated candidates — detailed

| Candidate | Stars | License | Last push | Tech stack | Stage reusable | Status flag |
|---|---|---|---|---|---|---|
| [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | 65,789 | NOASSERTION ([license metadata](https://api.github.com/repos/NanmiCoder/MediaCrawler)) | 2026-09-19 | Python | crawl (notes + comments, 6+ CN platforms) | **Healthy.** Author states 59k+★; note the license is a custom "Other" — audit before commercial use. |
| [666ghj/MindSpider](https://github.com/666ghj/MindSpider) | 428 | NOASSERTION | 2026-02-14 | Python | crawl (topic discovery → multi-platform) | **ABANDONED standalone: `archived: true` in the API.** Its README content now lives inside the BettaFish repo ([MindSpider/README.md](https://github.com/666ghj/BettaFish/blob/main/MindSpider/README.md)); it credits MediaCrawler for the two-step crawl. Use MediaCrawler instead. |
| [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar) | 62,551 | GPL-3.0 | 2026-09-13 | Python, Docker, MCP server | aggregate + LLM summarize/report + push channels | **Very active.** Not a comment-stance engine; reuse the scheduling/digest/push half only. GPL-3.0 is viral for a distributed product. |
| [CodeAsPoetry/PublicOpinion](https://github.com/CodeAsPoetry/PublicOpinion) | 461 | **none** | **2022-07-16** (≈4.2 yr) | Python | intended full chain: crawl → clean → summarize → topic classify → sentiment polarity → visualization | **ABANDONED.** Repo description claims the whole pipeline (crawler, cleaning, summarization, topic classification, sentiment polarity, visualization) but the last push is 2022 and there is no license file → reuse only as a design reference. |
| [dileepangara3008/Youtube_Comment_Stance_Detection](https://github.com/dileepangara3008/Youtube_Comment_Stance_Detection) | **0** | none | 2026-05-22 | Python, 64 KB | classify stance (YouTube comments, support/oppose) | **Demo-only / hobby.** One commit-day repo, no stars, no license. |
| [rachithaiyappa/stance_detector](https://github.com/rachithaiyappa/stance_detector) | **0** | none | 2025-06-09 | Python, ~360 KB | classify stance (zero-shot prompting of a lightweight LLM) | **Research artifact, effectively unusable as a library.** Reproduces the paper *Zero-Shot Stance Detection in Practice* ([paper page](https://rachithaiyappa.github.io/science/Zero-Shot-for-Stance-Detection/)). |
| Jigsaw alternatives | — | — | — | — | — | *Jigsaw-Code/sensemaking-tools* itself is excluded (109★ Apache-2.0, pushed 2026-09-22, API-verified) as is its site [jigsaw-code.github.io/sensemaking-tools](https://jigsaw-code.github.io/sensemaking-tools/). **No maintained third-party fork/alternative of "Google Sensemaker" surfaced in any search; treat this slot as empty.** |
| awesome-lists | [laugustyniak/awesome-sentiment-analysis](https://github.com/laugustyniak/awesome-sentiment-analysis) 552★, **no license**, 2026-07-20 · [declare-lab/awesome-sentiment-analysis](https://github.com/declare-lab/awesome-sentiment-analysis) 538★, no license, 2023-03-14 · [nicolay-r/AwesomeStanceLearning](https://github.com/nicolay-r/AwesomeStanceLearning) (found via [topic page](https://github.com/topics/stance-detection); **stars unverified — search index returned no entry**) · [LiyingCheng95/Papers-on-Argument-Mining](https://github.com/LiyingCheng95/Papers-on-Argument-Mining) 9★, 2024-04-11 | mixed/none | — | bibliography only | None have runnable pipeline code. |

## 3. Chinese-language projects (舆情 / 评论观点 / 立场)

| Repo | Stars | License | Last push | Stage | Flag |
|---|---|---|---|---|---|
| [hchhtc123/AttributeLevel-EmotionAnalysis-WebSystem](https://github.com/hchhtc123/AttributeLevel-EmotionAnalysis-WebSystem) | 69 | MIT | **2023-05-31** (2.3 yr) | extract 评论观点 + ABSA + **web visualization** | Stale but **directly matches our shape**: PaddleNLP comment-opinion extraction + attribute-level sentiment + separated front/back-end web system. |
| [leozeng-coder/opinion_analysis](https://github.com/leozeng-coder/opinion_analysis) | 7 | none | 2026-06-24 | full-pipeline attempt ("AI舆情分析系统") | Toy-scale, no license, no docs surfaced. |
| [rookie-wy/Public-Opinion-Analysis-System-Based-on-Python](https://github.com/rookie-wy/Public-Opinion-Analysis-System-Based-on-Python) | **0** (one search snippet showed "2906", almost certainly a mis-snippet) | none | 2026-09-24 | sentiment pipeline (Chinese RoBERTa fine-tune, train→deploy) | New, zero traction; sentiment only, no stance/clustering. |
| [liangyiqiancheng-commits/AI-powered-public-opinion-analysis-system](https://github.com/liangyiqiancheng-commits/AI-powered-public-opinion-analysis-system) | 1 | none | 2026-08-11 | claims 采集/清洗/情感/话题聚类/预测/预警/报告 7-layer arch | README-only ambition; unverified code. |
| [SmallVagetable/opinionExtraction](https://github.com/SmallVagetable/opinionExtraction) | 46 | none | **2019-01-15** | **cluster** (dependency-parse opinion extraction + similarity + unsupervised clustering) | Abandoned, but the algorithm idea (unsupervised opinion clustering) is the cheapest non-LLM fallback for our cluster stage. |

## 4. Stance detection & argument mining (classify stage)

API-verified, **all research-grade and mostly dormant**: [sheffieldnlp/stance-conditional](https://github.com/sheffieldnlp/stance-conditional) 70★, no license, 2017-01-14 · [kochkinaelena/Multitask4Veracity](https://github.com/kochkinaelena/Multitask4Veracity) 57★ MIT, 2018-08-24 · [UKPLab/mdl-stance-robustness](https://github.com/UKPLab/mdl-stance-robustness) 45★ MIT, 2023-07-06 · [GU-DataLab/stance-detection-KE-MLM](https://github.com/GU-DataLab/stance-detection-KE-MLM) 40★ GPL-3.0, 2021-10-26 · [launchnlp/POLITICS](https://github.com/launchnlp/POLITICS) 40★ NOASSERTION, 2024-07-22 · [Leon-Francis/Multi-Modal-Stance-Detection](https://github.com/Leon-Francis/Multi-Modal-Stance-Detection) 32★ Apache-2.0, 2024-06-10 · [prajwal1210/Stance-Detection-in-Web-and-Social-Media](https://github.com/prajwal1210/Stance-Detection-in-Web-and-Social-Media) 32★, no license, 2020-10-18 · [prrao87/tweet-stance-prediction](https://github.com/prrao87/tweet-stance-prediction) 106★ MIT, 2019-02-10.

Argument mining: [trusthlt/mining-legal-arguments](https://github.com/trusthlt/mining-legal-arguments) 83★ Apache-2.0, 2023-05-15 · [vene/marseille](https://github.com/vene/marseille) 66★ BSD-3, 2017-08-01 · [UKPLab/acl2017-neural_end2end_am](https://github.com/UKPLab/acl2017-neural_end2end_am) 59★, 2021-01-13 · [Hellisotherpeople/DebateSum](https://github.com/Hellisotherpeople/DebateSum) 55★, 2021-12-02 · [Liebeck/ArgMining](https://github.com/Liebeck/ArgMining) 13★ MIT, 2023-07-28 · [nicolay-r/AREkit](https://github.com/nicolay-r/AREkit) 66★ MIT, 2026-02-05 (attitude/relation extraction — the liveliest of this group).

**Finding:** there is no maintained, pip-installable, production-grade open-source **stance-detection library** or **ArgMining library**. The practical route is an LLM prompt/schema of your own, optionally seeded with xstance / SemEval-style label taxonomies. [thunlp/OpenAttack](https://github.com/thunlp/OpenAttack) (780★ MIT, 2023-07-20) is **adversarial-attack tooling, not opinion mining** — it does not fit this pipeline.

## 5. ABSA / opinion-unit extraction (classify stage)

[yangheng95/PyABSA](https://github.com/yangheng95/PyABSA) 1,105★ MIT, 2026-09-27 (best maintained) · [ScalaConsultants/Aspect-Based-Sentiment-Analysis](https://github.com/ScalaConsultants/Aspect-Based-Sentiment-Analysis) 583★ Apache-2.0, 2026-09-07 · [HSLCY/ABSA-BERT-pair](https://github.com/HSLCY/ABSA-BERT-pair) 519★ MIT, 2022-01-04 · [howardhsu/BERT-for-RRC-ABSA](https://github.com/howardhsu/BERT-for-RRC-ABSA) 461★ Apache-2.0, 2021-02-05 · [NUSTM/ACOS](https://github.com/NUSTM/ACOS) 203★, 2022-10-20 (aspect-category-opinion-sentiment **quadruples**) · [lixin4ever/BERT-E2E-ABSA](https://github.com/lixin4ever/BERT-E2E-ABSA) 401★ Apache-2.0, 2023-07-09 · [NUSTM/ABSA-Reading-List](https://github.com/NUSTM/ABSA-Reading-List) 233★ · [siat-nlp/MAMS-for-ABSA](https://github.com/siat-nlp/MAMS-for-ABSA) 268★ Apache-2.0, 2019-11-04.
**ARCHIVED — do not build on:** [songyouwei/ABSA-PyTorch](https://github.com/songyouwei/ABSA-PyTorch) 2,114★ MIT, archived, 2023-06-12.

## 6. What I could not find (explicit gaps)

- **No actively maintained, star-worthy open-source project that does exactly "one event → comment opinion clusters → counts/percentages → dashboard".** The closest are trendsonar (43★), VoxRadar (7★, xhs-only), lingxi_sentiment (5★, Vue front-end), and the abandoned CodeAsPoetry/PublicOpinion (461★, 2022).
- **No maintained "Google Sensemaker" alternative/fork** was found.
- **No "awesome-stance-detection" list with any traction** was found; `nicolay-r/AwesomeStanceLearning` is the only candidate and its star count is unverified.
- **No `awesome-opinion-mining` list** surfaced; the nearest are the two awesome-sentiment-analysis lists (552★/538★, both license-less, one frozen since 2023).
- Zero-shot **stance** via lightweight LLM exists only as the 0★ research repo above; there is no packaged equivalent.

## 7. Suggested composition for this pipeline

1. **crawl** → MediaCrawler (or reuse our BettaFish pipeline if already covered).
2. **clean** → own rules + LLM filter, pattern taken from VoxRadar (LLM drops marketing/spam).
3. **cluster** → embeddings + HDBSCAN (pattern from Gitter09/sift), or KeyBERT for cluster labels; avoid depending on BERTopic (excluded).
4. **classify stance/opinion** → LLM structured output (no OSS library exists) + PyABSA/ABSA for aspect-polarity units if we want trainable components; xstance as eval data.
5. **summarize** → TrendRadar's digest pattern / opiniondigest if we want a non-LLM baseline.
6. **visualize** → Streamlit or Dash + ECharts (all Apache/MIT, all pushed within days of 2026-09-27).

## 8. Source list

API metadata endpoints (one per repo, e.g.): `https://api.github.com/repos/NanmiCoder/MediaCrawler`, `.../sansan0/TrendRadar`, `.../666ghj/MindSpider`, `.../CodeAsPoetry/PublicOpinion`, `.../rachithaiyappa/stance_detector`, `.../dileepangara3008/Youtube_Comment_Stance_Detection`, `.../ScalaConsultants/Aspect-Based-Sentiment-Analysis`, `.../yangheng95/PyABSA`, `.../aicezam/trendsonar`, `.../PompeiiChan/VoxRadar-1.0`, `.../RUIIIOVO/lingxi_sentiment`, `.../hchhtc123/AttributeLevel-EmotionAnalysis-WebSystem`, `.../smallVagetable/opinionExtraction` (correct case: `SmallVagetable`), `.../x-tabdeveloping/topicwizard`, `.../apache/echarts`, `.../streamlit/streamlit`, `.../plotly/dash`, `.../argilla-io/argilla`, `.../MaartenGr/KeyBERT`, `.../ZurichNLP/xstance`, `.../kevinscaria/InstructABSA`, `.../yangheng95/ABSADatasets`, `.../thunlp/OpenAttack`, `.../songyouwei/ABSA-PyTorch`, `.../NUSTM/ACOS`, `.../nicolay-r/AREkit`, `.../Gitter09/sift`.

Search/topic pages used for discovery: [github.com/topics/public-opinion-analysis](https://github.com/topics/public-opinion-analysis), [github.com/topics/stance-detection](https://github.com/topics/stance-detection), [github.com/topics/opinion-mining](https://github.com/topics/opinion-mining), [github.com/topics/public-opinion](https://github.com/topics/public-opinion), [github.com/topics/argument-mining](https://github.com/topics/argument-mining), [github.com/topics/social-media-mining](https://github.com/topics/social-media-mining), [jigsaw-code.github.io/sensemaking-tools](https://jigsaw-code.github.io/sensemaking-tools/), [gitee.com/RUIOVO/lingxi](https://gitee.com/RUIOVO/lingxi), [rachithaiyappa.github.io/science/Zero-Shot-for-Stance-Detection](https://rachithaiyappa.github.io/science/Zero-Shot-for-Stance-Detection/).
