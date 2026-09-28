# viz-site

A self-hosted viewer over a folder in an object store. Agents and people publish
charts and dashboards into that folder through a paved path; the site only reads.

Setting it up at work (fresh clone, AWS, Databricks, deployment):
[`docs/work-setup.md`](docs/work-setup.md).

## Trust assumptions, read these first

- Publishing a chart or dashboard means sharing it with every person who can
  reach the site. There are no per-object permissions.
- Folders are organization, not permission.
- Dashboard filters are a view, not a restriction. Any viewer can download a
  chart's full data file.
- Everything in the bucket is treated as untrusted content: the site sanitizes
  what it renders and never runs SQL against a warehouse.

## Development

    python -m venv .venv && . .venv/Scripts/activate   # or .venv/bin/activate
    pip install -e ".[dev]"
    python -m pytest
    viz-server                                          # serves ./sample-bucket on 127.0.0.1:8000

## Publishing (the paved path)

    viz stage --from rows.csv --id sales/emea/revenue   # stage a csv, json or parquet file
    viz stage --from rows.csv --id sales/emea/revenue --drop-columns a,b --staging DIR
    viz query --sql @q.sql --id sales/emea/revenue      # run SQL on Databricks and stage the result
    viz query --sql @q.sql --id sales/emea/revenue --drop-columns a,b --staging DIR
    viz validate .viz-staging/charts/sales/emea/revenue # schema, data file, columns, author, id conflicts
    viz preview                                         # serve ./.viz-staging on 127.0.0.1:8000
    viz publish .viz-staging/charts/sales/emea/revenue  # validate, then upload (data first, then chart.json)
    viz publish .viz-staging/charts/sales/emea/revenue --allow-row-level  # large-lane (row-level) charts
    viz publish .viz-staging/dashboards/sales/board.json
    viz new-dashboard sales/board --chart sales/emea/revenue  # stage a new dashboard with author stamped
    viz pull-dashboard sales/board                      # copy a published dashboard into staging to edit
    viz install-skill                                   # copy the publish-viz skill to ~/.claude/skills
    viz move sales/emea/revenue sales/emea/revenue-monthly --yes

The staging directory `./.viz-staging` mirrors the bucket, so `viz preview` is
the real server pointed at it. `viz query` needs `pip install -e ".[databricks]"`
(from a checkout) and `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID`; nothing
else in the package reads them. Publisher settings: `VIZ_AUTHOR` (overrides the
AWS caller identity when set; the Databricks user from `viz query` always wins,
and `viz validate` confirms it with Databricks when the `DATABRICKS_*` variables
are set; author is attribution, not authentication), `VIZ_QUERY_DENY` (comma-separated
catalogs or `catalog.schema` that `viz query` refuses), `VIZ_PII_PATTERN`,
`VIZ_STAGING_DIR`. `--force` and `--yes` are flags only.

The `publish-viz` Claude skill (`skills/publish-viz/`) teaches an agent this
whole path, with a Vega-Lite authoring guide. Every chart form in the guide
is an example file under `skills/publish-viz/examples/`, published by
`sample-bucket/generate.py` as the gallery dashboard `/d/examples/gallery`.
`viz install-skill` copies the skill to `~/.claude/skills/publish-viz/`
(`--dest DIR` for another location).

Design: `docs/superpowers/specs/2026-09-22-viz-site-design.md`.

## Front end

The viewer is a Vite + React + TypeScript app in `web/`. Node 24 and npm are
required. From `web/`:

    npm install
    npm run dev          # Vite on http://127.0.0.1:5173, proxies /api to the server on :8000
    npm run build        # writes web/dist; serve it with VIZ_WEB_DIST=web/dist viz-server
    npm test             # vitest unit tests
    npm run typecheck
    npm run e2e          # Playwright smoke test: builds, starts viz-server, drives Chromium

Charts render with Vega-Lite (plus the built-in `stat` tile). The Vega
libraries, the DuckDB-WASM worker and its wasm are bundled and served from the
site. Nothing loads from a CDN. Chart specs from the bucket are sanitized
before they are mounted; see `web/src/renderers/vegaLiteSanitize.ts` and spec
section 12.3. Vega-Lite won the bake-off against Plotly and ECharts; the
decision and measurements are in
`docs/superpowers/specs/2026-09-22-bake-off-scorecard.md`.
