# Open-Source Tooling Research: Ideological Spectrum Visualizations & Charting Libraries

**Report date:** 2026-09-27 · **Maintenance status assessed as of this date.**
**Method:** `ungh.cc` proxy for repo metadata (star counts, `pushedAt`); `registry.npmjs.org` for package versions/licenses; official docs & `raw.githubusercontent.com` for specs and license text. `api.github.com` was **not** used (rate-limited/403 from this IP, as documented).

**Baseline validation:** `ungh.cc/repos/apache/echarts` returned `stars=67398`, `pushedAt=2026-09-16`, matching the provided known-good baseline, so the proxy is trustworthy for this session.

---

## TOPIC A — Political compass / opinion spectrum web visualizations

### A1. Project metadata

| Project | Live site | Source repo | Stars | License | Last push | Maintained @ 2026-09-27 |
|---|---|---|---|---|---|---|
| polcomp | [politicaltests.github.io/polcomp](https://politicaltests.github.io/polcomp/) | [politicaltests/polcomp](https://github.com/politicaltests/polcomp) | 1 | **None present** (no `LICENSE` file in repo listing → unlicensed) | 2022-03-05 | **Dormant ~4.5 yrs** |
| 8values | [8values.github.io](https://8values.github.io/) | [8values/8values.github.io](https://github.com/8values/8values.github.io) | 1111 | **MIT** ([LICENSE](https://raw.githubusercontent.com/8values/8values.github.io/master/LICENSE)) | 2023-07-28 | **Dormant ~3.2 yrs** |
| 9Axes | [9axes.github.io](https://9axes.github.io/) | [9Axes/9axes.github.io](https://github.com/9Axes/9axes.github.io) | 58 | **MIT** ([LICENSE](https://raw.githubusercontent.com/9Axes/9axes.github.io/master/LICENSE)) | 2021-11-09 | **Dormant ~4.9 yrs** |
| SapplyValues | [sapplyvalues.github.io](https://sapplyvalues.github.io/) | [SapplyValues/SapplyValues.github.io](https://github.com/SapplyValues/SapplyValues.github.io) | 75 | *unverified* | 2024-07-06 | Semi-dormant ~1.2 yrs |
| 10Groups | [politicaltests.github.io](https://politicaltests.github.io/index.html) | [10Groups/10groups.github.io](https://github.com/10Groups/10groups.github.io) | 35 | *unverified* | 2023-06-19 | **Dormant ~3.3 yrs** |
| 3D-Political-Spectrum | — | [JawnGrimm/3D-Political-Spectrum](https://github.com/JawnGrimm/3D-Political-Spectrum) | 0 | *unverified* | 2025-12-08 | Stale ~9.7 mo (one-shot AI-generated) |
| spectrum (cosponsorship) | — | [JakeLerner/spectrum](https://github.com/JakeLerner/spectrum) | 1 | *unverified* | 2015-10-21 | **Abandoned ~11 yrs** |

Star counts and `pushedAt` values above came from `https://ungh.cc/repos/<owner>/<repo>` (e.g. [ungh.cc/repos/8values/8values.github.io](https://ungh.cc/repos/8values/8values.github.io)).

### A2. Exactly what each renders

- **polcomp** — A **2-D political compass explorer**, *not a quiz*: "an interactive political compass, with 169 political ideologies plotted on it," with descriptions and lists of people/views per ideology. Axes are Economic (Left–Right) × Governmental (Authoritarian–Libertarian), with four named quadrants ([site text](https://politicaltests.github.io/polcomp/)). Repo files: `index.html`, `compass.html`, `ideologies.js`, `ideologies.js`, `style.css`, `img/quadrants.png` ([file listing](https://ungh.cc/repos/politicaltests/polcomp/files/main)).
- **8values** — Quiz producing **8 independent axis percentages** (Equality/Markets, Nation/Globe, Liberty/Authority, Tradition/Progress) plus an ideology label. Files: `index.html`, `quiz.html`, `results.html`, `questions.js`, `ideologies.js`, `style.css` ([file listing](https://ungh.cc/repos/8values/8values.github.io/files/master)).
- **9Axes** — Same 8values UI generalized to **9 axes**; includes a Russian translation under `ru/`. Same flat file layout ([file listing](https://ungh.cc/repos/9Axes/9axes.github.io/files/master)).
- **SapplyValues** — 2-D compass combining the Sapply question set with 8values' UI ([repo](https://github.com/SapplyValues/SapplyValues.github.io)).
- **10Groups** — Quiz scoring **10 category compasses** ([site](https://politicaltests.github.io/index.html)).
- **JawnGrimm/3D-Political-Spectrum** — "An interactive 3D visualization of political ideologies… rotating the cube… click on points to get an AI-generated summary… answer a questionnaire to plot your own position." README states: "Generated in Google AI Studio w/ assistance from Claude" ([repo](https://github.com/JawnGrimm/3D-Political-Spectrum/blob/main/README.md)).
- **JakeLerner/spectrum** — Analyzes congressional cosponsorship records to place politicians on arbitrary **1-D issue spectrums** ([repo](https://github.com/JakeLerner/spectrum)).

### A3. **KEY FINDING — none of these is a reusable library**

**Every Topic A project is a hardcoded, single-purpose standalone site. Not one exposes a reusable JS library with a documented API.** Evidence:

1. **No package manifest, no library entry point.** The file listings for polcomp, 8values and 9axes contain only `*.html`, `*.js` data files, `style.css`, images, `README.md` and `LICENSE`. There is **no `package.json`, no `src/` module graph, no build config, no exported API** ([polcomp](https://ungh.cc/repos/politicaltests/polcomp/files/main), [8values](https://ungh.cc/repos/8values/8values.github.io/files/master), [9axes](https://ungh.cc/repos/9Axes/9axes.github.io/files/master)).
2. **The `.js` files are data, not code libraries.** `questions.js` and `ideologies.js` are plain global-scope data tables loaded directly by `<script>` from the HTML pages. They are copyable as *data*, but they are not importable modules and carry no API surface.
3. **Rendering is bespoke per page.** The compass/scoring logic is inlined into the page templates; there is no charting abstraction, no configuration object, no renderer you can call with your own data.
4. **No releases, no npm publication, no versioning.** None of these appear on npm.

**Practical reuse verdict:** only the **MIT-licensed data files** from 8values/9axes are safe to lift. Any actual *visualization* must be rebuilt. For a reusable rendering layer, Topic B libraries are the only real option.

---

## TOPIC B — Charting libraries for an "ordered stance axis with proportional bars"

### B1. Library metadata

| Library | Repo | Stars (ungh.cc) | License | Last push | Maintained @ 2026-09-27 |
|---|---|---|---|---|---|
| Apache ECharts | [apache/echarts](https://github.com/apache/echarts) | **67398** ([ungh](https://ungh.cc/repos/apache/echarts)) | Apache-2.0 ([npm 6.1.0](https://registry.npmjs.org/echarts/latest)) | 2026-09-16 | **Very active** |
| D3 | [d3/d3](https://github.com/d3/d3) | **113768** ([ungh](https://ungh.cc/repos/d3/d3)) | ISC ([npm 7.9.0](https://registry.npmjs.org/d3/latest)) | 2026-05-28 | Active (~4 mo) |
| Vega-Lite | [vega/vega-lite](https://github.com/vega/vega-lite) | **5497** ([ungh](https://ungh.cc/repos/vega/vega-lite)) | BSD-3-Clause ([npm 6.4.3](https://registry.npmjs.org/vega-lite/latest)) | 2026-09-24 | **Very active** |
| plotly.js | [plotly/plotly.js](https://github.com/plotly/plotly.js) | **18347** ([ungh](https://ungh.cc/repos/plotly/plotly.js)) | MIT ([npm 4.1.1](https://registry.npmjs.org/plotly.js/latest)) | 2026-09-25 | **Very active** |
| nivo (React) | [plouc/nivo](https://github.com/plouc/nivo) | **14102** ([ungh](https://ungh.cc/repos/plouc/nivo)) | MIT ([npm @nivo/bar 0.99.0](https://registry.npmjs.org/@nivo/bar/latest)) | 2026-07-21 | Active |
| Frappe Gantt | [frappe/gantt](https://github.com/frappe/gantt) | **6128** ([ungh](https://ungh.cc/repos/frappe/gantt)) | MIT ([npm frappe-gantt 1.2.2](https://registry.npmjs.org/frappe-gantt/latest)) | 2026-06-18 | Active |

> Note: the npm package is `frappe-gantt` while the repo is `frappe/gantt`. `ungh.cc/repos/frappe/frappe-gantt` returns **404** — use `frappe/gantt`.

### B2. Visual-capability matrix

| Chart type | ECharts | D3 | Vega-Lite | plotly.js | nivo | Notes |
|---|---|---|---|---|---|---|
| **Diverging stacked bar** | Adapt (negative-value stack) | Custom | ✅ **native-ish recipe** | Adapt (`barmode:'relative'`) | ✅ recipe | see B3 |
| **Likert chart** | Adapt | Custom | ✅ via diverging recipe | Adapt | ✅ diverging recipe | no first-class "likert" type anywhere |
| **Gantt-style ordered bands** | Custom series | Custom | ❌ not native | Adapt (`bar` + `base`) | ❌ | dedicated lib: Frappe Gantt |
| **Theme river** | ✅ first-class `themeRiver` | Custom | ❌ not native | ❌ not native | ✅ `@nivo/stream` | |
| **Sankey** | ✅ `sankey` | `d3-sankey` | ❌ not native | ✅ | ✅ `@nivo/sankey` | |
| **2-D scatter w/ quadrants** | ✅ `scatter` + `markArea` | ✅ | ✅ `point` + layers | ✅ `scatter` | ✅ `@nivo/scatterplot` | |

### B3. Ready-made Likert / diverging stacked bar recipes

| Recipe | Source URL | Status | Verdict |
|---|---|---|---|
| **Vega-Lite "Diverging Stacked Bar Chart (with Neutral Parts)"** | [vega.github.io/vega-lite/examples/bar_diverging_stack_transform.html](https://vega.github.io/vega-lite/examples/bar_diverging_stack_transform.html) | HTTP 200, **v6 schema** | ✅ **Copy-paste ready.** Full JSON spec retrieved: `signed_percentage` calculate → `stack` → `joinaggregate` offset → `nx`/`nx2` for `x`/`x2`. Swap in your data. |
| **nivo "Stacked diverging bar chart"** | [nivo.rocks/storybook/?path=/story/bar--diverging-stacked](https://nivo.rocks/storybook/?path=/story/bar--diverging-stacked) | Listed under [Bar docs → Recipes](https://nivo.rocks/bar/) | ✅ First-class, **needs adaptation** (React props, not a copy-paste spec) |
| nivo "Grouped diverging bar chart" | [storybook: bar--diverging-grouped](https://nivo.rocks/storybook/?path=/story/bar--diverging-grouped) | Listed in [Bar docs](https://nivo.rocks/bar/) | Needs adaptation |
| **plotly.js relative barmode** | [plotly.com/javascript/bar-charts/#bar-chart-with-relative-barmode](https://plotly.com/javascript/bar-charts/) | Live, runnable `barmode: 'relative'` example | ⚠️ **Needs adaptation** — no dedicated Likert/diverging example exists; also `base:` example for offset bars |
| **ECharts negative/stacked bar** | [echarts.apache.org/en/option.html#series-bar](https://echarts.apache.org/en/option.html) | SPA doc (chart config reference) | ⚠️ **Custom build** — ECharts has **no** built-in diverging/Likert series; assemble from stacked negative values |
| ECharts Theme River | [example](https://echarts.apache.org/examples/en/editor.html?c=themeRiver-basic) · [option doc (source MD)](https://github.com/apache/echarts-doc/blob/master/en/option/series/themeRiver.md) | Both live | ✅ Native chart type (`lib/chart/themeRiver`) |
| ECharts Gantt (custom series) | [editor.html?c=custom-gantt-flight](https://echarts.apache.org/examples/en/editor.html?c=custom-gantt-flight) · [custom-series guide](https://echarts.apache.org/handbook/en/how-to/custom-series/) | Live | ⚠️ Custom series, not a core chart type |
| **D3 diverging stacked bar (Likert)** | [wpoely86/D3.js-Diverging-Stacked-Bar-Chart](https://github.com/wpoely86/D3.js-Diverging-Stacked-Bar-Chart) | 11 stars, last push **2014-12-21** | ⚠️ Explicitly built for a 5-point Likert scale, but **abandoned ~11 yrs**; reference only |
| D3 Local Chart Templates (147 templates) | [tnibir/D3-Local-Chart-Templates/021-diverging-stacked-bar-chart](https://github.com/tnibir/D3-Local-Chart-Templates/tree/main/021-diverging-stacked-bar-chart) | 0 stars, created/pushed **2026-08-06** | ⚠️ Very new, zero adoption — unproven |

### B4. Dedicated OSS React/Vue Likert components

| Component | Source | Stars | License | Last activity | Verdict |
|---|---|---|---|---|---|
| **react-likert** (jasonphillips) | [github](https://github.com/jasonphillips/react-likert) · [npm](https://www.npmjs.com/package/react-likert) | 7 ([ungh](https://ungh.cc/repos/jasonphillips/react-likert)) | MIT ([npm 0.8.0](https://registry.npmjs.org/react-likert/latest)) | 2019-03-28 | ⚠️ Closest match: **React + D3 diverging Likert bars inside a real `<table>`**, with ARIA tags. **Dormant ~7.5 yrs**, 7 stars — use as a code reference, not a dependency. |
| **react-likert-scale** (Craig-Creeger) | [repo](https://github.com/Craig-Creeger/react-likert-scale) · [npm](https://www.npmjs.com/package/react-likert-scale) | *unverified* | CC0-1.0 ([npm 4.1.2](https://registry.npmjs.org/react-likert-scale)) | last publish **2021-06-02** | ❌ **Not a chart.** ~5 kB, zero-dependency **radio-button *input*** for collecting survey answers. Does not visualize distributions. |
| robdongas/likert-charts | [repo](https://github.com/robdongas/likert-charts) | 0 ([ungh](https://ungh.cc/repos/robdongas/likert-charts)) | *unverified* | 2024-04-22 | Demo repo showing ApexCharts boxplots + stacked bars for 5-/7-point Likert. Reference only. |

**No maintained, dedicated, drop-in React/Vue Likert *chart* component exists.** The two real options are Vega-Lite (declarative, no React needed) or nivo (React-native, documented recipe).

---

## What is missing / must be custom-built

- **There is no reusable JS library for ideological-spectrum visualization.** All Topic A projects are unmaintained single-purpose sites (newest meaningful push: 2023-07-28 for 8values; polcomp 2022-03-05). Only 8values/9axes **MIT data files** are safely liftable; every renderer must be written from scratch.
- **No library has a first-class "Likert" or "ordered stance axis" chart type.** Vega-Lite's `bar_diverging_stack_transform` recipe is the single genuinely copy-paste-ready artifact found; it is a *spec pattern*, not a packaged component — you still own the data shaping for your stance scale.
- **Neutral-category handling is your responsibility.** Only the Vega-Lite recipe encodes the standard Likert convention of splitting the neutral band across the 0% mark (`semi-neutral` offset math). ECharts, plotly.js and nivo give you primitives, not this convention.
- **Gantt-style ordered bands.** Only Frappe Gantt provides this out of the box (MIT, 6128★, active). ECharts needs a custom series; plotly.js has no Gantt trace type and must fake it with `bar` + `base`.
- **Sankey in Vega-Lite is absent** — you would need Vega or a different library. (A community Vega-Lite Sankey demo exists but is not a native chart type: [msquinn/vega-demo](https://github.com/msquinn/vega-demo).)
- **Quadrant overlays** must be composed manually everywhere except ECharts (`markArea`/`markLine`) and Vega-Lite (layered specs).

## Unverified

Numbers/facts I could **not** confirm and did not guess:

- **License** for `politicaltests/polcomp` — no `LICENSE` file exists in the repo's file listing, so it is **unlicensed by default**; I could not confirm any grant of rights. Treat as all-rights-reserved.
- **License** unverified for: `SapplyValues/SapplyValues.github.io`, `10Groups/10groups.github.io`, `JawnGrimm/3D-Political-Spectrum`, `JakeLerner/spectrum`, `robdongas/likert-charts`, `tnibir/D3-Local-Chart-Templates`.
- **Star count** for `Craig-Creeger/react-likert-scale` — not fetched (only npm registry metadata verified: v4.1.2, CC0-1.0, last publish 2021-06-02).
- **Exact `pushedAt` precision**: ungh.cc values are reported as-is; I did not cross-check against `api.github.com` (403 from this IP).
- **ECharts official option-doc deep links** (`echarts.apache.org/en/option.html#series-*`) are client-side anchors on an SPA; I verified the page loads and the nav link resolves, but not each individual anchor. The `echarts-doc` GitHub Markdown source is cited where the anchor could not be fetched.
- **Vega-Lite Sankey absence** is stated from the absence of a native Sankey mark in the example gallery/docs I reviewed, not from an explicit upstream statement.
