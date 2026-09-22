# viz-site: Design Spec

Date: 2026-09-22
Status: Draft for review

## 1. Purpose

A self-hosted, open-source visualization site that replaces Databricks' built-in
dashboards for a team that finds them limiting. The site is a viewer over a
folder in an object store (S3). Agents and humans publish charts and dashboards
into that folder through a paved path: a Claude skill plus a Python CLI. The
site never runs SQL against Databricks. A refresher, part of the same app, can
re-run a chart's stored SQL later and overwrite its data file.

Users: a team inside a company VPC, reached only over VPN. No app-level auth in
v1. Developed and proven on a personal AWS account first.

## 2. Scope

### In scope for v1

- The contract: bucket layout and JSON Schemas for charts, dashboards, folders.
- The viewer: FastAPI server plus a React front end, reading from S3 or a local
  folder.
- Folders and hierarchies for both charts and dashboards.
- Viewer-side controls (date range, select, number range) that filter published
  data in the browser.
- Two data lanes: small (JSON) and large (parquet through DuckDB-WASM).
- Chart renderer bake-off: Vega-Lite, Plotly, ECharts, with the same samples in
  each. One winner is kept.
- The publisher: a `viz` CLI and a `publish-viz` skill usable from Databricks
  Genie Code and local Claude Code.
- A refresher scaffold inside the same app, off by default.
- Helm chart for a small k8s deployment.

### Out of scope for v1

- App-level authentication or per-object permissions.
- Any write API on the server. Publishing is only through the CLI to storage.
- Chart version history.
- The refresher's actual scheduling and execution behavior (v2, its own spec).
- Storage backends other than S3 and local filesystem. The storage interface is
  small so others can be added later.

## 3. Architecture

One repository, one Python package, one container image.

```
Databricks (Genie Code / notebook / local Claude Code)
   |  publish-viz skill  ->  viz CLI (query | stage | validate | publish | move | preview)
   v
S3 bucket  <root>/charts/...  <root>/dashboards/...
   ^                                   |
   |  boto3, pod IAM role              |  read-only JSON API + static files
   |                                   v
k8s pod: FastAPI app  --serves-->  React front end (browser, over VPN)
   |
   +-- refresher (same process, background scheduler, disabled by default)
```

Components:

- **storage**: interface with `list(prefix)`, `get(key)`, `put(key, bytes,
  content_type)`, `delete(key)`, `copy(src, dst)`. Backends: `s3` (boto3) and
  `local` (filesystem). Selected by `VIZ_STORAGE`.
- **server**: FastAPI. Serves the built front end and four GET routes. Validates
  every chart.json and dashboard.json against the schemas on read.
- **publish**: the `viz` CLI. Produces, validates, and uploads bundles.
- **refresh**: scaffold only in v1. A scheduler that, when enabled, will iterate
  charts with a `source` block and re-run them.
- **web**: Vite + React + TypeScript. Four screens. Renderer adapters.

## 4. The contract

### 4.1 Layout

All keys live under one root prefix, `VIZ_ROOT_PREFIX` (default `viz/`).

```
<root>/
  charts/
    <chart-id>/chart.json
    <chart-id>/data.json        small lane, or
    <chart-id>/data.parquet     large lane
    <folder>/_folder.json       optional, any depth
  dashboards/
    <dashboard-id>.json
    <folder>/_folder.json       optional, any depth
```

Ids are paths. An id matches `^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*$`:
lowercase slugs separated by single slashes, no leading or trailing slash, no
`.` segments. The chart id `sales/emea/revenue-by-region` lives at
`charts/sales/emea/revenue-by-region/chart.json`. Dashboards reference charts by
full id, so a chart in one folder can appear on a dashboard in another.

Writers publish the data file first, then chart.json, so a reader never sees a
spec whose data is missing.

### 4.2 chart.json

```json
{
  "schema_version": 1,
  "id": "sales/emea/revenue-by-region",
  "title": "EMEA revenue by region, monthly",
  "description": "Markdown. Optional.",
  "tags": ["sales", "emea"],
  "author": "someone@company.com",
  "created_at": "2026-09-22T10:00:00Z",
  "updated_at": "2026-09-22T10:00:00Z",
  "renderer": "vega-lite",
  "spec": { "...renderer-native JSON, data omitted..." },
  "data": {
    "path": "data.json",
    "format": "json",
    "lane": "small",
    "rows": 1440,
    "bytes": 98304,
    "columns": [
      { "name": "month", "type": "date" },
      { "name": "region", "type": "string" },
      { "name": "revenue", "type": "number" }
    ]
  },
  "aggregate": null,
  "source": {
    "kind": "databricks-sql",
    "sql": "SELECT ...",
    "warehouse_id": "abc123",
    "schedule": "0 6 * * *"
  }
}
```

Field rules:

- `renderer`: during the bake-off one of `vega-lite`, `plotly`, `echarts`,
  `stat`. After the bake-off the enum shrinks to the winner plus `stat`.
- `spec`: renderer-native JSON. It must not embed data. It refers to one named
  dataset, `data`, which the viewer injects after filtering. For `stat`, the
  spec is `{ "value": "<column>", "agg": "sum|avg|min|max|count|last",
  "format": "<d3-format string>", "compare": { "column": "...", "agg": "..." } }`
  with `compare` optional.
- `data.format`: `json` (array of row objects) for small lane, `parquet` for
  large lane. Nothing else.
- `data.lane`: `small` or `large`. Small: at most 50,000 rows and 10 MB. Large:
  at most 200 MB. The CLI refuses to publish beyond the caps.
- `data.columns[].type`: one of `string`, `number`, `integer`, `boolean`,
  `date`, `timestamp`. Dates are ISO 8601 strings in JSON and native types in
  parquet. Controls bind by column name and use the type to choose a widget.
- `aggregate`: required when `lane` is `large`, must be null otherwise. A DuckDB
  SQL statement over a table named `data` that reduces rows to a drawable
  result. The viewer injects control filters as a WHERE clause on `data` before
  running it. This SQL only ever touches the published file.
- `source`: optional. Present means refreshable. Absent means one-off and the
  UI shows a "static" badge. `schedule` is a cron string and is optional.

### 4.3 dashboards/<id>.json

```json
{
  "schema_version": 1,
  "id": "sales/emea/overview",
  "title": "EMEA overview",
  "description": "Markdown. Optional.",
  "tags": [],
  "author": "...",
  "created_at": "...",
  "updated_at": "...",
  "controls": [
    { "id": "period", "type": "date-range", "label": "Period",
      "column": "month", "default": { "last": "12m" } },
    { "id": "region", "type": "select", "label": "Region",
      "column": "region", "multi": true, "default": null },
    { "id": "minrev", "type": "number-range", "label": "Revenue",
      "column": "revenue", "default": null }
  ],
  "layout": [
    { "chart": "sales/emea/revenue-by-region", "w": 8, "h": 4 },
    { "chart": "sales/emea/total-revenue", "w": 4, "h": 2 },
    { "markdown": "Notes about this page.", "w": 12, "h": 1 }
  ]
}
```

- Controls bind by column name. A chart whose data has that column is
  filtered. A chart without it is untouched. `select` options are derived from
  the union of distinct values across the charts on the page.
- Layout is a flow grid of 12 columns. Each tile is a chart reference or a
  markdown block, with width `w` (1..12) and height `h` in row units. No
  absolute coordinates.
- A tile that references a missing or invalid chart renders as an error card.
  The rest of the page renders.

### 4.4 _folder.json

```json
{ "schema_version": 1, "title": "Sales", "description": "Markdown.", "order": 10 }
```

All fields optional. Without the file, the folder shows its slug, sorted
alphabetically after any folders with an explicit `order`.

### 4.5 Schemas

JSON Schemas live in `schemas/` and are the single source of truth. The Python
CLI and server validate with them, and the front end imports the same files
for type generation. Fixtures under `tests/fixtures/` hold one valid example of
each document and one invalid example per rule.

## 5. The viewer

### 5.1 Server

FastAPI app, `viz.server`. Routes:

| Route | Returns |
|---|---|
| `GET /api/tree` | Merged tree of folders, dashboards, and charts with titles and folder metadata |
| `GET /api/dashboards/{id}` | Validated dashboard JSON |
| `GET /api/charts/{id}` | Validated chart JSON |
| `GET /api/charts/{id}/data` | The data file, streamed, with content type and ETag |
| `GET /*` | Static front end, SPA fallback to index.html |

Behavior:

- Every id is validated against the id pattern before touching storage and is
  resolved under the root prefix. No path traversal is possible.
- The tree is cached in memory with a TTL (`VIZ_TREE_TTL_SECONDS`, default 60).
- Validation failures on read return a 422 with the schema errors, and the
  front end shows them in the tile's error card.
- The refresher is started only when `VIZ_REFRESH_ENABLED=true`. In v1 it is a
  scaffold that logs which charts it would refresh and exits the tick.

Configuration (environment variables):

| Variable | Meaning |
|---|---|
| `VIZ_STORAGE` | `s3` or `local` |
| `VIZ_S3_BUCKET` | bucket name when `s3` |
| `VIZ_ROOT_PREFIX` | root prefix, default `viz/` |
| `VIZ_LOCAL_DIR` | directory when `local`, default `./sample-bucket` |
| `VIZ_TREE_TTL_SECONDS` | tree cache TTL |
| `VIZ_REFRESH_ENABLED` | start the refresher scheduler |
| `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID` | read only by `viz query` and the refresher |

IAM: the pod role gets `s3:ListBucket` and `s3:GetObject` on the root prefix.
The refresher, when enabled, additionally gets `s3:PutObject` on the same
prefix. No credentials or bucket names reach the browser.

### 5.2 Front end

Vite + React + TypeScript, built to `web/dist` and served by FastAPI.

Screens:

1. Dashboards tree (home). Folder navigation with `_folder.json` titles.
2. Dashboard page: control bar, then tiles in the flow grid.
3. Charts library tree.
4. Single chart page: the chart at full width, its description, its columns,
   its source SQL if present, and the static badge if not.

Dashboard data flow:

1. Fetch the dashboard, then every referenced chart.json in parallel.
2. Load data per chart. Small lane: fetch JSON rows into memory. Large lane:
   register the parquet file with DuckDB-WASM. DuckDB-WASM is loaded lazily,
   only when a page contains a large-lane chart.
3. Controls produce a filter set. Small lane: filter rows in TypeScript. Large
   lane: filters become a WHERE clause on `data`, prepended to the chart's
   `aggregate`, executed in DuckDB.
4. Filtered rows go to the renderer adapter named by `renderer`.

Renderer adapters: one module per renderer with a single interface,
`mount(el, spec, rows)` and `update(rows)`. Bake-off adapters: `vega-lite`,
`plotly`, `echarts`. `stat` is a plain React component. Plotly needs a
column-binding convention because its native JSON embeds arrays; the adapter
maps `{ "x": { "column": "month" } }` style references to arrays.

Bake-off samples in `sample-bucket/`: four charts written once per renderer and
one dashboard per renderer. The four: a time series with a date-range control,
a grouped bar with a multi-select, a stat tile with a comparison, and a
large-lane parquet chart with a DuckDB aggregate. After the user picks a
winner, the two other adapters, their samples, and their enum values are
removed.

Error handling: missing chart, malformed JSON, schema failure, oversized data,
renderer exception, DuckDB failure. Each yields a tile-level error card with
the chart id and the reason. Nothing at tile level takes down the page.

## 6. The publisher

### 6.1 Package layout

`viz` package with subpackages `storage`, `server`, `publish`, `refresh`.
Console script `viz` maps to `viz.publish.cli`.

### 6.2 CLI

Staging directory: `./.viz-staging/<chart-id>/` containing `chart.json` and the
data file, mirroring the bucket layout so publish is a copy.

| Command | Does |
|---|---|
| `viz query --sql <str or @file> --id <id> [--warehouse <id>]` | Runs SQL through the Databricks SQL connector, writes rows to staging, infers columns, picks the lane by the caps, writes a skeleton chart.json with the `source` block filled, prints a column summary. |
| `viz stage --from <csv/json/parquet> --id <id>` | Same as query but from an existing file. No `source` block. Also callable from Python as `viz.publish.stage(df, id)` for a pandas frame. |
| `viz validate <staging dir or dashboard file>` | Schema validation, data file present, declared columns match the file, lane caps, large-lane aggregate parses and runs in local DuckDB. For dashboards, every referenced chart id exists in storage. |
| `viz publish <staging dir or dashboard file>` | Runs validate, then uploads data first and chart.json second. Refuses on any validation failure. |
| `viz move <old-id> <new-id>` | Renames a chart or dashboard prefix in storage and rewrites references in every dashboard that pointed at it. |
| `viz preview <staging dir>` | Starts the local server against the staging directory so the chart can be opened in a browser before publishing. |

Publish modes:

- Refreshable: chart.json has `source`. Produced by `viz query`. The refresher
  may re-run it.
- One-off: no `source`. Produced by `viz stage`. Never refreshed. UI shows a
  "static" badge.

The CLI uses the same storage layer and environment variables as the server.

### 6.3 The skill

Canonical location `skills/publish-viz/SKILL.md`, also exposed at the path
Claude Code reads. The Genie Code discovery path is confirmed during
implementation, not assumed here.

Workflow the skill teaches:

1. Restate the question. Decide: one chart, or a dashboard.
2. Write the SQL. Aggregate in the warehouse so the result lands in the small
   lane. Use the large lane only when the viewer needs row-level filtering the
   warehouse cannot precompute.
3. Run `viz query` (or `viz stage` when the rows already exist). Read the
   column summary.
4. Write chart.json: pick the chart form from the data shape, bind columns,
   never embed data, keep `source` whenever there is real SQL.
5. `viz validate`. Fix. `viz preview` when unsure. `viz publish`.
6. If the chart belongs on a dashboard, create or edit the dashboard file and
   publish it too.

The skill also carries: the chart-authoring guide for the winning renderer, the
control-binding rules, lane guidelines with the caps, and anti-patterns
(publishing raw rows when a GROUP BY would do; embedding data in the spec;
omitting `source` when SQL exists).

## 7. Refresher (scaffold)

In v1 `viz.refresh` contains the scheduler entry point and a `plan()` function
that lists charts with a `source` block and their schedules. When enabled, it
logs the plan on each tick and does nothing else. The v2 spec will define
execution, overwrite semantics (data first, then chart.json with a new
`updated_at`), failure handling, and concurrency.

## 8. Testing

- Schemas: fixture-driven. One valid document per type, one invalid per rule.
- Storage: one test suite run against both backends, S3 via moto.
- CLI: end to end on the local backend: stage, validate, publish, move, read
  back through the server API. Databricks connector mocked. One opt-in
  integration test against a real warehouse when environment variables are set.
- Server: route tests with FastAPI's test client, including traversal
  rejection and 422 on invalid documents.
- Front end: component tests for filter logic and each adapter; one Playwright
  smoke test that loads a sample dashboard and asserts a control changes a
  chart.
- CI: GitHub Actions runs all suites and builds the container image.

## 9. Repository layout

```
viz-site/
  README.md  LICENSE (MIT)  pyproject.toml  Dockerfile  docker-compose.yml
  schemas/               chart.schema.json  dashboard.schema.json  folder.schema.json
  viz/                   storage/  server/  publish/  refresh/
  web/                   Vite + React + TypeScript
  skills/publish-viz/    SKILL.md and reference docs
  sample-bucket/         local sample data for dev, tests, and the bake-off
  deploy/helm/           chart for the k8s deployment
  tests/                 python tests and fixtures
  docs/superpowers/      specs and plans
```

## 10. Build order

1. Contract: schemas, fixtures, sample bucket.
2. Storage layer with both backends and tests.
3. Server with the four routes.
4. Front end: tree, dashboard page, controls, small lane, the three adapters,
   stat tile. Then large lane with DuckDB-WASM.
5. Bake-off review with the user. Remove losers.
6. CLI and skill.
7. Refresher scaffold, Dockerfile, Helm chart, CI.

Each step is usable on its own before the next starts.
