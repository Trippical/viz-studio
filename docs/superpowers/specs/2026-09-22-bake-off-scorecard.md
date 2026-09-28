# Renderer bake-off scorecard

Spec: `2026-09-22-viz-site-design.md` section 5.2 (bake-off) and 12.3 (renderer
attack surface is a scored criterion). Measured on 2026-09-23 from the Plan 2
build (`web/dist`, built from HEAD `79fd3bd` plus this task's own files).
Blank columns are for the reviewer.

## How to review

1. From the repo root: `cd web && npm run build && cd ..` then
   `VIZ_WEB_DIST=web/dist .venv/Scripts/viz-server` (bash) or, in PowerShell,
   `$env:VIZ_WEB_DIST = "web/dist"; .venv/Scripts/viz-server`.
2. Open `http://127.0.0.1:8000/d/bakeoff/vega-lite`, `/d/bakeoff/plotly` and
   `/d/bakeoff/echarts`. Each has the same four tiles: a monthly time series,
   a stat tile, a quarterly grouped bar, and a 200,000-row parquet chart
   aggregated in the browser.
3. Use the Period, Days and Region controls on each. Hover for tooltips.
   Resize the window.
4. Open one chart from each dashboard on its own page (`/c/bakeoff/<renderer>/time-series`).
5. Score 1 (poor) to 5 (excellent) in the blank columns, then write the
   decision at the bottom.

## Measured

| Renderer | Lazy chunk (KiB) | Sanitizer rules | time-series spec lines | grouped-bar spec lines | order-lines spec lines | Smoke test |
|---|---|---|---|---|---|---|
| vega-lite | 841 | 10 | 47 | 44 | 32 | pass |
| plotly | 4,727 | 10 | 33 | 27 | 25 | pass |
| echarts | 1,108 | 12 | 26 | 25 | 23 | pass |

Shared, loaded lazily and reused by all three renderers on a page:

| Asset | Size (KiB) |
|---|---|
| DuckDB wasm (`duckdb-eh-*.wasm`) | 33,440 |
| DuckDB worker (`duckdb-browser-eh.worker-*.js`) | 755 |
| DuckDB glue JS (`duckdb-*.js`, non-worker) | 201 |
| Self-hosted parquet extension (`duckdb/v1.4.3/wasm_eh/parquet.duckdb_extension.wasm`, served outside `dist/assets`, exact size 3,045,039 bytes) | 2,974 |
| Main bundle (`index-*`) | 439 |

Notes on the measurements:

- "Lazy chunk" is the renderer library plus its adapter as Vite emitted it; it
  loads only when a page contains a chart with that renderer. Numbers are
  from `node scripts/chunk-sizes.mjs` reading `web/dist/assets`.
- "Sanitizer rules" counts the entries in each sanitizer's `RULES` list, which
  is the list of things the adapter has to refuse or rewrite to be safe under
  the site CSP. Fewer rules with the same guarantees means a smaller attack
  surface to maintain. Counts come from `node scripts/spec-lines.mjs` reading
  each sanitizer's `RULES: readonly string[]` block directly, not from the
  original task brief's numbers: review rulings after the brief was written
  added rules to all three sanitizers (Vega-Lite `datasets` rejection;
  ECharts `image` key and `image://` string rejection plus explicit `tooltip:
  false` handling; Plotly `customdata` escaping and `<a` anchor-tag
  rejection), so the measured counts differ from any number written down
  earlier.
- "Spec lines" is the pretty-printed size of the same chart written for each
  renderer: a rough proxy for authoring ergonomics for the publishing skill.
- Grouping: Vega-Lite groups by an encoding (`color`); Plotly and ECharts need
  the `split` convention this plan added to their adapters.
- The DuckDB wasm, worker and self-hosted parquet extension are listed
  separately from each renderer's own chunk because they load lazily (only
  when a page has a large-lane chart) and are shared across all three
  renderers on the same page, not duplicated per renderer. The extension
  file lives under `web/public/duckdb/` and is copied to `web/dist/duckdb/`
  rather than into `dist/assets`, so `chunk-sizes.mjs`, which only scans
  `dist/assets`, does not include it in the `duckdb` group total; it is
  measured separately here with `ls -la`.
- "Smoke test" is the Playwright suite (`npm run e2e`), which exercises all
  three dashboards together, not per renderer; "pass" here means that
  renderer's dashboard and single-chart page passed in that run. All 5 tests
  passed in the run this scorecard is built from (1 vega-lite dashboard test,
  1 plotly dashboard test, 1 echarts dashboard test, 1 single-chart test, 1
  missing-dashboard error-card test), with no CSP violations, no foreign
  requests and no failed requests. The browser DuckDB build lacks
  `json_serialize_sql`; at init the runtime logs a warning ("duckdb:
  json_serialize_sql is unavailable in this build; relying on the syntax
  check and subquery wrapping") rather than an error, and this is expected
  and does not fail the smoke test or any dashboard.
- Select-filter values reach DuckDB through prepared, parameterized `INSERT`
  statements into a temp table, not through Arrow temp tables: `apache-arrow`'s
  table builder compiles its null-bitmap validity checker with the `Function`
  constructor, which the site's CSP (no `unsafe-eval`) forbids. See
  `web/src/data/duckdb.ts`.

## Reviewer

| Renderer | Visual quality (1-5) | Tooltips and hover (1-5) | Controls feel responsive (1-5) | Resize behaviour (1-5) | Notes |
|---|---|---|---|---|---|
| vega-lite | | | | | |
| plotly | | | | | |
| echarts | | | | | |

## Decision

Winner: **Vega-Lite** (decided 2026-09-28 by the user; the scoring columns
above were not filled in).

Reason: it covers the everyday business charts natively (line, area, bar,
stacked, combo, heatmap, box plot, small multiples, reference lines), has the
smallest lazy chunk and a short sanitizer rule list, needs no custom `split`
or column-binding convention, and is the most reliable format for Claude to
write. It read cleanest in small dashboard tiles. It has no treemap, sankey,
network graph or gauge. A capability comparison and interactive examples of a
network graph and a gauge were reviewed alongside the dashboards.

Note: the first screenshots showed the Vega-Lite tiles nearly empty. That was
a site bug, not the library: vega-embed's injected `.vega-embed { position:
relative }` beat `.tile-mount` and collapsed every mount to 21px. Fixed by
raising the selector to `.tile-body > .tile-mount`; the smoke test now asserts
every chart fills its tile.

Paths for the chart families Vega-Lite lacks, cheapest first: (1) site-owned
tile types like `stat` (gauge and bullet are ~150 lines of plain SVG);
(2) allow full Vega specs, which are already bundled (vega-lite compiles to
vega) and add force-directed networks, treemap, sunburst, tree and custom
shapes, at the cost of extending the sanitizer to Vega's signal and event
features; (3) restore a second renderer from git history for one family.

Done after the decision: the Plotly and ECharts adapters, sanitizers, tests,
sample folders, dashboards, manual chunks, npm dependencies, Python checks and
`renderer` enum values were removed (branch `vega-lite-only`). Plan 3b writes
the skill's Vega-Lite authoring guide.
