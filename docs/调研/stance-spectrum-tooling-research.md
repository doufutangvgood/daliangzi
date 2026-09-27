# Stance Spectrum / Opinion Landscape — Open-Source Tooling Research

**Research date:** 2026-09-27 · All maintenance status assessed as of this date.
**Goal context:** place multiple opinion/stance groups (each with count + percentage) on a single
spectrum/axis ordered by how opposed they are, in a web front-end, plus a "stance overview table".

## Method & confidence notes

- `api.github.com` was **rate-limited (HTTP 403)** from this IP all session. Star counts come from
  two independent sources: the `ungh.cc` proxy (`https://ungh.cc/repos/<owner>/<repo>`) and
  shields.io badges. Where both were available they agreed; where only shields was available the
  count is rounded (e.g. "1.2k") and is marked as such.
- `github.com/<repo>` HTML pages consistently failed to fetch; `raw.githubusercontent.com`,
  `cdn.jsdelivr.net`, `data.jsdelivr.com` and `deepwiki.com` were reachable.
- `en.wikipedia.org` is **blocked from this host** (resolves to a non-public IP), so the Wikipedia
  "Opinion Space" entry could not be verified directly.
- PDFs are not fetchable (unsupported content type), so PDF-only claims are attributed to the
  secondary listing that described them.

---

## 1. Pol.is

| Field | Value | Source |
|---|---|---|
| Repo | [compdemocracy/polis](https://github.com/compdemocracy/polis) | — |
| Stars | **1,207** (+263 forks) | [ungh.cc](https://ungh.cc/repos/compdemocracy/polis) |
| License | **AGPL-3.0** — specifically "AGPLv3 with additional permission under section 7" | [badge](https://img.shields.io/github/license/compdemocracy/polis), [raw README](https://raw.githubusercontent.com/compdemocracy/polis/main/README.md) |
| Maintenance | **Actively maintained.** `pushedAt` 2026-09-25; shields "last commit: last friday" | [ungh.cc](https://ungh.cc/repos/compdemocracy/polis), [badge](https://img.shields.io/github/last-commit/compdemocracy/polis) |
| Default branch | `edge` (a `main` branch also resolves) | [ungh.cc](https://ungh.cc/repos/compdemocracy/polis) |
| Stack | Docker Compose; subdirs `math` (Clojure), `delphi` (Python ML), `server`, `*-client` | [raw README](https://raw.githubusercontent.com/compdemocracy/polis/main/README.md) |

### What it actually does (algorithm — verified)

Pol.is collects an **opinion matrix**: participants × statements, filled with `agree` / `disagree` /
`pass` ("comments * participants = a sparse matrix of votes") —
[compdemocracy.org/polis-opinion-matrix](https://compdemocracy.org/polis-opinion-matrix/).

Pipeline, from the official algorithm page ([compdemocracy.org/algorithms](https://compdemocracy.org/algorithms)):

- **Dimensionality reduction: PCA**, plus UMAP as an alternative.
- **Clustering: K-Means**, Leiden graph community detection, hierarchical clustering.
- Dimensions of note: `base-clusters` = fine-grained K-means with K=100; `group-clusters` = coarse
  grouping with the number of groups chosen by silhouette coefficient; math blob also exposes
  `pca`, `proj`, `repness` — [polis wiki math-overview](https://github.com/compdemocracy/polis/wiki/math-overview)
  (cited via the wiki page; the github.com HTML page itself did not fetch, so this line relies on the
  indexed wiki content).
- **Critical constraint, answered explicitly by the project:** *"Does Polis use natural language
  processing (NLP)? No. The machine learning algorithms run are solely run on the polis opinion
  matrix of agrees, disagrees and passes by participants on comments. Thus, Polis is language
  agnostic."* — [compdemocracy.org/algorithms](https://compdemocracy.org/algorithms),
  [FAQ](https://compdemocracy.org/faq/)
- Methods paper: *Polis: Scaling Deliberation by Mapping High Dimensional Opinion Spaces* (2021) —
  [article page](https://www.e-revistes.uji.es/index.php/recerca/article/view/5516) ·
  [PDF](https://www.e-revistes.uji.es/index.php/recerca/article/download/5516/6558/28347)

### What the visualization is, and what it is called

The project does **not** market the chart under a product name — the documentation calls it simply
**"the visualization"**, and the outputs are **"opinion groups"** and **consensus statements**
([polis documentation overview](https://pol-is.github.io/polis-documentation/welcome/Overview.html)).
Its stated three purposes: engagement, education, insight — "to reveal the landscape of opinion
(minority, majority, consensus)".

Behaviour, per [How to read the visualization](https://pol-is.github.io/polis-documentation/visualization/HowToRead.html):

- Every participant is a dot positioned by the PCA projection, "closest to other participants that
  voted similarly"; your own dot has a blue halo.
- **Opinion groups** are dotted-line regions around clusters of participants; "Groups form because
  members voted similarly on multiple issues, not just one issue."
- Clicking a group opens a **carousel of the comments that differentiated that group** (in-group
  agreement + out-group disagreement); as you swipe, participants' halos turn green/red/grey for
  agree/disagree/pass.
- The circle at each group's centre shows **the number of people in the group total**, and the halo
  shows the agree/disagree/pass ratio for those who saw the current comment, expressed as a
  percentage of the group.

**This is a 2-D scatter, not an ordered 1-D spectrum, and the PCA axes are not labelled or
interpretable.** Pol.is does not produce a "how opposed is group A to group B" scalar.

### Reusable for comments that are NOT structured votes?

**No, not directly — and the project says so explicitly.** The ML runs *only* on the agree/disagree/pass
matrix ([algorithms](https://compdemocracy.org/algorithms), [FAQ](https://compdemocracy.org/faq/)).
Free text can be *submitted* as statements, but a text is only ever positioned relative to others by
the votes it receives. To use Pol.is on unstructured comments you must first author statements and
collect votes on them — which is a product change, not a config change. (This is exactly the bridge
Talk to the City and Jigsaw build: they consume text, Pol.is consumes votes.)

### Embedding

Yes, and it is documented and first-class.

- Embed via a `<div class="polis" data-page_id=… data-site_id=…>` plus
  `<script async src="https://pol.is/embed.js">`, or by copying a script tag from the inbox —
  [Embedding docs](https://pol-is.github.io/polis-documentation/usage/Embedding.html)
- Per-user config flags include `data-show_vis` (toggle the visualization), `data-ucv` (can vote),
  `data-ucw` (can write), `data-ui_lang` (language), `bg_white`, `show_share`, etc. —
  [compdemocracy.org/embed-code](https://compdemocracy.org/embed-code/)
- The embed **emits a `vote` event** per vote that you can subscribe to via
  `window.addEventListener("message", …)` — [compdemocracy.org/embed-code](https://compdemocracy.org/embed-code/)
- Embed source: [github.com/compdemocracy/polis/…/client-participation/api/embed.js](https://github.com/compdemocracy/polis/blob/dev/client-participation/api/embed.js)
  (from the embed-code page; the standalone predecessor repo
  [pol-is/polisClientParticipation](https://github.com/pol-is/polisClientParticipation) is 26★ and
  last pushed **2021-02-25** — superseded by the monorepo).

**Limit:** you embed the *whole participation UI* (voting + writing + visualization). You can hide
facets, but you cannot embed the opinion-group chart alone as a component.

### Data you get out (the "stance overview table" raw material)

Export produces four tables — `summary.csv`, `stats-history.csv`, `participants-votes.csv`,
`comments.csv` — or a multi-sheet XLSX ([Data Export](https://pol-is.github.io/polis-documentation/data/Export.html)):

- **`participants-votes.csv`**: one row per participant with **`Group ID`**, comment count, vote
  count, agrees, disagrees, then one column per comment (1=agree, −1=disagree, 0=pass). → group
  **counts and percentages are trivial to compute** from this.
- **`comments.csv`**: one row per comment with **Agrees**, **Disagrees**, Moderated, Comment Body.

**Reuse verdict:** reuse it as a *service* (self-hosted stack or the hosted embed) or reuse its
*math*; do not treat it as a front-end chart component. Self-hosting is Docker-heavy, and AGPL-3.0
network copyleft applies.

---

## 2. Talk to the City

| Project | Repo | Stars | License | Last push | Status @ 2026-09-27 |
|---|---|---|---|---|---|
| **tttc-light-js** (current) | [AIObjectives/tttc-light-js](https://github.com/AIObjectives/tttc-light-js) | **59** | **Apache-2.0** | 2026-09-22 | **Active** (shields: "last tuesday") |
| **talk-to-the-city-reports** (archived) | [AIObjectives/talk-to-the-city-reports](https://github.com/AIObjectives/talk-to-the-city-reports) | **145** | mixed — `scatter/` README states **AGPL-3.0**; successor repo is Apache-2.0 | 2025-07 | **Deprecated**, explicitly "will soon be made read-only and archived" |

Sources: [ungh.cc tttc-light-js](https://ungh.cc/repos/AIObjectives/tttc-light-js),
[ungh.cc tttc-reports](https://ungh.cc/repos/AIObjectives/talk-to-the-city-reports),
[license badge](https://img.shields.io/github/license/AIObjectives/tttc-light-js),
[last-commit badge](https://img.shields.io/github/last-commit/AIObjectives/tttc-light-js),
[archived README](https://raw.githubusercontent.com/AIObjectives/talk-to-the-city-reports/main/README.md).

### What it produces

Current README: *"an open-source, LLM-enabled SaaS tool … It aggregates responses and organizes
similar claims into a **nested tree of main topics and subtopics**."*
([tttc-light-js README](https://raw.githubusercontent.com/AIObjectives/tttc-light-js/main/README.md))

Archived `scatter/` pipeline: *"takes a csv file of comments and generates html reports which: extract
the key arguments made in the original comments; **arrange the arguments into clusters based on their
semantic similarity**; generate labels and summaries for all the clusters; **provide interactive maps
to explore the arguments in each cluster**"* — and reports are *"static interactive **scatter-plot**
reports with summaries"* ([scatter README](https://raw.githubusercontent.com/AIObjectives/talk-to-the-city-reports/main/scatter/README.md)).

So there are two distinct visuals across the project's history:

1. **Older (`scatter`)**: a 2-D **scatter/argument map** of LLM-extracted arguments clustered by
   embedding similarity, with cluster labels/summaries; for Pol.is-sourced inputs *"the maps let you
   filter arguments by level of consensus"* — [scatter README](https://raw.githubusercontent.com/AIObjectives/talk-to-the-city-reports/main/scatter/README.md).
   Examples: [tttc.dev/heal-michigan](https://tttc.dev/heal-michigan), [tttc.dev/recursive](https://tttc.dev/recursive), [tttc.dev/genai](https://tttc.dev/genai).
2. **Current (`tttc-light-js`)**: a **hierarchical report** — topic tree → subtopics → claims → quotes.
   Confirmed in the file listing: `express-server/src/pipeline/topicTreeStep.ts`,
   `claimsStep.ts`, `cruxesStep.ts`, `sortClaimsTree.ts`, and a `next-client/src/components/barchart/Barchart.tsx`
   ([jsDelivr file listing](https://data.jsdelivr.com/v1/packages/gh/AIObjectives/tttc-light-js@main?structure=flat)).
   There is **no scatter component in the current repo.** Committed static example reports exist
   (`next-client/public/reports/heal-michigan.html`, `CIP.html`).

### Is it reusable?

Partially, and at high integration cost.

- The pipeline is genuinely runnable on your own CSV (`id,interview,comment`) and produces
  `args.csv`, `clusters.csv`, `embeddings.pkl`, `labels.csv`, `result.json`, plus an HTML report
  ([scatter README](https://raw.githubusercontent.com/AIObjectives/talk-to-the-city-reports/main/scatter/README.md)).
- The **current** repo is a SaaS application, not a chart library: it requires
  **Firebase (auth), Google Cloud Storage, Redis, and Google Pub/Sub — "required even for local
  development"** ([DEVELOPMENT.md](https://raw.githubusercontent.com/AIObjectives/tttc-light-js/main/DEVELOPMENT.md)).
- Reports are deployed as static/self-contained HTML; the older pipeline's output loads assets by
  relative paths and can be hosted anywhere ([scatter README](https://raw.githubusercontent.com/AIObjectives/talk-to-the-city-reports/main/scatter/README.md)).
- There is **no documented component API** to drop the map into an existing React app.

### Relevance to an ordered stance spectrum

TttC gives **semantic clusters of arguments**, not an ordered axis of opposition. It has no notion of
a 1-D stance coordinate. Clusters are unordered.

---

## 3. Jigsaw sensemaking-tools & the Sensemaker product

| Field | Value | Source |
|---|---|---|
| Repo | [Jigsaw-Code/sensemaking-tools](https://github.com/Jigsaw-Code/sensemaking-tools) | — |
| Stars | **109** (+39 forks) | [ungh.cc](https://ungh.cc/repos/Jigsaw-Code/sensemaking-tools), [badge](https://img.shields.io/github/stars/Jigsaw-Code/sensemaking-tools) |
| License | **Apache-2.0** | [badge](https://img.shields.io/github/license/Jigsaw-Code/sensemaking-tools) |
| Maintenance | `pushedAt` 2026-09-22 (shields: "september"), **but the README states: *"This codebase is not actively maintained"*** | [ungh.cc](https://ungh.cc/repos/Jigsaw-Code/sensemaking-tools), [README](https://raw.githubusercontent.com/Jigsaw-Code/sensemaking-tools/main/README.md) |
| Product page | [jigsaw-code.github.io/sensemaking-tools](https://jigsaw-code.github.io/sensemaking-tools/) — "Sensemaking AI", now a Jigsaw Partner Program with Change.org / make.org / RMG Research | product page |

### What it produces

From the [README](https://raw.githubusercontent.com/Jigsaw-Code/sensemaking-tools/main/README.md):
adaptive interviewing; data preparation; **topic modeling and quote extraction** (Gemini, or any
OpenAI-compatible endpoint incl. Gemma/vLLM/Ollama); **quote ranking** (reasoning, curiosity, "bridging"
scores); **discussion summarization** (recursive: opinion → topic → overview); **proposition
generation + simulated juries** ("identify statements likely to receive broad agreement"); and
*"identifying points of agreement and disagreement in free response public opinion research"*.
Also present: `src/social_choice/` with proportional approval voting and Schulze.

**Agreement/disagreement matrices: I found no matrix *visualization*.** What exists is per-comment
agreement metrics, "bridging" scores, and a **"Predicted Agreement" tab** rendering statements with a
`predicted_agreement` percentage ([report_ui README](https://raw.githubusercontent.com/Jigsaw-Code/sensemaking-tools/main/src/report_ui/README.md)).
A secondary source (DeepWiki, JS-rendered so the page body did not fetch) states there is a Pol.is
export processing component doing *"vote aggregation, group assignment, and calculation of key
metrics for each comment"* — [deepwiki.com/Jigsaw-Code/sensemaking-tools/2.3-data-processing](https://deepwiki.com/Jigsaw-Code/sensemaking-tools/2.3-data-processing).
Treat that as **secondary/unverified**; I could not confirm a `polis` module in the current file
listing (it shows `src/qualtrics/`, `src/participation.py`, no `src/polis/`).

### Is there a public UI? Yes — and it is the closest match to the goal

`src/report_ui/` is a **static interactive HTML report generator** (Node, no framework):
inputs `opinions.csv` (`topic`, `opinion`, `representative_text`, `participant_id`, optional
`AVERAGE_OF_2_BRIDGING`, optional `demo:*` columns) + `summary.json` + `config.json`, output either a
**static** site or a **single self-contained `index.html`** ("inline", best for emailing/offline)
([report_ui README](https://raw.githubusercontent.com/Jigsaw-Code/sensemaking-tools/main/src/report_ui/README.md)).

Visualization logic, verbatim from that README:

> **Frameworks**: D3.v7 (charts), Tippy.js (tooltips), Mustache (templating).
> **Charts**: *Topic Chart*: A **stacked horizontal bar chart** summarizing opinion distribution.
> *Opinion Chart*: A **flattened bar chart** of the top opinions across all topics.
> *Donut Charts*: Per-topic visualization of opinion breakdown.

Plus: `overview_chart` mode toggle (`"toggle" | "topics" | "opinions"`), top-N opinions, sample-quote
counts, topic/demographic colour palettes, low-sample warning threshold, `translations.json` i18n with
LTR/**RTL** support, demographic breakdown chart from `demo:*` columns, and a "Predicted Agreement" tab.

Public example reports: [report.whatcouldbgbe.com](https://report.whatcouldbgbe.com) (Bowling Green KY,
8,000 participants), [freedom.wethepeople-250.org](https://freedom.wethepeople-250.org),
[napolitaninstitute.org/Oklahoma's America Dream](https://napolitaninstitute.org/Oklahoma%27s%20American%20Dream.html)
— all from the [product page](https://jigsaw-code.github.io/sensemaking-tools/).

**Reuse verdict:** the `report_ui` is the single best *architectural* precedent for "ordered
proportional bars + a stance overview table + per-topic breakdowns" — but it is a **build-script +
Mustache template + vanilla JS/D3 report generator**, not a reusable component. Reuse means copying
and adapting `data.js` / `script.js` / `index.mustache`. Note it also has **no opposition ordering**:
topics and opinions are grouped, not placed on a spectrum.

---

## 4. Political compass / opinion spectrum web visualizations

| Project | Live | Repo | Stars | License | Last push | Maintained @ 2026-09-27 |
|---|---|---|---|---|---|---|
| polcomp | [politicaltests.github.io/polcomp](https://politicaltests.github.io/polcomp/) | [politicaltests/polcomp](https://github.com/politicaltests/polcomp) | 1 | **none present** → unlicensed | 2022-03-05 | Dormant ~4.5 yrs |
| 8values | [8values.github.io](https://8values.github.io/) | [8values/8values.github.io](https://github.com/8values/8values.github.io) | 1111 | **MIT** ([LICENSE](https://raw.githubusercontent.com/8values/8values.github.io/master/LICENSE)) | 2023-07-28 | Dormant ~3.2 yrs |
| 9Axes | [9axes.github.io](https://9axes.github.io/) | [9Axes/9axes.github.io](https://github.com/9Axes/9axes.github.io) | 58 | **MIT** ([LICENSE](https://raw.githubusercontent.com/9Axes/9axes.github.io/master/LICENSE)) | 2021-11-09 | Dormant ~4.9 yrs |
| SapplyValues | [sapplyvalues.github.io](https://sapplyvalues.github.io/) | [SapplyValues/SapplyValues.github.io](https://github.com/SapplyValues/SapplyValues.github.io) | 75 | *unverified* | 2024-07-06 | Semi-dormant ~1.2 yrs |
| 10Groups | [politicaltests.github.io](https://politicaltests.github.io/index.html) | [10Groups/10groups.github.io](https://github.com/10Groups/10groups.github.io) | 35 | *unverified* | 2023-06-19 | Dormant ~3.3 yrs |
| 3D-Political-Spectrum | — | [JawnGrimm/3D-Political-Spectrum](https://github.com/JawnGrimm/3D-Political-Spectrum) | 0 | *unverified* | 2025-12-08 | Stale ~9.7 mo |
| spectrum (cosponsorship) | — | [JakeLerner/spectrum](https://github.com/JakeLerner/spectrum) | 1 | *unverified* | 2015-10-21 | Abandoned ~11 yrs |

**What each renders**

- **polcomp** — a **2-D compass explorer, not a quiz**: "an interactive political compass, with 169
  political ideologies plotted on it", with descriptions and lists of people/views; axes Economic
  (Left–Right) × Governmental (Authoritarian–Libertarian), four named quadrants.
- **8values** — quiz producing **8 independent axis percentages** (Equality/Markets, Nation/Globe,
  Liberty/Authority, Tradition/Progress) + an ideology label.
- **9Axes** — the 8values UI generalised to **9 axes**; ships a `ru/` translation.
- **SapplyValues** — 2-D compass: Sapply question set + 8values UI.
- **10Groups** — quiz scoring **10 category compasses**.
- **JawnGrimm/3D-Political-Spectrum** — "interactive 3D visualization of political ideologies …
  rotating the cube … AI-generated summary per ideology … questionnaire to plot your own position";
  README states it was "Generated in Google AI Studio w/ assistance from Claude".
- **JakeLerner/spectrum** — derives **arbitrary 1-D issue spectrums** from congressional
  cosponsorship records (the one project here that computes an empirical 1-D axis).

**KEY FINDING — none of these is a reusable library.** Every project above is a hardcoded,
single-purpose standalone site:

1. **No package manifest, no library entry point.** File listings for polcomp / 8values / 9Axes contain
   only `*.html`, `*.js` data files, `style.css`, images, `README.md`, `LICENSE` — no `package.json`,
   no module graph, no build config, no exported API
   ([polcomp files](https://ungh.cc/repos/politicaltests/polcomp/files/main),
   [8values files](https://ungh.cc/repos/8values/8values.github.io/files/master),
   [9axes files](https://ungh.cc/repos/9Axes/9axes.github.io/files/master)).
2. The `.js` files are **global-scope data tables** (`questions.js`, `ideologies.js`) loaded by
   `<script>` — copyable as data, not importable.
3. Rendering/scoring logic is **inlined per page**; no renderer callable with your own data.
4. No releases, no npm publication, no versioning.

**Reuse verdict:** only the **MIT data files** from 8values/9axes are safely liftable. Any actual
visualization must be rebuilt.

---

## 5. Charting options for "ordered stance axis with proportional bars"

| Library | Repo | Stars | License | Last push | Status @ 2026-09-27 |
|---|---|---|---|---|---|
| Apache ECharts | [apache/echarts](https://github.com/apache/echarts) | **67398** | Apache-2.0 | 2026-09-16 | Very active |
| D3 | [d3/d3](https://github.com/d3/d3) | **113768** (shields: 114k) | ISC | 2026-05-28 | Active |
| Vega-Lite | [vega/vega-lite](https://github.com/vega/vega-lite) | **5497** | BSD-3-Clause | 2026-09-24 | Very active |
| plotly.js | [plotly/plotly.js](https://github.com/plotly/plotly.js) | **18347** | MIT | 2026-09-25 | Very active |
| nivo (React) | [plouc/nivo](https://github.com/plouc/nivo) | **14102** (shields: 14k) | MIT | 2026-07-21 | Active |
| Frappe Gantt | [frappe/gantt](https://github.com/frappe/gantt) | **6128** | MIT | 2026-06-18 | Active |

Star counts via [ungh.cc](https://ungh.cc/repos/apache/echarts); licences via npm registry metadata
([echarts](https://registry.npmjs.org/echarts/latest), [d3](https://registry.npmjs.org/d3/latest),
[vega-lite](https://registry.npmjs.org/vega-lite/latest), [plotly.js](https://registry.npmjs.org/plotly.js/latest),
[@nivo/bar](https://registry.npmjs.org/@nivo/bar/latest), [frappe-gantt](https://registry.npmjs.org/frappe-gantt/latest)).
Note the npm package is `frappe-gantt` while the repo is `frappe/gantt`.

### Visual-capability matrix

| Chart type | ECharts | D3 | Vega-Lite | plotly.js | nivo | Notes |
|---|---|---|---|---|---|---|
| Diverging stacked bar | Adapt (negative stack) | Custom | **recipe** | Adapt (`barmode:'relative'`) | **recipe** | see below |
| Likert chart | Adapt | Custom | via diverging recipe | Adapt | via diverging recipe | **no first-class "likert" type anywhere** |
| Gantt-style ordered bands | Custom series | Custom | not native | Adapt (`bar`+`base`) | — | dedicated lib: Frappe Gantt |
| Theme river | **`themeRiver`** | Custom | — | — | `@nivo/stream` | |
| Sankey | **`sankey`** | `d3-sankey` | not native | yes | `@nivo/sankey` | |
| 2-D scatter w/ quadrants | `scatter`+`markArea` | yes | `point`+layers | `scatter` | `@nivo/scatterplot` | |

### Ready-made Likert / diverging stacked bar recipes

| Recipe | Source | Verdict |
|---|---|---|
| **Vega-Lite "Diverging Stacked Bar Chart (with Neutral Parts)"** | [vega.github.io/vega-lite/examples/bar_diverging_stack_transform.html](https://vega.github.io/vega-lite/examples/bar_diverging_stack_transform.html) | **Copy-paste ready** (v6 schema): `signed_percentage` calculate → `stack` → `joinaggregate` offset → `nx`/`nx2` on `x`/`x2` |
| **nivo "Stacked diverging bar chart"** | [storybook](https://nivo.rocks/storybook/?path=/story/bar--diverging-stacked) · [Bar docs → Recipes](https://nivo.rocks/bar/) | First-class, needs adaptation (React props) |
| nivo "Grouped diverging bar chart" | [Bar docs](https://nivo.rocks/bar/) | Needs adaptation |
| plotly.js relative barmode | [plotly.com/javascript/bar-charts](https://plotly.com/javascript/bar-charts/) | Needs adaptation; no dedicated Likert example |
| ECharts negative/stacked bar | [echarts.apache.org/en/option.html#series-bar](https://echarts.apache.org/en/option.html) | Custom build — no built-in diverging/Likert series |
| ECharts Theme River | [example](https://echarts.apache.org/examples/en/editor.html?c=themeRiver-basic) · [option MD](https://github.com/apache/echarts-doc/blob/master/en/option/series/themeRiver.md) | Native chart type |
| ECharts Gantt | [custom-gantt-flight](https://echarts.apache.org/examples/en/editor.html?c=custom-gantt-flight) · [custom-series guide](https://echarts.apache.org/handbook/en/how-to/custom-series/) | Custom series |
| D3 diverging stacked bar (Likert) | [wpoely86/D3.js-Diverging-Stacked-Bar-Chart](https://github.com/wpoely86/D3.js-Diverging-Stacked-Bar-Chart) | 11★, last push **2014-12-21** — abandoned ~11 yrs; reference only |
| D3 Local Chart Templates (147 templates) | [tnibir/D3-Local-Chart-Templates/021-diverging-stacked-bar-chart](https://github.com/tnibir/D3-Local-Chart-Templates/tree/main/021-diverging-stacked-bar-chart) | 0★, pushed 2026-08-06 — unproven |

### Dedicated OSS React/Vue Likert components

| Component | Source | Stars | License | Activity | Verdict |
|---|---|---|---|---|---|
| react-likert | [jasonphillips/react-likert](https://github.com/jasonphillips/react-likert) · [npm](https://www.npmjs.com/package/react-likert) | 7 | MIT | 2019-03-28 | Closest match: React + D3 diverging Likert bars inside a real `<table>` with ARIA; **dormant ~7.5 yrs** — reference only |
| react-likert-scale | [npm](https://registry.npmjs.org/react-likert-scale) | *unverified* | CC0-1.0 | last publish 2021-06-02 | **Not a chart** — ~5 kB radio-button *input* |
| robdongas/likert-charts | [repo](https://github.com/robdongas/likert-charts) | 0 | *unverified* | 2024-04-22 | ApexCharts stack demo; reference only |

**No maintained, dedicated, drop-in React/Vue Likert *chart* component exists.** The realistic options
are Vega-Lite (declarative, framework-agnostic) or nivo (React-native recipe).

---

## 6. Projects that render an *opinion space* from clustered text (not votes)

### Direct answer

**I found no open-source project that takes raw clustered text (no votes) and renders a 1-D ordered
stance spectrum.** What exists falls into two families:

**(a) Votes → 2-D opinion map with groups** (Pol.is family). Closest to "opinion landscape", but the
axes are unlabelled and unordered, and a vote matrix is mandatory.

**(b) Text → 2-D cluster/argument map** (no ordering, no opposition). Closest to "from text", but the
layout encodes *semantic similarity*, not *stance opposition*.

| Project | Repo | Stars | License | Last push | What it renders | Axis? |
|---|---|---|---|---|---|---|
| Pol.is | [compdemocracy/polis](https://github.com/compdemocracy/polis) | 1207 | AGPL-3.0 | 2026-09-25 | 2-D PCA scatter + opinion groups + consensus | 2-D, unlabelled |
| **Red Dwarf** | [polis-community/red-dwarf](https://github.com/polis-community/red-dwarf) | **25** | **MPL-2.0** | 2026-09-11 | **Python library** reproducing the Pol.is pipeline exactly (PCA + KMeans) + PaCMAP/LocalMAP/HDBSCAN alternatives; matplotlib plots; loads data from *any* Pol.is conversation by URL; on PyPI | 2-D projection, programmatic |
| Talk to the City | [AIObjectives/tttc-light-js](https://github.com/AIObjectives/tttc-light-js) | 59 | Apache-2.0 | 2026-09-22 | Nested topic/claim tree (older: 2-D argument scatter) | none |
| Jigsaw Sensemaking | [Jigsaw-Code/sensemaking-tools](https://github.com/Jigsaw-Code/sensemaking-tools) | 109 | Apache-2.0 | 2026-09-22 | Topic/opinion stacked bars + donuts + tables | none |
| **Consider.it** | [Considerit/ConsiderIt](https://github.com/Considerit/ConsiderIt) | 106 | **AGPL-3.0** | 2026-06-15 | "deliberation and **opinion visualization**"; 4-quadrant per-proposal stance views | stance per proposal |
| Harmonica | [harmonicabot/harmonica-web-app](https://github.com/harmonicabot/harmonica-web-app) | 7 | AGPL-3.0 | 2026-04-12 | AI-facilitated deliberation; thematic synthesis, consensus/tension surfacing | none |
| Agora Citizen Network | [zkorum/agora](https://github.com/zkorum/agora) | 43 | *unverified* | 2026-09-24 | Polis-inspired deliberation platform | Polis-like |
| Nexus / MindMeld | [sofvanh/Nexus](https://github.com/sofvanh/Nexus) | 7 | *unverified* | 2026-05-22 | Group deliberation, "inspired by Polis and X Community Notes" | — |
| Metropolis | [canvasxyz/metropolis](https://github.com/canvasxyz/metropolis) | 12 | *unverified* | 2025-04-30 | "A new Polis frontend and collective-response tool" | Polis-like |
| Viewpoints.xyz | [Goodheart-Labs/polislike](https://github.com/Goodheart-Labs/polislike) | 11 | **not specified** | 2024-09-10 | "New UI experiment for a Polis-like platform" | — |
| Polis Storybook | [CivicTechTO/polis-storybook](https://github.com/CivicTechTO/polis-storybook) | 3 | *unverified* | 2025-01-14 | Storybook of Polis/forks UI components | — |
| deliberation.io | [deliberation.io](https://deliberation.io/) | — | *no public repo found* | — | Stanford Digital Economy Lab + MIT Gov Lab civic deliberation platform; "open-source and open-science" claimed | — |

Sources: Red Dwarf [README](https://cdn.jsdelivr.net/gh/polis-community/red-dwarf@main/README.md),
[license badge](https://img.shields.io/github/license/polis-community/red-dwarf),
[ungh.cc](https://ungh.cc/repos/polis-community/red-dwarf); Consider.it [README](https://raw.githubusercontent.com/Considerit/ConsiderIt/master/README.md),
[license badge](https://img.shields.io/github/license/Considerit/ConsiderIt); Harmonica
[README](https://raw.githubusercontent.com/harmonicabot/harmonica-web-app/master/README.md); Agora/Nexus/Metropolis/Viewpoints/Storybook
via ungh.cc per repo; deliberation.io via the [site](https://deliberation.io/).

**Discovery hub:** [Awesome Polis](https://patcon.github.io/awesome-polis/) (plus
[/forks](https://patcon.github.io/awesome-polis/forks/) and [/misc](https://patcon.github.io/awesome-polis/misc/))
is the community index of every Pol.is fork, frontend and academic extension — the best single place
to keep scanning.

**Notable research artefact for this exact problem:** *"Using LLMs to Structure and Visualize Policy
Discourse"* (Sukthankar et al., **Best Paper, 4th International Workshop on Democracy and AI /
Democrai 2024**, DARPA-funded) — described by Awesome Polis as *"a unique approach to visualizing
opinion data gathered from the Polis online platform in which LLMs are used to generate positions and
structure the data into argument maps"*
([Awesome Polis listing](https://patcon.github.io/awesome-polis/), PDF:
[ial.eecs.ucf.edu/pdf/Sukthankar-Democrai2024.pdf](https://ial.eecs.ucf.edu/pdf/Sukthankar-Democrai2024.pdf)).
**PDF body not fetched** (unsupported content type) — no code link was listed.

### Two "compute the axis yourself" building blocks worth calling out

1. **Red Dwarf** (MPL-2.0, 25★, active, on PyPI as `red-dwarf`) is the only library found that
   reproduces a Pol.is-style opinion-space projection as a *reusable dependency* — `pip install red-dwarf`
   ("Polis" pipeline = PCA + KMeans; "Agora" pipeline adds Benjamini-Hochberg statement selection and
   Simes' p-value combination), with `red-dwarf[plots]` for matplotlib output. It **consumes a vote
   matrix / Pol.is conversation URL**, not raw text.
2. **Pol.is exported `participants-votes.csv`** already contains a `Group ID` per participant
   ([Data Export](https://pol-is.github.io/polis-documentation/data/Export.html)) — so if votes exist,
   group counts and percentages (the parent's requirement) are a one-line aggregation.

---

## Gap analysis — what must be custom-built

| Requirement | Off-the-shelf? | What is missing |
|---|---|---|
| Opinion groups with **count + percentage** | **Yes, if votes exist** — Pol.is `participants-votes.csv` carries `Group ID`; math blob `group-clusters` | For text-only inputs, you must define groups (= clusters) and count members yourself |
| **1-D ordered opposition axis** | **No — nothing found** | Pol.is yields an *unlabelled 2-D PCA* projection; TttC yields *unordered* semantic clusters; Jigsaw yields topics/opinions with no ordering. The scalar "how opposed is A to B" coordinate does not exist in any of these projects |
| Rendering "spectrum with proportional bars" | **Partly** | Vega-Lite `bar_diverging_stack_transform` is copy-paste ready for the bars; but you own the data shaping, the neutral-band convention, and the axis labels |
| **"Stance overview table"** | **No** | Nearest precedents are bespoke: Pol.is admin comment tables (Agrees/Disagrees per comment), Jigsaw `report_ui` topic/opinion tables. No packaged component found |
| 2-D opinion/argument map | **Yes** | Pol.is (votes), TttC `scatter` pipeline + the Democrai-2024 argument-map work (text) — all as pipelines/apps, not components |
| Reusable front-end chart component | **No** | No maintained Likert/spectrum component; `react-likert` is 7★ and 7.5 yrs dormant. Vega-Lite or nivo + custom code is the pragmatic path |

### How the ordering axis would have to be computed (three viable routes)

1. **First principal component of a vote matrix** (the Pol.is family). Cheap, principled, and
   reproducible — `red-dwarf` does it directly. Requires agree/disagree votes.
2. **LLM-assigned stance scores**: have the model place each group's position statement on a
   pre-declared axis (e.g. −100…+100). Works with pure text; needs a defined axis and a validation pass.
3. **Pairwise "how opposed are A and B" → 1-D scaling (MDS / ordinal embedding).** Most faithful to
   "ordered by how opposed they are", most expensive and least deterministic.

### Licence warnings that affect a web front-end

- **Polis and Consider.it and Harmonica are AGPL-3.0.** Self-hosting Pol.is behind a network service
  triggers AGPL's network-copyleft obligation (Pol.is adds "additional permission under section 7" —
  see [LICENSE](https://github.com/compdemocracy/polis/blob/main/LICENSE), linked from the
  [README](https://raw.githubusercontent.com/compdemocracy/polis/main/README.md)).
- **Red Dwarf is MPL-2.0** (file-level copyleft — safer to link against than AGPL).
- **tttc-light-js and Jigsaw sensemaking-tools are Apache-2.0** — the most permissive of the civic-tech
  options reviewed. (The archived `talk-to-the-city-reports` `scatter/` pipeline is AGPL-3.0.)
- **`politicaltests/polcomp` has no LICENSE file** → unlicensed/all-rights-reserved by default.

---

## Unverified / could not confirm

- **Exact Pol.is star count from GitHub itself** — `api.github.com` returned 403 all session.
  ungh.cc gave 1207; shields.io independently rendered "1.2k" (consistent).
- **Pol.is math-overview wiki details** (`base-clusters` K=100, `group-clusters` silhouette) — cited
  from the indexed wiki page; `github.com/compdemocracy/polis/wiki/math-overview` did not fetch
  (github.com HTML blocked). Reported as-is, not independently re-read.
- **Consider.it's exact chart type** — `consider.it/tour` returned only a title stub ("the only forum
  to visually summarize what your community thinks and why"); the detailed visualization description
  could not be read. The repo self-describes as "for deliberation and opinion visualization";
  my claim about 4-quadrant stance views is **not** verified from a primary source.
- **Wikipedia "Opinion Space"** — could not be fetched (host resolves to a non-public IP from this
  machine), so that entry is excluded from the tables above rather than guessed at.
- **deliberation.io's source repository** — the site claims "open-source and open-science" and cites a
  2025 working paper, but I found **no public code repository**.
- **Licenses marked *unverified*** (Agora, Nexus/MindMeld, Metropolis, Polis Storybook, SapplyValues,
  10Groups, 3D-Political-Spectrum, JakeLerner/spectrum, robdongas/likert-charts,
  tnibir/D3-Local-Chart-Templates) — not fetched.
- **`Craig-Creeger/react-likert-scale` stars** — not fetched (npm metadata only).
- **`Sukthankar-Democrai2024.pdf` body** — PDFs are not fetchable by this toolchain; the description
  comes from the Awesome Polis listing, not the paper.
- **DeepWiki's claim of a Pol.is export processing component in sensemaking-tools** — DeepWiki pages
  are JS-rendered and returned only "Loading…"; the claim comes from the search-result snippet.
- **`frappe/gantt` npm naming** — `ungh.cc/repos/frappe/frappe-gantt` returns 404; the correct repo
  path is `frappe/gantt` (verified).
