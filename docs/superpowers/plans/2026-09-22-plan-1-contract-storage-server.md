# Plan 1: Contract, Storage and Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python package `viz` with validated JSON Schemas for the bucket contract, a storage layer with local and S3 backends, and a hardened read-only FastAPI server that serves a sample bucket through four API routes.

**Architecture:** One Python package. `viz.ids` and `viz.schemas` define the contract. `viz.storage` is a small protocol with two backends chosen by configuration. `viz.server` builds a FastAPI app that lists and validates documents from storage, caches the tree, and streams data files, with security headers and an identity slot on every response. No write routes exist.

**Tech Stack:** Python 3.11+, FastAPI, Starlette, uvicorn, jsonschema (draft 2020-12), boto3, pydantic-settings, pytest, httpx, moto.

**Spec:** `docs/superpowers/specs/2026-09-22-viz-site-design.md` (sections 3, 4, 5.1, 8, 9, 12.2, 12.6). Security rationale: `docs/superpowers/specs/2026-09-22-security-review.md`.

## Global Constraints

- Python `>=3.11`. Package name `viz`, distribution name `viz-site`, MIT license.
- Id pattern, verbatim from the spec: `^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*$`, max 512 characters.
- Column name pattern: `^[A-Za-z_][A-Za-z0-9_]*$`.
- Small lane: format `json`, at most `100000` rows and `20971520` bytes, `aggregate` must be null. Large lane: format `parquet`, at most `209715200` bytes, `aggregate` required, a non-empty string.
- `description` and markdown tiles: max `8192` characters. Documents: max `1048576` bytes (checked by HEAD before GET).
- Root prefix default `viz/`. Data key is derived: `<root>charts/<id>/data.<format>`. There is no `data.path` field.
- Chart API response strips `source.sql` and `source.warehouse_id` unless `source.show_sql` is true.
- Content Security Policy header value, verbatim: `default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`
- No CORS middleware anywhere. `TrustedHostMiddleware` is always on.
- Data route is `GET /api/data/{id}` (amended from the spec's `/api/charts/{id}/data`, which is ambiguous when an id ends in `/data`).
- Sample bucket content is synthetic: `author` is always `sample@example.com`, any `source.warehouse_id` is `sample`.
- Every commit message ends with these two trailer lines:
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_014JyBpbUMQyfxRP89X12AES`
- Run tests with `python -m pytest` from the repo root. All tests must pass before each commit.

---

## File structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, dependencies, pytest config, console script |
| `viz/__init__.py` | Version string only |
| `viz/ids.py` | Id validation and bucket key derivation |
| `viz/schemas.py` | Load JSON Schemas, validate documents, renderer-specific spec checks |
| `schemas/chart.schema.json` | Chart contract |
| `schemas/dashboard.schema.json` | Dashboard contract |
| `schemas/folder.schema.json` | Folder metadata contract |
| `viz/config.py` | `Settings` from `VIZ_*` environment variables |
| `viz/storage/base.py` | `Storage` protocol, `ObjectInfo`, `NotFound` |
| `viz/storage/local.py` | Filesystem backend |
| `viz/storage/s3.py` | S3 backend via boto3 |
| `viz/storage/__init__.py` | `get_storage(settings)` factory |
| `viz/server/documents.py` | Load, size-check, validate a document from storage; public view of a chart |
| `viz/server/tree.py` | Build the folder tree; `TreeCache` with single-flight refresh |
| `viz/server/middleware.py` | Security headers, identity header slot with access log |
| `viz/server/routes.py` | The API router |
| `viz/server/static.py` | Serve the built front end with SPA fallback |
| `viz/server/app.py` | `create_app(settings)` |
| `viz/server/__main__.py` | `python -m viz.server` / `viz-server` entry point |
| `sample-bucket/generate.py` | Deterministic generator for the sample bucket |
| `sample-bucket/viz/...` | Generated sample charts, dashboard, folders |
| `tests/` | Mirrors the package layout |

---

### Task 1: Repository scaffold

**Files:**
- Create: `pyproject.toml`, `viz/__init__.py`, `README.md`, `LICENSE`, `.gitattributes`, `tests/__init__.py`, `tests/test_package.py`

**Interfaces:**
- Produces: `viz.__version__` (str).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_package.py
def test_version_is_a_string():
    import viz
    assert isinstance(viz.__version__, str)
    assert viz.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_package.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'viz'`

- [ ] **Step 3: Create the package files**

`pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "viz-site"
version = "0.1.0"
description = "A viewer over an object-store folder of published charts and dashboards"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "jsonschema[format]>=4.23",
  "boto3>=1.35",
  "pydantic-settings>=2.5",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.24",
  "httpx>=0.27",
  "moto[s3]>=5",
]

[project.scripts]
viz-server = "viz.server.__main__:main"

[tool.hatch.build.targets.wheel]
packages = ["viz"]

[tool.hatch.build.targets.wheel.force-include]
"schemas" = "viz/_schemas"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

`viz/__init__.py`:

```python
__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

`.gitattributes`:

```
* text=auto eol=lf
```

`LICENSE`: the MIT license text with `Copyright (c) 2026 viz-site contributors`.

`README.md`:

```markdown
# viz-site

A self-hosted viewer over a folder in an object store. Agents and people publish
charts and dashboards into that folder through a paved path; the site only reads.

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

Design: `docs/superpowers/specs/2026-09-22-viz-site-design.md`.
```

- [ ] **Step 4: Install and run the test**

Run: `pip install -e ".[dev]"` then `python -m pytest tests/test_package.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml viz/__init__.py README.md LICENSE .gitattributes tests/__init__.py tests/test_package.py
git commit -m "chore: scaffold viz package"
```

---

### Task 2: Ids and key derivation

**Files:**
- Create: `viz/ids.py`, `tests/test_ids.py`

**Interfaces:**
- Produces:
  - `ID_PATTERN: re.Pattern`, `MAX_ID_LENGTH = 512`
  - `class InvalidId(ValueError)`
  - `validate_id(value: str) -> str` (returns the value or raises `InvalidId`)
  - `normalize_root(prefix: str) -> str` (no leading slash, trailing slash unless empty)
  - `chart_key(root: str, chart_id: str) -> str`
  - `data_key(root: str, chart_id: str, fmt: str) -> str` (`fmt` is `"json"` or `"parquet"`)
  - `dashboard_key(root: str, dashboard_id: str) -> str`
  - `folder_key(root: str, kind: str, folder: str) -> str` (`kind` is `"charts"` or `"dashboards"`, `folder` may be `""`)
  - `is_ancestor(a: str, b: str) -> bool` (true when `b` starts with `a + "/"`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ids.py
import pytest
from viz import ids


@pytest.mark.parametrize("value", ["a", "sales", "sales/emea", "revenue-by-region", "a1/b-2/c3"])
def test_valid_ids(value):
    assert ids.validate_id(value) == value


@pytest.mark.parametrize(
    "value",
    ["", "Sales", "sales/", "/sales", "sales//emea", "sales/../x", "a b", "a_b", "-a", "a-", "a/.b", "x" * 513],
)
def test_invalid_ids(value):
    with pytest.raises(ids.InvalidId):
        ids.validate_id(value)


def test_normalize_root():
    assert ids.normalize_root("viz") == "viz/"
    assert ids.normalize_root("viz/") == "viz/"
    assert ids.normalize_root("/viz/") == "viz/"
    assert ids.normalize_root("") == ""


def test_keys():
    assert ids.chart_key("viz/", "sales/emea/rev") == "viz/charts/sales/emea/rev/chart.json"
    assert ids.data_key("viz/", "sales/emea/rev", "json") == "viz/charts/sales/emea/rev/data.json"
    assert ids.data_key("viz/", "sales/emea/rev", "parquet") == "viz/charts/sales/emea/rev/data.parquet"
    assert ids.dashboard_key("viz/", "sales/overview") == "viz/dashboards/sales/overview.json"
    assert ids.folder_key("viz/", "charts", "sales") == "viz/charts/sales/_folder.json"
    assert ids.folder_key("viz/", "dashboards", "") == "viz/dashboards/_folder.json"


def test_data_key_rejects_unknown_format():
    with pytest.raises(ValueError):
        ids.data_key("viz/", "a", "csv")


def test_is_ancestor():
    assert ids.is_ancestor("a", "a/b")
    assert ids.is_ancestor("a/b", "a/b/c")
    assert not ids.is_ancestor("a", "ab")
    assert not ids.is_ancestor("a/b", "a")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ids.py -v`
Expected: FAIL with `ImportError: cannot import name 'ids'`

- [ ] **Step 3: Implement**

```python
# viz/ids.py
"""Id validation and bucket key derivation. Ids are slash-separated slugs."""
import re

ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*$")
MAX_ID_LENGTH = 512
DATA_FORMATS = ("json", "parquet")
KINDS = ("charts", "dashboards")


class InvalidId(ValueError):
    pass


def validate_id(value: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_ID_LENGTH or not ID_PATTERN.fullmatch(value):
        raise InvalidId(f"invalid id: {value!r}")
    return value


def normalize_root(prefix: str) -> str:
    prefix = prefix.strip("/")
    return f"{prefix}/" if prefix else ""


def chart_key(root: str, chart_id: str) -> str:
    return f"{root}charts/{chart_id}/chart.json"


def data_key(root: str, chart_id: str, fmt: str) -> str:
    if fmt not in DATA_FORMATS:
        raise ValueError(f"unknown data format: {fmt!r}")
    return f"{root}charts/{chart_id}/data.{fmt}"


def dashboard_key(root: str, dashboard_id: str) -> str:
    return f"{root}dashboards/{dashboard_id}.json"


def folder_key(root: str, kind: str, folder: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind!r}")
    return f"{root}{kind}/{folder}/_folder.json" if folder else f"{root}{kind}/_folder.json"


def is_ancestor(a: str, b: str) -> bool:
    return b.startswith(a + "/")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ids.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add viz/ids.py tests/test_ids.py
git commit -m "feat: id validation and bucket key derivation"
```

---

### Task 3: JSON Schemas and document validation

**Files:**
- Create: `schemas/chart.schema.json`, `schemas/dashboard.schema.json`, `schemas/folder.schema.json`, `viz/schemas.py`
- Create: `tests/fixtures/valid/chart-vegalite.json`, `tests/fixtures/valid/chart-plotly.json`, `tests/fixtures/valid/chart-echarts.json`, `tests/fixtures/valid/chart-large.json`, `tests/fixtures/valid/chart-stat.json`, `tests/fixtures/valid/dashboard.json`, `tests/fixtures/valid/folder.json`
- Create: `tests/test_schemas.py`

**Interfaces:**
- Produces:
  - `class SchemaError(ValueError)` with `.errors: list[str]`
  - `validate_chart(doc: dict) -> dict`, `validate_dashboard(doc: dict) -> dict`, `validate_folder(doc: dict) -> dict` (each returns `doc` or raises `SchemaError`)
  - `schema_dir() -> Path`
  - `FORBIDDEN_SPEC_KEYS: frozenset[str]`

- [ ] **Step 1: Write the valid fixtures**

`tests/fixtures/valid/chart-vegalite.json`:

```json
{
  "schema_version": 1,
  "id": "sales/revenue-by-region",
  "title": "Revenue by region, monthly",
  "description": "Monthly revenue per region.",
  "tags": ["sales"],
  "author": "sample@example.com",
  "created_at": "2026-09-22T10:00:00Z",
  "updated_at": "2026-09-22T10:00:00Z",
  "renderer": "vega-lite",
  "spec": {
    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
    "data": {"name": "data"},
    "mark": {"type": "line", "point": true},
    "encoding": {
      "x": {"field": "month", "type": "temporal", "title": "Month"},
      "y": {"field": "revenue", "type": "quantitative", "title": "Revenue"},
      "color": {"field": "region", "type": "nominal", "title": "Region"}
    }
  },
  "data": {
    "format": "json",
    "lane": "small",
    "rows": 144,
    "bytes": 9000,
    "columns": [
      {"name": "month", "type": "date"},
      {"name": "region", "type": "string"},
      {"name": "revenue", "type": "number"},
      {"name": "orders", "type": "integer"}
    ]
  },
  "aggregate": null,
  "source": {
    "kind": "databricks-sql",
    "sql": "SELECT month, region, revenue, orders FROM sample.sales.monthly",
    "warehouse_id": "sample",
    "schedule": "0 6 * * *",
    "show_sql": true
  }
}
```

`tests/fixtures/valid/chart-plotly.json`:

```json
{
  "schema_version": 1,
  "id": "sales/orders-by-region",
  "title": "Orders by region",
  "author": "sample@example.com",
  "renderer": "plotly",
  "spec": {
    "traces": [
      {"type": "bar", "x": {"column": "region"}, "y": {"column": "orders"}, "name": "Orders"}
    ],
    "layout": {"title": {"text": "Orders by region"}, "barmode": "group"}
  },
  "data": {
    "format": "json",
    "lane": "small",
    "rows": 4,
    "bytes": 200,
    "columns": [
      {"name": "region", "type": "string"},
      {"name": "orders", "type": "integer"}
    ]
  }
}
```

`tests/fixtures/valid/chart-echarts.json`:

```json
{
  "schema_version": 1,
  "id": "sales/orders-by-region-echarts",
  "title": "Orders by region",
  "author": "sample@example.com",
  "renderer": "echarts",
  "spec": {
    "xAxis": {"type": "category"},
    "yAxis": {"type": "value"},
    "tooltip": {"trigger": "axis", "renderMode": "richText"},
    "series": [{"type": "bar", "encode": {"x": "region", "y": "orders"}}]
  },
  "data": {
    "format": "json",
    "lane": "small",
    "rows": 4,
    "bytes": 200,
    "columns": [
      {"name": "region", "type": "string"},
      {"name": "orders", "type": "integer"}
    ]
  }
}
```

`tests/fixtures/valid/chart-large.json`:

```json
{
  "schema_version": 1,
  "id": "sales/order-lines",
  "title": "Order lines, aggregated by day",
  "author": "sample@example.com",
  "renderer": "vega-lite",
  "spec": {
    "data": {"name": "data"},
    "mark": "bar",
    "encoding": {
      "x": {"field": "day", "type": "temporal"},
      "y": {"field": "total", "type": "quantitative"}
    }
  },
  "data": {
    "format": "parquet",
    "lane": "large",
    "rows": 2500000,
    "bytes": 52428800,
    "columns": [
      {"name": "day", "type": "date"},
      {"name": "region", "type": "string"},
      {"name": "amount", "type": "number"}
    ]
  },
  "aggregate": "SELECT day, sum(amount) AS total FROM data GROUP BY day ORDER BY day"
}
```

`tests/fixtures/valid/chart-stat.json`:

```json
{
  "schema_version": 1,
  "id": "sales/total-revenue",
  "title": "Total revenue",
  "author": "sample@example.com",
  "renderer": "stat",
  "spec": {"value": "revenue", "agg": "sum", "format": "$,.0f", "compare": {"column": "orders", "agg": "sum"}},
  "data": {
    "format": "json",
    "lane": "small",
    "rows": 144,
    "bytes": 9000,
    "columns": [
      {"name": "month", "type": "date"},
      {"name": "region", "type": "string"},
      {"name": "revenue", "type": "number"},
      {"name": "orders", "type": "integer"}
    ]
  }
}
```

`tests/fixtures/valid/dashboard.json`:

```json
{
  "schema_version": 1,
  "id": "sales/overview",
  "title": "Sales overview",
  "description": "Revenue and orders by region.",
  "tags": ["sales"],
  "author": "sample@example.com",
  "created_at": "2026-09-22T10:00:00Z",
  "updated_at": "2026-09-22T10:00:00Z",
  "controls": [
    {"id": "period", "type": "date-range", "label": "Period", "column": "month", "default": {"last": "12m"}},
    {"id": "region", "type": "select", "label": "Region", "column": "region", "multi": true, "default": null},
    {"id": "revenue", "type": "number-range", "label": "Revenue", "column": "revenue", "default": null}
  ],
  "layout": [
    {"chart": "sales/revenue-by-region", "w": 8, "h": 4},
    {"chart": "sales/total-revenue", "w": 4, "h": 2},
    {"markdown": "Sample data, generated deterministically.", "w": 12, "h": 1}
  ]
}
```

`tests/fixtures/valid/folder.json`:

```json
{"schema_version": 1, "title": "Sales", "description": "Everything the sales team publishes.", "order": 10}
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_schemas.py
import copy
import json
from pathlib import Path

import pytest

from viz import schemas

FIXTURES = Path(__file__).parent / "fixtures" / "valid"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


VALID_CHARTS = ["chart-vegalite.json", "chart-plotly.json", "chart-echarts.json", "chart-large.json", "chart-stat.json"]


@pytest.mark.parametrize("name", VALID_CHARTS)
def test_valid_charts_pass(name):
    doc = load(name)
    assert schemas.validate_chart(doc) is doc


def test_valid_dashboard_passes():
    doc = load("dashboard.json")
    assert schemas.validate_dashboard(doc) is doc


def test_valid_folder_passes():
    doc = load("folder.json")
    assert schemas.validate_folder(doc) is doc


def test_empty_folder_doc_passes():
    assert schemas.validate_folder({"schema_version": 1}) == {"schema_version": 1}


def _set(path: str, value):
    def mutate(doc):
        parts = path.split(".")
        target = doc
        for part in parts[:-1]:
            target = target[int(part)] if part.isdigit() else target[part]
        last = parts[-1]
        if last.isdigit():
            target[int(last)] = value
        else:
            target[last] = value
    return mutate


def _delete(path: str):
    def mutate(doc):
        parts = path.split(".")
        target = doc
        for part in parts[:-1]:
            target = target[int(part)] if part.isdigit() else target[part]
        del target[parts[-1]]
    return mutate


CHART_CASES = [
    ("bad id", "chart-vegalite.json", _set("id", "Sales/EMEA"), "id"),
    ("id too long", "chart-vegalite.json", _set("id", "a" * 513), "id"),
    ("unknown renderer", "chart-vegalite.json", _set("renderer", "d3"), "renderer"),
    ("unknown top-level key", "chart-vegalite.json", _set("path", "x"), "path"),
    ("description too long", "chart-vegalite.json", _set("description", "x" * 8193), "description"),
    ("small lane with aggregate", "chart-vegalite.json", _set("aggregate", "SELECT 1"), "aggregate"),
    ("small lane parquet", "chart-vegalite.json", _set("data.format", "parquet"), "format"),
    ("small lane too many rows", "chart-vegalite.json", _set("data.rows", 100001), "rows"),
    ("small lane too many bytes", "chart-vegalite.json", _set("data.bytes", 20971521), "bytes"),
    ("large lane without aggregate", "chart-large.json", _delete("aggregate"), "aggregate"),
    ("large lane null aggregate", "chart-large.json", _set("aggregate", None), "aggregate"),
    ("large lane json", "chart-large.json", _set("data.format", "json"), "format"),
    ("large lane too many bytes", "chart-large.json", _set("data.bytes", 209715201), "bytes"),
    ("bad column name", "chart-vegalite.json", _set("data.columns.0.name", "month-1"), "name"),
    ("bad column type", "chart-vegalite.json", _set("data.columns.0.type", "text"), "type"),
    ("no columns", "chart-vegalite.json", _set("data.columns", []), "columns"),
    ("source extra property", "chart-vegalite.json", _set("source.token", "abc"), "token"),
    ("source unknown kind", "chart-vegalite.json", _set("source.kind", "snowflake"), "kind"),
    ("forbidden key href", "chart-vegalite.json", _set("spec.encoding.href", {"field": "region"}), "href"),
    ("forbidden key url", "chart-vegalite.json", _set("spec.data", {"url": "https://x"}), "url"),
    ("vega-lite inline values", "chart-vegalite.json", _set("spec.data", {"values": [{"a": 1}]}), "values"),
    ("vega-lite wrong data name", "chart-vegalite.json", _set("spec.data", {"name": "other"}), "data"),
    ("vega-lite image mark", "chart-vegalite.json", _set("spec.mark", "image"), "image"),
    ("vega-lite image mark object", "chart-vegalite.json", _set("spec.mark", {"type": "image"}), "image"),
    ("echarts formatter html", "chart-echarts.json", _set("spec.tooltip.formatter", "<b>{b}</b>"), "formatter"),
    ("echarts inline series data", "chart-echarts.json", _set("spec.series.0.data", [1, 2]), "data"),
    ("echarts dataset", "chart-echarts.json", _set("spec.dataset", {"source": []}), "dataset"),
    ("echarts html render mode", "chart-echarts.json", _set("spec.tooltip.renderMode", "html"), "renderMode"),
    ("echarts forbidden graphic", "chart-echarts.json", _set("spec.graphic", []), "graphic"),
    ("plotly inline array", "chart-plotly.json", _set("spec.traces.0.x", ["a", "b"]), "x"),
    ("plotly unknown column", "chart-plotly.json", _set("spec.traces.0.y", {"column": "nope"}), "nope"),
    ("plotly geo trace", "chart-plotly.json", _set("spec.traces.0.type", "choropleth"), "type"),
    ("plotly extra top-level key", "chart-plotly.json", _set("spec.frames", []), "frames"),
    ("plotly layout images", "chart-plotly.json", _set("spec.layout.images", []), "images"),
    ("stat unknown column", "chart-stat.json", _set("spec.value", "nope"), "nope"),
    ("stat bad agg", "chart-stat.json", _set("spec.agg", "median"), "agg"),
    ("stat compare unknown column", "chart-stat.json", _set("spec.compare.column", "nope"), "nope"),
]


@pytest.mark.parametrize("label,fixture,mutate,needle", CHART_CASES, ids=[c[0] for c in CHART_CASES])
def test_invalid_charts_fail(label, fixture, mutate, needle):
    doc = copy.deepcopy(load(fixture))
    mutate(doc)
    with pytest.raises(schemas.SchemaError) as excinfo:
        schemas.validate_chart(doc)
    assert needle in str(excinfo.value)


DASHBOARD_CASES = [
    ("bad id", _set("id", "Sales"), "id"),
    ("no layout", _delete("layout"), "layout"),
    ("empty layout", _set("layout", []), "layout"),
    ("tile too wide", _set("layout.0.w", 13), "w"),
    ("tile zero height", _set("layout.0.h", 0), "h"),
    ("tile with both chart and markdown", _set("layout.0.markdown", "x"), "markdown"),
    ("markdown too long", _set("layout.2.markdown", "x" * 8193), "markdown"),
    ("bad control type", _set("controls.0.type", "slider"), "type"),
    ("bad control column", _set("controls.0.column", "a-b"), "column"),
    ("bad date-range default", _set("controls.0.default", {"last": "12 months"}), "last"),
    ("bad number-range default", _set("controls.2.default", {"min": "1"}), "min"),
    ("duplicate control id", _set("controls.1.id", "period"), "duplicate"),
    ("unknown key", _set("filters", []), "filters"),
]


@pytest.mark.parametrize("label,mutate,needle", DASHBOARD_CASES, ids=[c[0] for c in DASHBOARD_CASES])
def test_invalid_dashboards_fail(label, mutate, needle):
    doc = copy.deepcopy(load("dashboard.json"))
    mutate(doc)
    with pytest.raises(schemas.SchemaError) as excinfo:
        schemas.validate_dashboard(doc)
    assert needle in str(excinfo.value)


def test_invalid_folder_fails():
    with pytest.raises(schemas.SchemaError) as excinfo:
        schemas.validate_folder({"schema_version": 1, "order": "first"})
    assert "order" in str(excinfo.value)


def test_schema_error_lists_all_errors():
    doc = copy.deepcopy(load("chart-vegalite.json"))
    doc["id"] = "Bad"
    doc["renderer"] = "d3"
    with pytest.raises(schemas.SchemaError) as excinfo:
        schemas.validate_chart(doc)
    assert len(excinfo.value.errors) >= 2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: FAIL with `ImportError: cannot import name 'schemas'`

- [ ] **Step 4: Write the schemas**

`schemas/chart.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://viz-site.dev/schemas/chart.schema.json",
  "title": "Chart",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "id", "title", "renderer", "spec", "data"],
  "properties": {
    "schema_version": {"const": 1},
    "id": {"$ref": "#/$defs/id"},
    "title": {"type": "string", "minLength": 1, "maxLength": 200},
    "description": {"type": "string", "maxLength": 8192},
    "tags": {"type": "array", "maxItems": 32, "items": {"type": "string", "minLength": 1, "maxLength": 64}},
    "author": {"type": "string", "maxLength": 200},
    "created_at": {"type": "string", "format": "date-time"},
    "updated_at": {"type": "string", "format": "date-time"},
    "renderer": {"enum": ["vega-lite", "plotly", "echarts", "stat"]},
    "spec": {"$ref": "#/$defs/noForbiddenKeys"},
    "data": {
      "type": "object",
      "additionalProperties": false,
      "required": ["format", "lane", "rows", "bytes", "columns"],
      "properties": {
        "format": {"enum": ["json", "parquet"]},
        "lane": {"enum": ["small", "large"]},
        "rows": {"type": "integer", "minimum": 0},
        "bytes": {"type": "integer", "minimum": 0},
        "columns": {
          "type": "array",
          "minItems": 1,
          "maxItems": 500,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["name", "type"],
            "properties": {
              "name": {"$ref": "#/$defs/columnName"},
              "type": {"enum": ["string", "number", "integer", "boolean", "date", "timestamp"]}
            }
          }
        }
      }
    },
    "aggregate": {"type": ["string", "null"], "maxLength": 8192},
    "source": {
      "type": "object",
      "additionalProperties": false,
      "required": ["kind", "sql"],
      "properties": {
        "kind": {"const": "databricks-sql"},
        "sql": {"type": "string", "minLength": 1, "maxLength": 65536},
        "warehouse_id": {"type": "string", "maxLength": 64},
        "schedule": {"type": "string", "maxLength": 64},
        "show_sql": {"type": "boolean"}
      }
    }
  },
  "allOf": [
    {
      "if": {"properties": {"data": {"properties": {"lane": {"const": "small"}}}}},
      "then": {
        "properties": {
          "data": {"properties": {"format": {"const": "json"}, "rows": {"maximum": 100000}, "bytes": {"maximum": 20971520}}},
          "aggregate": {"type": "null"}
        }
      }
    },
    {
      "if": {"properties": {"data": {"properties": {"lane": {"const": "large"}}}}},
      "then": {
        "required": ["aggregate"],
        "properties": {
          "data": {"properties": {"format": {"const": "parquet"}, "bytes": {"maximum": 209715200}}},
          "aggregate": {"type": "string", "minLength": 1}
        }
      }
    },
    {
      "if": {"properties": {"renderer": {"const": "stat"}}},
      "then": {"properties": {"spec": {"$ref": "#/$defs/statSpec"}}}
    }
  ],
  "$defs": {
    "id": {"type": "string", "maxLength": 512, "pattern": "^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*$"},
    "columnName": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
    "agg": {"enum": ["sum", "avg", "min", "max", "count", "last"]},
    "statSpec": {
      "type": "object",
      "additionalProperties": false,
      "required": ["value", "agg"],
      "properties": {
        "value": {"$ref": "#/$defs/columnName"},
        "agg": {"$ref": "#/$defs/agg"},
        "format": {"type": "string", "maxLength": 32},
        "compare": {
          "type": "object",
          "additionalProperties": false,
          "required": ["column", "agg"],
          "properties": {"column": {"$ref": "#/$defs/columnName"}, "agg": {"$ref": "#/$defs/agg"}}
        }
      }
    },
    "noForbiddenKeys": {
      "if": {"type": "object"},
      "then": {
        "propertyNames": {
          "not": {
            "enum": ["url", "href", "usermeta", "link", "sublink", "graphic", "extraCssText", "appendTo", "className", "images", "mapbox", "map", "__proto__", "constructor", "prototype"]
          }
        },
        "additionalProperties": {"$ref": "#/$defs/noForbiddenKeys"}
      },
      "else": {
        "if": {"type": "array"},
        "then": {"items": {"$ref": "#/$defs/noForbiddenKeys"}}
      }
    }
  }
}
```

`schemas/dashboard.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://viz-site.dev/schemas/dashboard.schema.json",
  "title": "Dashboard",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "id", "title", "layout"],
  "properties": {
    "schema_version": {"const": 1},
    "id": {"type": "string", "maxLength": 512, "pattern": "^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*$"},
    "title": {"type": "string", "minLength": 1, "maxLength": 200},
    "description": {"type": "string", "maxLength": 8192},
    "tags": {"type": "array", "maxItems": 32, "items": {"type": "string", "minLength": 1, "maxLength": 64}},
    "author": {"type": "string", "maxLength": 200},
    "created_at": {"type": "string", "format": "date-time"},
    "updated_at": {"type": "string", "format": "date-time"},
    "controls": {
      "type": "array",
      "maxItems": 20,
      "items": {
        "oneOf": [
          {"$ref": "#/$defs/dateRange"},
          {"$ref": "#/$defs/select"},
          {"$ref": "#/$defs/numberRange"}
        ]
      }
    },
    "layout": {
      "type": "array",
      "minItems": 1,
      "maxItems": 100,
      "items": {"oneOf": [{"$ref": "#/$defs/chartTile"}, {"$ref": "#/$defs/markdownTile"}]}
    }
  },
  "$defs": {
    "slug": {"type": "string", "maxLength": 64, "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
    "columnName": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
    "controlBase": {
      "type": "object",
      "required": ["id", "type", "label", "column"],
      "properties": {
        "id": {"$ref": "#/$defs/slug"},
        "label": {"type": "string", "minLength": 1, "maxLength": 80},
        "column": {"$ref": "#/$defs/columnName"}
      }
    },
    "dateRange": {
      "allOf": [{"$ref": "#/$defs/controlBase"}],
      "properties": {
        "id": true, "label": true, "column": true,
        "type": {"const": "date-range"},
        "default": {
          "oneOf": [
            {"type": "null"},
            {"type": "object", "additionalProperties": false, "required": ["last"], "properties": {"last": {"type": "string", "pattern": "^[0-9]{1,3}[dwmy]$"}}},
            {"type": "object", "additionalProperties": false, "required": ["from", "to"], "properties": {"from": {"type": "string", "format": "date"}, "to": {"type": "string", "format": "date"}}}
          ]
        }
      },
      "additionalProperties": false
    },
    "select": {
      "allOf": [{"$ref": "#/$defs/controlBase"}],
      "properties": {
        "id": true, "label": true, "column": true,
        "type": {"const": "select"},
        "multi": {"type": "boolean"},
        "default": {
          "oneOf": [
            {"type": "null"},
            {"type": "string", "maxLength": 200},
            {"type": "array", "maxItems": 100, "items": {"type": "string", "maxLength": 200}}
          ]
        }
      },
      "additionalProperties": false
    },
    "numberRange": {
      "allOf": [{"$ref": "#/$defs/controlBase"}],
      "properties": {
        "id": true, "label": true, "column": true,
        "type": {"const": "number-range"},
        "default": {
          "oneOf": [
            {"type": "null"},
            {"type": "object", "additionalProperties": false, "properties": {"min": {"type": "number"}, "max": {"type": "number"}}}
          ]
        }
      },
      "additionalProperties": false
    },
    "chartTile": {
      "type": "object",
      "additionalProperties": false,
      "required": ["chart", "w", "h"],
      "properties": {
        "chart": {"type": "string", "maxLength": 512, "pattern": "^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*$"},
        "w": {"type": "integer", "minimum": 1, "maximum": 12},
        "h": {"type": "integer", "minimum": 1, "maximum": 12}
      }
    },
    "markdownTile": {
      "type": "object",
      "additionalProperties": false,
      "required": ["markdown", "w", "h"],
      "properties": {
        "markdown": {"type": "string", "maxLength": 8192},
        "w": {"type": "integer", "minimum": 1, "maximum": 12},
        "h": {"type": "integer", "minimum": 1, "maximum": 12}
      }
    }
  }
}
```

`schemas/folder.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://viz-site.dev/schemas/folder.schema.json",
  "title": "Folder",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version"],
  "properties": {
    "schema_version": {"const": 1},
    "title": {"type": "string", "minLength": 1, "maxLength": 200},
    "description": {"type": "string", "maxLength": 8192},
    "order": {"type": "integer"}
  }
}
```

- [ ] **Step 5: Write the validator module**

```python
# viz/schemas.py
"""Document validation: JSON Schema plus renderer-specific spec rules."""
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator, FormatChecker

FORBIDDEN_SPEC_KEYS = frozenset(
    ["url", "href", "usermeta", "link", "sublink", "graphic", "extraCssText", "appendTo",
     "className", "images", "mapbox", "map", "__proto__", "constructor", "prototype"]
)
PLOTLY_BOUND_KEYS = ("x", "y", "z", "text", "hovertext", "labels", "values", "customdata")
PLOTLY_FORBIDDEN_TRACE_TYPES = frozenset(
    ["scattergeo", "choropleth", "scattermapbox", "choroplethmapbox", "densitymapbox",
     "scattermap", "choroplethmap", "densitymap"]
)

_CANDIDATE_DIRS = (
    Path(__file__).parent / "_schemas",
    Path(__file__).resolve().parents[1] / "schemas",
)


class SchemaError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def schema_dir() -> Path:
    for candidate in _CANDIDATE_DIRS:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("schemas directory not found")


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((schema_dir() / f"{name}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _schema_errors(name: str, doc: Any) -> list[str]:
    errors = sorted(_validator(name).iter_errors(doc), key=lambda e: list(e.absolute_path))
    out = []
    for e in errors:
        path = "/".join(str(p) for p in e.absolute_path) or "$"
        out.append(f"{path}: {e.message}")
    return out


def _walk(node: Any, path: str = "spec") -> Iterator[tuple[str, str, Any]]:
    """Yield (path, key, value) for every key in every nested object."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}/{key}"
            yield here, key, value
            yield from _walk(value, here)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, f"{path}/{i}")


def _check_vegalite(spec: dict, columns: set[str]) -> list[str]:
    errors = []
    for path, key, value in _walk(spec):
        if key == "data" and value != {"name": "data"}:
            errors.append(f"{path}: vega-lite data must be exactly {{\"name\": \"data\"}}")
        if key == "values":
            errors.append(f"{path}: inline values are not allowed")
        if key == "mark" and (value == "image" or (isinstance(value, dict) and value.get("type") == "image")):
            errors.append(f"{path}: image marks are not allowed")
    return errors


def _check_echarts(spec: dict, columns: set[str]) -> list[str]:
    errors = []
    for path, key, value in _walk(spec):
        if key == "dataset":
            errors.append(f"{path}: dataset is injected by the viewer and must not be set")
        if key == "data":
            errors.append(f"{path}: inline data is not allowed")
        if key == "formatter" and isinstance(value, str) and "<" in value:
            errors.append(f"{path}: formatter must not contain HTML")
        if key == "renderMode" and value != "richText":
            errors.append(f"{path}: renderMode must be richText")
    return errors


def _check_plotly(spec: dict, columns: set[str]) -> list[str]:
    errors = []
    extra = set(spec) - {"traces", "layout"}
    for key in sorted(extra):
        errors.append(f"spec/{key}: plotly spec allows only traces and layout")
    traces = spec.get("traces")
    if not isinstance(traces, list) or not traces:
        errors.append("spec/traces: must be a non-empty array")
        return errors
    for i, trace in enumerate(traces):
        if not isinstance(trace, dict):
            errors.append(f"spec/traces/{i}: must be an object")
            continue
        if trace.get("type") in PLOTLY_FORBIDDEN_TRACE_TYPES:
            errors.append(f"spec/traces/{i}/type: geo and map traces are not allowed")
        for key in PLOTLY_BOUND_KEYS:
            if key not in trace:
                continue
            binding = trace[key]
            if not isinstance(binding, dict) or set(binding) != {"column"}:
                errors.append(f"spec/traces/{i}/{key}: must be a column binding {{\"column\": name}}")
            elif binding["column"] not in columns:
                errors.append(f"spec/traces/{i}/{key}: unknown column {binding['column']!r}")
    return errors


def _check_stat(spec: dict, columns: set[str]) -> list[str]:
    errors = []
    if isinstance(spec, dict):
        if spec.get("value") not in columns:
            errors.append(f"spec/value: unknown column {spec.get('value')!r}")
        compare = spec.get("compare")
        if isinstance(compare, dict) and compare.get("column") not in columns:
            errors.append(f"spec/compare/column: unknown column {compare.get('column')!r}")
    return errors


_RENDERER_CHECKS = {
    "vega-lite": _check_vegalite,
    "echarts": _check_echarts,
    "plotly": _check_plotly,
    "stat": _check_stat,
}


def validate_chart(doc: Any) -> dict:
    errors = _schema_errors("chart", doc)
    if isinstance(doc, dict) and isinstance(doc.get("spec"), dict) and doc.get("renderer") in _RENDERER_CHECKS:
        columns = {c.get("name") for c in doc.get("data", {}).get("columns", []) if isinstance(c, dict)}
        errors += _RENDERER_CHECKS[doc["renderer"]](doc["spec"], columns)
    if errors:
        raise SchemaError(errors)
    return doc


def validate_dashboard(doc: Any) -> dict:
    errors = _schema_errors("dashboard", doc)
    if isinstance(doc, dict) and isinstance(doc.get("controls"), list):
        seen: set[str] = set()
        for i, control in enumerate(doc["controls"]):
            cid = control.get("id") if isinstance(control, dict) else None
            if cid in seen:
                errors.append(f"controls/{i}/id: duplicate control id {cid!r}")
            if cid is not None:
                seen.add(cid)
    if errors:
        raise SchemaError(errors)
    return doc


def validate_folder(doc: Any) -> dict:
    errors = _schema_errors("folder", doc)
    if errors:
        raise SchemaError(errors)
    return doc
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: PASS (all). If a `oneOf` case in the dashboard schema reports a confusing message, check that the needle in that case appears in the joined message; the `path:` prefix contains the property name for every case listed.

- [ ] **Step 7: Commit**

```bash
git add schemas viz/schemas.py tests/fixtures tests/test_schemas.py
git commit -m "feat: JSON schemas and document validation with renderer spec rules"
```

---

### Task 4: Storage protocol and local backend

**Files:**
- Create: `viz/storage/__init__.py` (empty for now), `viz/storage/base.py`, `viz/storage/local.py`, `tests/storage/__init__.py`, `tests/storage/test_backends.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) ObjectInfo(key: str, size: int, etag: str, last_modified: datetime | None)`
  - `class NotFound(KeyError)`
  - `class Storage(Protocol)` with `list(prefix) -> list[ObjectInfo]`, `head(key) -> ObjectInfo`, `get(key) -> bytes`, `open(key, start=0, end=None) -> Iterator[bytes]` (end inclusive), `put(key, data, content_type) -> None`, `delete(key) -> None`, `copy(src, dst) -> None`
  - `LocalStorage(root: Path)`

- [ ] **Step 1: Write the shared backend test suite (local only for now)**

```python
# tests/storage/test_backends.py
from datetime import datetime

import pytest

from viz.storage.base import NotFound, ObjectInfo
from viz.storage.local import LocalStorage


@pytest.fixture(params=["local"])
def storage(request, tmp_path):
    if request.param == "local":
        yield LocalStorage(tmp_path / "bucket")


def test_put_get_head(storage):
    storage.put("viz/charts/a/chart.json", b'{"x": 1}', "application/json")
    assert storage.get("viz/charts/a/chart.json") == b'{"x": 1}'
    info = storage.head("viz/charts/a/chart.json")
    assert isinstance(info, ObjectInfo)
    assert info.key == "viz/charts/a/chart.json"
    assert info.size == 8
    assert info.etag
    assert info.last_modified is None or isinstance(info.last_modified, datetime)


def test_missing_key_raises(storage):
    with pytest.raises(NotFound):
        storage.get("nope")
    with pytest.raises(NotFound):
        storage.head("nope")
    with pytest.raises(NotFound):
        list(storage.open("nope"))


def test_list_is_recursive_and_sorted(storage):
    storage.put("viz/charts/b/chart.json", b"b", "application/json")
    storage.put("viz/charts/a/sub/chart.json", b"a", "application/json")
    storage.put("viz/dashboards/x.json", b"x", "application/json")
    keys = [o.key for o in storage.list("viz/charts/")]
    assert keys == ["viz/charts/a/sub/chart.json", "viz/charts/b/chart.json"]
    assert storage.list("viz/nothing/") == []


def test_open_streams_whole_object_and_ranges(storage):
    storage.put("k", b"0123456789", "application/octet-stream")
    assert b"".join(storage.open("k")) == b"0123456789"
    assert b"".join(storage.open("k", start=2, end=4)) == b"234"
    assert b"".join(storage.open("k", start=7)) == b"789"


def test_etag_changes_when_content_changes(storage):
    storage.put("k", b"one", "text/plain")
    first = storage.head("k").etag
    storage.put("k", b"two!", "text/plain")
    assert storage.head("k").etag != first


def test_delete_and_copy(storage):
    storage.put("src", b"data", "text/plain")
    storage.copy("src", "dst")
    assert storage.get("dst") == b"data"
    storage.delete("src")
    with pytest.raises(NotFound):
        storage.get("src")
    with pytest.raises(NotFound):
        storage.copy("src", "other")


def test_delete_missing_is_noop(storage):
    storage.delete("never-existed")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/storage -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'viz.storage'`

- [ ] **Step 3: Implement the protocol and the local backend**

`viz/storage/__init__.py`: empty file for now (Task 6 fills it).

```python
# viz/storage/base.py
"""The storage protocol every backend implements."""
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Protocol


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    etag: str
    last_modified: datetime | None


class NotFound(KeyError):
    pass


class Storage(Protocol):
    def list(self, prefix: str) -> list[ObjectInfo]:
        """All objects whose key starts with prefix, sorted by key."""

    def head(self, key: str) -> ObjectInfo: ...

    def get(self, key: str) -> bytes: ...

    def open(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        """Stream bytes from start to end inclusive. end=None means to the end."""

    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def delete(self, key: str) -> None:
        """Delete if present. Missing keys are not an error."""

    def copy(self, src: str, dst: str) -> None: ...
```

```python
# viz/storage/local.py
"""Filesystem backend. The root directory is the bucket."""
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .base import NotFound, ObjectInfo

CHUNK = 1024 * 1024


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._resolved_root = self.root.resolve()

    def _path(self, key: str) -> Path:
        if key.startswith("/") or ".." in key.split("/"):
            raise NotFound(key)
        path = (self.root / key)
        # Refuse anything that resolves outside the root, including symlinks that escape.
        resolved = path.resolve()
        if resolved != self._resolved_root and self._resolved_root not in resolved.parents:
            raise NotFound(key)
        return path

    def _info(self, key: str, path: Path) -> ObjectInfo:
        st = path.stat()
        return ObjectInfo(
            key=key,
            size=st.st_size,
            etag=f"{st.st_size:x}-{st.st_mtime_ns:x}",
            last_modified=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        )

    def list(self, prefix: str) -> list[ObjectInfo]:
        out = []
        for dirpath, _dirnames, filenames in os.walk(self.root):
            for name in filenames:
                path = Path(dirpath) / name
                key = path.relative_to(self.root).as_posix()
                if not key.startswith(prefix):
                    continue
                try:
                    self._path(key)
                except NotFound:
                    continue
                out.append(self._info(key, path))
        return sorted(out, key=lambda o: o.key)

    def head(self, key: str) -> ObjectInfo:
        path = self._path(key)
        if not path.is_file():
            raise NotFound(key)
        return self._info(key, path)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise NotFound(key)
        return path.read_bytes()

    def open(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        path = self._path(key)
        if not path.is_file():
            raise NotFound(key)
        size = path.stat().st_size
        stop = size - 1 if end is None else min(end, size - 1)
        remaining = stop - start + 1
        with path.open("rb") as f:
            f.seek(start)
            while remaining > 0:
                chunk = f.read(min(CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def copy(self, src: str, dst: str) -> None:
        src_path = self._path(src)
        if not src_path.is_file():
            raise NotFound(src)
        dst_path = self._path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, dst_path)
```

Create `tests/storage/__init__.py` as an empty file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/storage -v`
Expected: PASS (all)

- [ ] **Step 5: Add a symlink-escape test for the local backend**

Append to `tests/storage/test_backends.py`:

```python
import os
import sys


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privileges on Windows")
def test_local_refuses_symlink_escape(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    os.symlink(outside, bucket / "leak.txt")
    storage = LocalStorage(bucket)
    with pytest.raises(NotFound):
        storage.get("leak.txt")
    assert [o.key for o in storage.list("")] == []


def test_local_refuses_dotdot(tmp_path):
    storage = LocalStorage(tmp_path / "bucket")
    with pytest.raises(NotFound):
        storage.get("../outside.txt")
```

Run: `python -m pytest tests/storage -v`
Expected: PASS (symlink test skipped on Windows, passes elsewhere)

- [ ] **Step 6: Commit**

```bash
git add viz/storage tests/storage
git commit -m "feat: storage protocol and local filesystem backend"
```

---

### Task 5: S3 backend

**Files:**
- Create: `viz/storage/s3.py`
- Modify: `tests/storage/test_backends.py` (fixture params)

**Interfaces:**
- Produces: `S3Storage(bucket: str, client=None)`; when `client` is None a boto3 S3 client is created from the default session.

- [ ] **Step 1: Extend the shared fixture to run every test against S3 via moto**

Replace the fixture at the top of `tests/storage/test_backends.py` with:

```python
import boto3
import pytest
from moto import mock_aws

from viz.storage.base import NotFound, ObjectInfo
from viz.storage.local import LocalStorage
from viz.storage.s3 import S3Storage


@pytest.fixture(params=["local", "s3"])
def storage(request, tmp_path, monkeypatch):
    if request.param == "local":
        yield LocalStorage(tmp_path / "bucket")
        return
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-bucket")
        yield S3Storage("test-bucket", client=client)
```

- [ ] **Step 2: Run tests to verify the S3 cases fail**

Run: `python -m pytest tests/storage -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'viz.storage.s3'`

- [ ] **Step 3: Implement the S3 backend**

```python
# viz/storage/s3.py
"""S3 backend via boto3. Credentials come from the environment or the pod role."""
from typing import Iterator

import boto3
from botocore.exceptions import ClientError

from .base import NotFound, ObjectInfo

CHUNK = 1024 * 1024


def _is_missing(err: ClientError) -> bool:
    return err.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound")


class S3Storage:
    def __init__(self, bucket: str, client=None):
        self.bucket = bucket
        self.client = client or boto3.client("s3")

    def list(self, prefix: str) -> list[ObjectInfo]:
        out = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                out.append(ObjectInfo(
                    key=obj["Key"],
                    size=obj["Size"],
                    etag=obj["ETag"].strip('"'),
                    last_modified=obj.get("LastModified"),
                ))
        return sorted(out, key=lambda o: o.key)

    def head(self, key: str) -> ObjectInfo:
        try:
            resp = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(key) from err
            raise
        return ObjectInfo(key=key, size=resp["ContentLength"], etag=resp["ETag"].strip('"'),
                          last_modified=resp.get("LastModified"))

    def get(self, key: str) -> bytes:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(key) from err
            raise
        return resp["Body"].read()

    def open(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        range_header = f"bytes={start}-" if end is None else f"bytes={start}-{end}"
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key, Range=range_header)
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(key) from err
            raise
        yield from resp["Body"].iter_chunks(CHUNK)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def copy(self, src: str, dst: str) -> None:
        try:
            self.client.copy_object(Bucket=self.bucket, Key=dst, CopySource={"Bucket": self.bucket, "Key": src})
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(src) from err
            raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/storage -v`
Expected: PASS for both `local` and `s3` params on every test. Note: `test_missing_key_raises` for `open` requires the generator to be consumed with `list(...)`, which the test does.

- [ ] **Step 5: Commit**

```bash
git add viz/storage/s3.py tests/storage/test_backends.py
git commit -m "feat: S3 storage backend with moto-backed tests"
```

---

### Task 6: Settings and storage factory

**Files:**
- Create: `viz/config.py`, `tests/test_config.py`
- Modify: `viz/storage/__init__.py`

**Interfaces:**
- Produces:
  - `class Settings(BaseSettings)` with fields `storage: Literal["local","s3"] = "local"`, `s3_bucket: str | None = None`, `root_prefix: str = "viz/"` (normalized), `local_dir: Path = Path("./sample-bucket")`, `tree_ttl_seconds: int = 60`, `allowed_hosts: str = "localhost,127.0.0.1,testserver"`, `auth_header: str = "X-Forwarded-Email"`, `max_document_bytes: int = 1048576`, `web_dist: Path = Path("./web/dist")`, `host: str = "127.0.0.1"`, `port: int = 8000`; property `allowed_hosts_list: list[str]`. Env prefix `VIZ_`.
  - `get_storage(settings: Settings) -> Storage`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
from pathlib import Path

import pytest

from viz.config import Settings
from viz.storage import get_storage
from viz.storage.local import LocalStorage
from viz.storage.s3 import S3Storage


def test_defaults(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("VIZ_"):
            monkeypatch.delenv(key)
    s = Settings()
    assert s.storage == "local"
    assert s.root_prefix == "viz/"
    assert s.local_dir == Path("./sample-bucket")
    assert s.tree_ttl_seconds == 60
    assert s.allowed_hosts_list == ["localhost", "127.0.0.1", "testserver"]
    assert s.auth_header == "X-Forwarded-Email"
    assert s.max_document_bytes == 1048576
    assert s.host == "127.0.0.1"


def test_env_overrides_and_root_normalization(monkeypatch):
    monkeypatch.setenv("VIZ_STORAGE", "s3")
    monkeypatch.setenv("VIZ_S3_BUCKET", "my-bucket")
    monkeypatch.setenv("VIZ_ROOT_PREFIX", "/dash")
    monkeypatch.setenv("VIZ_ALLOWED_HOSTS", "viz.internal, localhost")
    s = Settings()
    assert s.storage == "s3"
    assert s.s3_bucket == "my-bucket"
    assert s.root_prefix == "dash/"
    assert s.allowed_hosts_list == ["viz.internal", "localhost"]


def test_get_storage_local(tmp_path):
    s = Settings(storage="local", local_dir=tmp_path)
    assert isinstance(get_storage(s), LocalStorage)


def test_get_storage_s3_requires_bucket():
    with pytest.raises(ValueError):
        get_storage(Settings(storage="s3", s3_bucket=None))


def test_get_storage_s3(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    storage = get_storage(Settings(storage="s3", s3_bucket="b"))
    assert isinstance(storage, S3Storage)
    assert storage.bucket == "b"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'viz.config'`

- [ ] **Step 3: Implement**

```python
# viz/config.py
"""Settings shared by the server and the CLI. All from VIZ_* environment variables."""
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .ids import normalize_root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIZ_", extra="ignore")

    storage: Literal["local", "s3"] = "local"
    s3_bucket: str | None = None
    root_prefix: str = "viz/"
    local_dir: Path = Path("./sample-bucket")
    tree_ttl_seconds: int = 60
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    auth_header: str = "X-Forwarded-Email"
    max_document_bytes: int = 1_048_576
    web_dist: Path = Path("./web/dist")
    host: str = "127.0.0.1"
    port: int = 8000

    @field_validator("root_prefix")
    @classmethod
    def _normalize_root(cls, value: str) -> str:
        return normalize_root(value)

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]
```

```python
# viz/storage/__init__.py
"""Pick a storage backend from settings."""
from ..config import Settings
from .base import NotFound, ObjectInfo, Storage
from .local import LocalStorage
from .s3 import S3Storage

__all__ = ["NotFound", "ObjectInfo", "Storage", "get_storage"]


def get_storage(settings: Settings) -> Storage:
    if settings.storage == "local":
        return LocalStorage(settings.local_dir)
    if not settings.s3_bucket:
        raise ValueError("VIZ_S3_BUCKET is required when VIZ_STORAGE=s3")
    return S3Storage(settings.s3_bucket)
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add viz/config.py viz/storage/__init__.py tests/test_config.py
git commit -m "feat: settings from environment and storage factory"
```

---

### Task 7: Sample bucket

**Files:**
- Create: `sample-bucket/generate.py`, `tests/test_sample_bucket.py`
- Generated: `sample-bucket/viz/charts/sales/_folder.json`, `sample-bucket/viz/charts/sales/revenue-by-region/{chart.json,data.json}`, `sample-bucket/viz/charts/sales/total-revenue/{chart.json,data.json}`, `sample-bucket/viz/dashboards/sales/_folder.json`, `sample-bucket/viz/dashboards/sales/overview.json`

**Interfaces:**
- Produces: a sample bucket at `sample-bucket/` with root prefix `viz/`, used by server tests and local development. Chart ids `sales/revenue-by-region` (vega-lite) and `sales/total-revenue` (stat); dashboard id `sales/overview`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sample_bucket.py
import json
from pathlib import Path

from viz import schemas

ROOT = Path(__file__).resolve().parents[1] / "sample-bucket" / "viz"


def _docs(kind: str, suffix: str):
    return sorted((ROOT / kind).rglob(suffix))


def test_sample_bucket_exists():
    assert (ROOT / "charts" / "sales" / "revenue-by-region" / "chart.json").is_file()
    assert (ROOT / "dashboards" / "sales" / "overview.json").is_file()


def test_every_chart_validates_and_matches_its_data():
    charts = _docs("charts", "chart.json")
    assert len(charts) >= 2
    for path in charts:
        doc = schemas.validate_chart(json.loads(path.read_text(encoding="utf-8")))
        assert doc["author"] == "sample@example.com"
        if "source" in doc:
            assert doc["source"]["warehouse_id"] == "sample"
        data_path = path.parent / f"data.{doc['data']['format']}"
        assert data_path.is_file()
        assert data_path.stat().st_size == doc["data"]["bytes"]
        if doc["data"]["format"] == "json":
            rows = json.loads(data_path.read_text(encoding="utf-8"))
            assert len(rows) == doc["data"]["rows"]
            declared = {c["name"] for c in doc["data"]["columns"]}
            assert set(rows[0]) == declared


def test_every_dashboard_validates_and_references_existing_charts():
    dashboards = [p for p in _docs("dashboards", "*.json") if p.name != "_folder.json"]
    assert len(dashboards) >= 1
    for path in dashboards:
        doc = schemas.validate_dashboard(json.loads(path.read_text(encoding="utf-8")))
        for tile in doc["layout"]:
            if "chart" in tile:
                assert (ROOT / "charts" / tile["chart"] / "chart.json").is_file()


def test_every_folder_validates():
    folders = _docs("charts", "_folder.json") + _docs("dashboards", "_folder.json")
    assert len(folders) >= 2
    for path in folders:
        schemas.validate_folder(json.loads(path.read_text(encoding="utf-8")))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sample_bucket.py -v`
Expected: FAIL on `test_sample_bucket_exists`

- [ ] **Step 3: Write the generator**

```python
# sample-bucket/generate.py
"""Regenerate the sample bucket. Deterministic, synthetic, safe to commit.

Run from the repo root:  python sample-bucket/generate.py
"""
import json
import random
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "viz"
AUTHOR = "sample@example.com"
STAMP = "2026-09-22T10:00:00Z"
REGIONS = ["EMEA", "NA", "APAC", "LATAM"]
COLUMNS = [
    {"name": "month", "type": "date"},
    {"name": "region", "type": "string"},
    {"name": "revenue", "type": "number"},
    {"name": "orders", "type": "integer"},
]


def month_series(n: int = 36) -> list[date]:
    out = []
    year, month = 2023, 10
    for _ in range(n):
        out.append(date(year, month, 1))
        month += 1
        if month == 13:
            month, year = 1, year + 1
    return out


def rows() -> list[dict]:
    rng = random.Random(20260922)
    base = {"EMEA": 420_000, "NA": 610_000, "APAC": 300_000, "LATAM": 150_000}
    out = []
    for i, m in enumerate(month_series()):
        for region in REGIONS:
            growth = 1 + 0.012 * i
            season = 1 + 0.08 * ((m.month in (11, 12)) - (m.month in (1, 2)))
            noise = rng.uniform(0.93, 1.07)
            revenue = round(base[region] * growth * season * noise, 2)
            orders = int(revenue / rng.uniform(180, 260))
            out.append({"month": m.isoformat(), "region": region, "revenue": revenue, "orders": orders})
    return out


def write_json(path: Path, doc) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return len(text.encode("utf-8"))


def chart_doc(chart_id, title, description, renderer, spec, data_rows, data_bytes, source=None):
    doc = {
        "schema_version": 1,
        "id": chart_id,
        "title": title,
        "description": description,
        "tags": ["sales", "sample"],
        "author": AUTHOR,
        "created_at": STAMP,
        "updated_at": STAMP,
        "renderer": renderer,
        "spec": spec,
        "data": {"format": "json", "lane": "small", "rows": data_rows, "bytes": data_bytes, "columns": COLUMNS},
        "aggregate": None,
    }
    if source:
        doc["source"] = source
    return doc


def main() -> None:
    data = rows()
    charts = ROOT / "charts" / "sales"
    dashboards = ROOT / "dashboards" / "sales"

    write_json(charts / "_folder.json", {"schema_version": 1, "title": "Sales", "description": "Sample sales charts.", "order": 10})
    write_json(dashboards / "_folder.json", {"schema_version": 1, "title": "Sales", "description": "Sample sales dashboards.", "order": 10})

    n = write_json(charts / "revenue-by-region" / "data.json", data)
    write_json(charts / "revenue-by-region" / "chart.json", chart_doc(
        "sales/revenue-by-region",
        "Revenue by region, monthly",
        "Monthly revenue for each region over the last three years. Synthetic data.",
        "vega-lite",
        {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"name": "data"},
            "mark": {"type": "line", "point": True},
            "encoding": {
                "x": {"field": "month", "type": "temporal", "title": "Month"},
                "y": {"field": "revenue", "type": "quantitative", "title": "Revenue"},
                "color": {"field": "region", "type": "nominal", "title": "Region"},
            },
        },
        len(data), n,
        source={
            "kind": "databricks-sql",
            "sql": "SELECT month, region, revenue, orders FROM sample.sales.monthly_revenue ORDER BY month, region",
            "warehouse_id": "sample",
            "schedule": "0 6 * * *",
            "show_sql": True,
        },
    ))

    n = write_json(charts / "total-revenue" / "data.json", data)
    write_json(charts / "total-revenue" / "chart.json", chart_doc(
        "sales/total-revenue",
        "Total revenue",
        "Sum of revenue over the selected period. One-off publish, no source.",
        "stat",
        {"value": "revenue", "agg": "sum", "format": "$,.0f", "compare": {"column": "orders", "agg": "sum"}},
        len(data), n,
    ))

    write_json(dashboards / "overview.json", {
        "schema_version": 1,
        "id": "sales/overview",
        "title": "Sales overview",
        "description": "Revenue and orders by region. Synthetic sample data.",
        "tags": ["sales", "sample"],
        "author": AUTHOR,
        "created_at": STAMP,
        "updated_at": STAMP,
        "controls": [
            {"id": "period", "type": "date-range", "label": "Period", "column": "month", "default": {"last": "12m"}},
            {"id": "region", "type": "select", "label": "Region", "column": "region", "multi": True, "default": None},
        ],
        "layout": [
            {"chart": "sales/revenue-by-region", "w": 8, "h": 4},
            {"chart": "sales/total-revenue", "w": 4, "h": 2},
            {"markdown": "This dashboard is generated by `sample-bucket/generate.py`. Nothing here is real.", "w": 12, "h": 1},
        ],
    })


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Generate and test**

Run: `python sample-bucket/generate.py` then `python -m pytest tests/test_sample_bucket.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add sample-bucket tests/test_sample_bucket.py
git commit -m "feat: deterministic synthetic sample bucket"
```

---

### Task 8: Server app skeleton, security headers, identity slot

**Files:**
- Create: `viz/server/__init__.py` (empty), `viz/server/middleware.py`, `viz/server/app.py`, `viz/server/routes.py` (health route only for now), `tests/server/__init__.py`, `tests/server/conftest.py`, `tests/server/test_middleware.py`

**Interfaces:**
- Produces:
  - `create_app(settings: Settings | None = None) -> FastAPI`; `app.state.settings`, `app.state.storage`
  - `CSP: str` constant in `viz.server.middleware`
  - `router: APIRouter` in `viz.server.routes`
  - `request.state.user: str | None` set by `IdentityMiddleware`

- [ ] **Step 1: Write the test fixtures and failing tests**

```python
# tests/server/conftest.py
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from viz.config import Settings
from viz.server.app import create_app

SAMPLE = Path(__file__).resolve().parents[2] / "sample-bucket"


@pytest.fixture
def bucket(tmp_path) -> Path:
    """A writable copy of the sample bucket."""
    dst = tmp_path / "bucket"
    shutil.copytree(SAMPLE / "viz", dst / "viz")
    return dst


@pytest.fixture
def settings(bucket) -> Settings:
    return Settings(storage="local", local_dir=bucket, root_prefix="viz/", tree_ttl_seconds=60,
                    web_dist=bucket / "no-web-dist")


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))
```

```python
# tests/server/test_middleware.py
from fastapi.testclient import TestClient

from viz.server.app import create_app
from viz.server.middleware import CSP


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_security_headers_on_every_response(client):
    r = client.get("/api/health")
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cross-origin-resource-policy"] == "same-origin"
    assert r.headers["referrer-policy"] == "same-origin"
    assert r.headers["x-frame-options"] == "DENY"


def test_csp_exact_value():
    assert CSP == (
        "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
        "connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )


def test_untrusted_host_is_rejected(settings):
    app = create_app(settings)
    with TestClient(app, base_url="http://evil.example") as c:
        r = c.get("/api/health")
    assert r.status_code == 400


def test_no_cors_headers(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_identity_header_is_logged(client, caplog):
    with caplog.at_level("INFO", logger="viz.access"):
        client.get("/api/health", headers={"X-Forwarded-Email": "someone@example.com"})
    assert any("user=someone@example.com" in rec.getMessage() for rec in caplog.records)


def test_missing_identity_logs_anonymous(client, caplog):
    with caplog.at_level("INFO", logger="viz.access"):
        client.get("/api/health")
    assert any("user=-" in rec.getMessage() for rec in caplog.records)
```

Create `tests/server/__init__.py` as an empty file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/server -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'viz.server'`

- [ ] **Step 3: Implement middleware, routes stub and app factory**

```python
# viz/server/middleware.py
"""Security headers on every response, and the identity slot."""
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

CSP = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
    "connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}

access_log = logging.getLogger("viz.access")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response


class IdentityMiddleware(BaseHTTPMiddleware):
    """Reads the identity header set by an upstream SSO proxy. No-op without one.

    This is the auth slot: a real deployment puts the site behind a proxy that
    sets the header, and this middleware records it. Nothing here enforces.
    """

    def __init__(self, app, header: str):
        super().__init__(app)
        self.header = header

    async def dispatch(self, request: Request, call_next):
        user = request.headers.get(self.header) or None
        request.state.user = user
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        access_log.info(
            "user=%s method=%s path=%s status=%s ms=%.1f",
            user or "-", request.method, request.url.path, response.status_code, elapsed_ms,
        )
        return response
```

```python
# viz/server/routes.py
"""Read-only API. Four routes plus health. No writes anywhere."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
```

```python
# viz/server/app.py
"""FastAPI application factory."""
from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..config import Settings
from ..storage import get_storage
from .middleware import IdentityMiddleware, SecurityHeadersMiddleware
from .routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    storage = get_storage(settings)

    app = FastAPI(title="viz-site", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.storage = storage

    # Last added runs outermost. Order: TrustedHost -> SecurityHeaders -> Identity -> routes.
    app.add_middleware(IdentityMiddleware, header=settings.auth_header)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

    app.include_router(router, prefix="/api")
    return app
```

Create `viz/server/__init__.py` as an empty file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/server -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add viz/server tests/server
git commit -m "feat: FastAPI app factory with security headers, trusted hosts and identity slot"
```

---

### Task 9: Document loading and the tree

**Files:**
- Create: `viz/server/documents.py`, `viz/server/tree.py`, `tests/server/test_documents.py`, `tests/server/test_tree.py`

**Interfaces:**
- Produces (documents):
  - `class DocumentTooLarge(ValueError)`
  - `load_chart(storage, settings, chart_id) -> dict`, `load_dashboard(storage, settings, dashboard_id) -> dict`, `load_folder(storage, settings, kind, folder) -> dict | None` (None when absent). Each raises `NotFound`, `DocumentTooLarge`, or `SchemaError` (including for JSON parse errors and id mismatch).
  - `public_chart(doc: dict) -> dict` (strips `source.sql` and `source.warehouse_id` unless `show_sql`)
- Produces (tree):
  - `build_tree(storage, settings) -> dict` with shape `{"charts": FolderNode, "dashboards": FolderNode, "built_at": str}`
  - `FolderNode = {"type": "folder", "path": str, "name": str, "title": str | None, "description": str | None, "order": int | None, "folders": [FolderNode], "items": [ChartNode | DashboardNode]}`
  - `ChartNode = {"type": "chart", "id", "title", "description", "tags", "renderer", "lane", "static": bool, "updated_at"}` or `{"type": "chart", "id", "error": str}`
  - `DashboardNode = {"type": "dashboard", "id", "title", "description", "tags", "controls", "updated_at"}` or `{"type": "dashboard", "id", "error": str}`
  - `class TreeCache(storage, settings)` with `async get() -> dict`, `invalidate()`, and attribute `builds: int` counting builds.

- [ ] **Step 1: Write the failing document tests**

```python
# tests/server/test_documents.py
import json

import pytest

from viz.schemas import SchemaError
from viz.server import documents
from viz.storage import NotFound, get_storage


@pytest.fixture
def storage(settings):
    return get_storage(settings)


def test_load_chart(storage, settings):
    doc = documents.load_chart(storage, settings, "sales/revenue-by-region")
    assert doc["id"] == "sales/revenue-by-region"
    assert doc["renderer"] == "vega-lite"


def test_load_dashboard(storage, settings):
    doc = documents.load_dashboard(storage, settings, "sales/overview")
    assert doc["layout"][0]["chart"] == "sales/revenue-by-region"


def test_load_folder_present_and_absent(storage, settings):
    assert documents.load_folder(storage, settings, "charts", "sales")["title"] == "Sales"
    assert documents.load_folder(storage, settings, "charts", "") is None


def test_missing_chart(storage, settings):
    with pytest.raises(NotFound):
        documents.load_chart(storage, settings, "sales/nope")


def test_invalid_json_is_schema_error(storage, settings):
    storage.put("viz/charts/broken/chart.json", b"{not json", "application/json")
    with pytest.raises(SchemaError) as excinfo:
        documents.load_chart(storage, settings, "broken")
    assert "invalid JSON" in str(excinfo.value)


def test_id_mismatch_is_schema_error(storage, settings):
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    storage.put("viz/charts/sales/copy/chart.json", json.dumps(doc).encode(), "application/json")
    with pytest.raises(SchemaError) as excinfo:
        documents.load_chart(storage, settings, "sales/copy")
    assert "expected 'sales/copy'" in str(excinfo.value)


def test_too_large_document(storage, settings):
    big = json.dumps({"schema_version": 1, "pad": "x" * (settings.max_document_bytes + 10)}).encode()
    storage.put("viz/charts/big/chart.json", big, "application/json")
    with pytest.raises(documents.DocumentTooLarge):
        documents.load_chart(storage, settings, "big")


def test_public_chart_strips_sql_by_default():
    doc = {"id": "a", "source": {"kind": "databricks-sql", "sql": "SELECT 1", "warehouse_id": "w", "schedule": "0 6 * * *"}}
    out = documents.public_chart(doc)
    assert out["source"] == {"kind": "databricks-sql", "schedule": "0 6 * * *", "show_sql": False}
    assert "sql" in doc["source"], "input must not be mutated"


def test_public_chart_keeps_sql_when_show_sql():
    doc = {"id": "a", "source": {"kind": "databricks-sql", "sql": "SELECT 1", "warehouse_id": "w", "show_sql": True}}
    out = documents.public_chart(doc)
    assert out["source"]["sql"] == "SELECT 1"
    assert out["source"]["warehouse_id"] == "w"


def test_public_chart_without_source_is_unchanged():
    doc = {"id": "a", "title": "t"}
    assert documents.public_chart(doc) == doc
```

- [ ] **Step 2: Write the failing tree tests**

```python
# tests/server/test_tree.py
import asyncio
import json

import pytest

from viz.server.tree import TreeCache, build_tree
from viz.storage import get_storage


@pytest.fixture
def storage(settings):
    return get_storage(settings)


def _find_folder(node, name):
    return next(f for f in node["folders"] if f["name"] == name)


def test_tree_shape(storage, settings):
    tree = build_tree(storage, settings)
    assert set(tree) == {"charts", "dashboards", "built_at"}
    sales = _find_folder(tree["charts"], "sales")
    assert sales["path"] == "sales"
    assert sales["title"] == "Sales"
    assert sales["order"] == 10
    ids = sorted(item["id"] for item in sales["items"])
    assert ids == ["sales/revenue-by-region", "sales/total-revenue"]
    chart = next(i for i in sales["items"] if i["id"] == "sales/total-revenue")
    assert chart["type"] == "chart"
    assert chart["renderer"] == "stat"
    assert chart["lane"] == "small"
    assert chart["static"] is True
    refreshable = next(i for i in sales["items"] if i["id"] == "sales/revenue-by-region")
    assert refreshable["static"] is False


def test_dashboard_node_carries_controls(storage, settings):
    tree = build_tree(storage, settings)
    sales = _find_folder(tree["dashboards"], "sales")
    dash = sales["items"][0]
    assert dash["type"] == "dashboard"
    assert dash["id"] == "sales/overview"
    assert [c["id"] for c in dash["controls"]] == ["period", "region"]


def test_folder_without_metadata_uses_slug(storage, settings):
    storage.put("viz/charts/misc/deep/thing/chart.json", b"{}", "application/json")
    tree = build_tree(storage, settings)
    misc = _find_folder(tree["charts"], "misc")
    assert misc["title"] is None
    assert misc["name"] == "misc"
    deep = _find_folder(misc, "deep")
    assert deep["items"][0]["id"] == "misc/deep/thing"
    assert "error" in deep["items"][0]


def test_folder_sorting_order_then_name(storage, settings):
    storage.put("viz/charts/zeta/_folder.json", json.dumps({"schema_version": 1, "order": 1}).encode(), "application/json")
    storage.put("viz/charts/alpha/x/chart.json", b"{}", "application/json")
    tree = build_tree(storage, settings)
    names = [f["name"] for f in tree["charts"]["folders"]]
    assert names == ["zeta", "sales", "alpha"]  # order 1, order 10, then unordered by name


def test_invalid_chart_becomes_error_node(storage, settings):
    storage.put("viz/charts/sales/bad/chart.json", b"{not json", "application/json")
    tree = build_tree(storage, settings)
    sales = _find_folder(tree["charts"], "sales")
    bad = next(i for i in sales["items"] if i["id"] == "sales/bad")
    assert "invalid JSON" in bad["error"]


def test_invalid_id_becomes_error_node(storage, settings):
    storage.put("viz/charts/Sales/chart.json", b"{}", "application/json")
    tree = build_tree(storage, settings)
    bad = next(i for i in tree["charts"]["items"] if i["id"] == "Sales")
    assert "invalid id" in bad["error"]


def test_prefix_conflict_marks_both(storage, settings):
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc["id"] = "sales"
    storage.put("viz/charts/sales/chart.json", json.dumps(doc).encode(), "application/json")
    tree = build_tree(storage, settings)
    top = next(i for i in tree["charts"]["items"] if i["id"] == "sales")
    assert "conflicts" in top["error"]
    sales = _find_folder(tree["charts"], "sales")
    child = next(i for i in sales["items"] if i["id"] == "sales/total-revenue")
    assert "conflicts" in child["error"]


async def test_cache_builds_once_and_refreshes_in_background(storage, settings):
    settings.tree_ttl_seconds = 0
    cache = TreeCache(storage, settings)
    first = await cache.get()
    assert cache.builds == 1
    second = await cache.get()          # stale: returns old value, kicks off one refresh
    assert second is first
    await asyncio.sleep(0.2)
    assert cache.builds == 2
    third = await cache.get()
    assert third is not first


async def test_cache_single_flight_on_cold_start(storage, settings):
    cache = TreeCache(storage, settings)
    results = await asyncio.gather(*(cache.get() for _ in range(5)))
    assert cache.builds == 1
    assert all(r is results[0] for r in results)


async def test_cache_invalidate(storage, settings):
    cache = TreeCache(storage, settings)
    await cache.get()
    cache.invalidate()
    await cache.get()
    assert cache.builds == 2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/server/test_documents.py tests/server/test_tree.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 4: Implement documents**

```python
# viz/server/documents.py
"""Load and validate one document from storage. The only way the server reads JSON."""
import json
from typing import Callable

from ..config import Settings
from ..ids import chart_key, dashboard_key, folder_key
from ..schemas import SchemaError, validate_chart, validate_dashboard, validate_folder
from ..storage import NotFound, Storage


class DocumentTooLarge(ValueError):
    pass


def _read(storage: Storage, settings: Settings, key: str) -> dict:
    info = storage.head(key)
    if info.size > settings.max_document_bytes:
        raise DocumentTooLarge(f"{key}: {info.size} bytes exceeds {settings.max_document_bytes}")
    raw = storage.get(key)
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SchemaError([f"$: invalid JSON ({err})"]) from err


def _load(storage, settings, key, validate: Callable[[dict], dict], expected_id: str) -> dict:
    doc = validate(_read(storage, settings, key))
    if doc.get("id") != expected_id:
        raise SchemaError([f"id: expected {expected_id!r}, found {doc.get('id')!r}"])
    return doc


def load_chart(storage: Storage, settings: Settings, chart_id: str) -> dict:
    return _load(storage, settings, chart_key(settings.root_prefix, chart_id), validate_chart, chart_id)


def load_dashboard(storage: Storage, settings: Settings, dashboard_id: str) -> dict:
    return _load(storage, settings, dashboard_key(settings.root_prefix, dashboard_id), validate_dashboard, dashboard_id)


def load_folder(storage: Storage, settings: Settings, kind: str, folder: str) -> dict | None:
    try:
        return validate_folder(_read(storage, settings, folder_key(settings.root_prefix, kind, folder)))
    except NotFound:
        return None


def public_chart(doc: dict) -> dict:
    """The chart as the API returns it. SQL text stays in the bucket unless show_sql."""
    source = doc.get("source")
    if not source or source.get("show_sql"):
        return doc
    out = dict(doc)
    public = {"kind": source.get("kind"), "show_sql": False}
    if "schedule" in source:
        public["schedule"] = source["schedule"]
    out["source"] = public
    return out
```

- [ ] **Step 5: Implement the tree**

```python
# viz/server/tree.py
"""Build the folder tree from storage and cache it with single-flight refresh."""
import asyncio
import time
from datetime import datetime, timezone

from ..config import Settings
from ..ids import InvalidId, is_ancestor, validate_id
from ..schemas import SchemaError
from ..storage import Storage
from .documents import DocumentTooLarge, load_chart, load_dashboard, load_folder


def _folder_node(path: str) -> dict:
    return {"type": "folder", "path": path, "name": path.rsplit("/", 1)[-1] if path else "",
            "title": None, "description": None, "order": None, "folders": [], "items": []}


def _chart_node(storage, settings, chart_id: str) -> dict:
    try:
        validate_id(chart_id)
        doc = load_chart(storage, settings, chart_id)
    except InvalidId:
        return {"type": "chart", "id": chart_id, "error": "invalid id"}
    except (SchemaError, DocumentTooLarge) as err:
        return {"type": "chart", "id": chart_id, "error": str(err)}
    return {
        "type": "chart", "id": chart_id, "title": doc["title"], "description": doc.get("description"),
        "tags": doc.get("tags", []), "renderer": doc["renderer"], "lane": doc["data"]["lane"],
        "static": "source" not in doc, "updated_at": doc.get("updated_at"),
    }


def _dashboard_node(storage, settings, dashboard_id: str) -> dict:
    try:
        validate_id(dashboard_id)
        doc = load_dashboard(storage, settings, dashboard_id)
    except InvalidId:
        return {"type": "dashboard", "id": dashboard_id, "error": "invalid id"}
    except (SchemaError, DocumentTooLarge) as err:
        return {"type": "dashboard", "id": dashboard_id, "error": str(err)}
    return {
        "type": "dashboard", "id": dashboard_id, "title": doc["title"], "description": doc.get("description"),
        "tags": doc.get("tags", []), "controls": doc.get("controls", []), "updated_at": doc.get("updated_at"),
    }


def _mark_conflicts(nodes: list[dict]) -> None:
    ids = [n["id"] for n in nodes]
    for node in nodes:
        others = [other for other in ids if other != node["id"] and (is_ancestor(node["id"], other) or is_ancestor(other, node["id"]))]
        if others:
            node["error"] = f"id conflicts with {', '.join(sorted(others))}"


def _assemble(kind: str, storage, settings, items: list[dict], folder_paths: set[str]) -> dict:
    root = _folder_node("")
    index = {"": root}

    def folder_for(path: str) -> dict:
        if path in index:
            return index[path]
        parent_path = path.rsplit("/", 1)[0] if "/" in path else ""
        parent = folder_for(parent_path)
        node = _folder_node(path)
        parent["folders"].append(node)
        index[path] = node
        return node

    for path in sorted(folder_paths):
        folder_for(path)
    for item in items:
        parent_path = item["id"].rsplit("/", 1)[0] if "/" in item["id"] else ""
        folder_for(parent_path)["items"].append(item)

    for path, node in index.items():
        meta = load_folder(storage, settings, kind, path) if path in folder_paths or path == "" else None
        if meta:
            node["title"] = meta.get("title")
            node["description"] = meta.get("description")
            node["order"] = meta.get("order")

    def sort(node: dict) -> None:
        node["folders"].sort(key=lambda f: (f["order"] is None, f["order"] if f["order"] is not None else 0, f["title"] or f["name"]))
        node["items"].sort(key=lambda i: (i.get("title") or i["id"]).lower())
        for child in node["folders"]:
            sort(child)

    sort(root)
    return root


def build_tree(storage: Storage, settings: Settings) -> dict:
    root = settings.root_prefix
    charts_prefix = f"{root}charts/"
    dashboards_prefix = f"{root}dashboards/"

    chart_ids, chart_folders = [], set()
    for obj in storage.list(charts_prefix):
        rel = obj.key[len(charts_prefix):]
        if rel.endswith("/chart.json"):
            chart_ids.append(rel[: -len("/chart.json")])
        elif rel.endswith("_folder.json"):
            chart_folders.add(rel[: -len("_folder.json")].rstrip("/"))

    dashboard_ids, dashboard_folders = [], set()
    for obj in storage.list(dashboards_prefix):
        rel = obj.key[len(dashboards_prefix):]
        if rel.endswith("_folder.json"):
            dashboard_folders.add(rel[: -len("_folder.json")].rstrip("/"))
        elif rel.endswith(".json"):
            dashboard_ids.append(rel[: -len(".json")])

    charts = [_chart_node(storage, settings, cid) for cid in chart_ids]
    _mark_conflicts(charts)
    dashboards = [_dashboard_node(storage, settings, did) for did in dashboard_ids]
    _mark_conflicts(dashboards)

    return {
        "charts": _assemble("charts", storage, settings, charts, chart_folders),
        "dashboards": _assemble("dashboards", storage, settings, dashboards, dashboard_folders),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


class TreeCache:
    """Serve the last tree; rebuild in the background when stale; never rebuild twice at once."""

    def __init__(self, storage: Storage, settings: Settings):
        self.storage = storage
        self.settings = settings
        self.builds = 0
        self._value: dict | None = None
        self._built_at = 0.0
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None

    def _build(self) -> dict:
        self.builds += 1
        return build_tree(self.storage, self.settings)

    async def get(self) -> dict:
        if self._value is None:
            async with self._lock:
                if self._value is None:
                    self._value = await asyncio.to_thread(self._build)
                    self._built_at = time.monotonic()
            return self._value
        stale = time.monotonic() - self._built_at >= self.settings.tree_ttl_seconds
        if stale and (self._refresh_task is None or self._refresh_task.done()):
            self._refresh_task = asyncio.create_task(self._refresh())
        return self._value

    async def _refresh(self) -> None:
        value = await asyncio.to_thread(self._build)
        self._value = value
        self._built_at = time.monotonic()

    def invalidate(self) -> None:
        self._value = None
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/server/test_documents.py tests/server/test_tree.py -v`
Expected: PASS (all). If `test_folder_sorting_order_then_name` fails on ordering, check that unordered folders sort after ordered ones: the sort key is `(order is None, order, title or name)`.

- [ ] **Step 7: Commit**

```bash
git add viz/server/documents.py viz/server/tree.py tests/server/test_documents.py tests/server/test_tree.py
git commit -m "feat: document loading with validation, tree builder and single-flight cache"
```

---

### Task 10: Tree, dashboard and chart routes

**Files:**
- Modify: `viz/server/routes.py`, `viz/server/app.py`
- Create: `tests/server/test_routes.py`

**Interfaces:**
- Produces: `GET /api/tree`, `GET /api/dashboards/{id}`, `GET /api/charts/{id}`. Error bodies: `{"detail": {"errors": [...]}}` for 422; `{"detail": "..."}` otherwise. Status codes: 400 invalid id, 404 not found, 413 too large, 422 invalid document. `app.state.tree: TreeCache`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/server/test_routes.py
import json

import pytest

from viz.storage import get_storage


@pytest.fixture
def storage(settings):
    return get_storage(settings)


def test_tree(client):
    r = client.get("/api/tree")
    assert r.status_code == 200
    body = r.json()
    assert body["charts"]["type"] == "folder"
    assert [f["name"] for f in body["dashboards"]["folders"]] == ["sales"]


def test_dashboard(client):
    r = client.get("/api/dashboards/sales/overview")
    assert r.status_code == 200
    assert r.json()["id"] == "sales/overview"


def test_chart_strips_sql_unless_show_sql(client, storage):
    r = client.get("/api/charts/sales/revenue-by-region")
    assert r.status_code == 200
    assert r.json()["source"]["sql"].startswith("SELECT")  # sample sets show_sql true

    doc = json.loads(storage.get("viz/charts/sales/revenue-by-region/chart.json"))
    doc["source"].pop("show_sql")
    storage.put("viz/charts/sales/revenue-by-region/chart.json", json.dumps(doc).encode(), "application/json")
    r = client.get("/api/charts/sales/revenue-by-region")
    assert r.status_code == 200
    assert r.json()["source"] == {"kind": "databricks-sql", "schedule": "0 6 * * *", "show_sql": False}


@pytest.mark.parametrize("path", ["/api/charts/Sales", "/api/charts/a//b", "/api/dashboards/../x", "/api/charts/a%2F..%2Fb"])
def test_invalid_ids_are_400(client, path):
    r = client.get(path)
    assert r.status_code == 400


def test_missing_is_404(client):
    assert client.get("/api/charts/sales/nope").status_code == 404
    assert client.get("/api/dashboards/sales/nope").status_code == 404


def test_invalid_document_is_422_with_errors(client, storage):
    storage.put("viz/charts/sales/bad/chart.json", b'{"schema_version": 1}', "application/json")
    r = client.get("/api/charts/sales/bad")
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    assert any("required" in e for e in errors)


def test_too_large_is_413(client, storage, settings):
    big = json.dumps({"schema_version": 1, "pad": "x" * (settings.max_document_bytes + 10)}).encode()
    storage.put("viz/charts/sales/big/chart.json", big, "application/json")
    assert client.get("/api/charts/sales/big").status_code == 413


def test_id_mismatch_is_422(client, storage):
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    storage.put("viz/charts/sales/copy/chart.json", json.dumps(doc).encode(), "application/json")
    r = client.get("/api/charts/sales/copy")
    assert r.status_code == 422
    assert "expected 'sales/copy'" in r.json()["detail"]["errors"][0]


def test_tree_reflects_new_chart_after_ttl(client, storage, settings):
    r1 = client.get("/api/tree")
    assert all(i["id"] != "sales/new" for i in r1.json()["charts"]["folders"][0]["items"])
    client.app.state.tree.invalidate()
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc["id"] = "sales/new"
    storage.put("viz/charts/sales/new/chart.json", json.dumps(doc).encode(), "application/json")
    r2 = client.get("/api/tree")
    assert any(i["id"] == "sales/new" for i in r2.json()["charts"]["folders"][0]["items"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/server/test_routes.py -v`
Expected: FAIL with 404s (routes do not exist yet)

- [ ] **Step 3: Implement the routes and wire the cache**

Replace `viz/server/routes.py`:

```python
# viz/server/routes.py
"""Read-only API. Four routes plus health. No writes anywhere."""
from fastapi import APIRouter, HTTPException, Request

from ..ids import InvalidId, validate_id
from ..schemas import SchemaError
from ..storage import NotFound
from .documents import DocumentTooLarge, load_chart, load_dashboard, public_chart

router = APIRouter()


def _id(value: str) -> str:
    try:
        return validate_id(value)
    except InvalidId:
        raise HTTPException(status_code=400, detail="invalid id")


def _document(loader, request: Request, doc_id: str) -> dict:
    try:
        return loader(request.app.state.storage, request.app.state.settings, doc_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="not found")
    except DocumentTooLarge as err:
        raise HTTPException(status_code=413, detail=str(err))
    except SchemaError as err:
        raise HTTPException(status_code=422, detail={"errors": err.errors})


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/tree")
async def tree(request: Request):
    return await request.app.state.tree.get()


@router.get("/dashboards/{dashboard_id:path}")
def dashboard(dashboard_id: str, request: Request):
    return _document(load_dashboard, request, _id(dashboard_id))


@router.get("/charts/{chart_id:path}")
def chart(chart_id: str, request: Request):
    return public_chart(_document(load_chart, request, _id(chart_id)))
```

In `viz/server/app.py`, add the import and the cache:

```python
from .tree import TreeCache
```

and after `app.state.storage = storage`:

```python
    app.state.tree = TreeCache(storage, settings)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/server -v`
Expected: PASS (all). If the `a%2F..%2Fb` case returns 404 instead of 400, Starlette decoded the path and matched `a/../b`; `validate_id` rejects `..` so `_id` must run before any storage call, which it does in `chart()`. Check the route ordering.

- [ ] **Step 5: Commit**

```bash
git add viz/server/routes.py viz/server/app.py tests/server/test_routes.py
git commit -m "feat: tree, dashboard and chart routes with source stripping"
```

---

### Task 11: Streaming data route with ETag and Range

**Files:**
- Modify: `viz/server/routes.py`
- Create: `tests/server/test_data_route.py`

**Interfaces:**
- Produces: `GET /api/data/{id}`. Headers: `ETag`, `Accept-Ranges: bytes`, `Content-Disposition: attachment; filename="data.<fmt>"`, `Cache-Control: private, max-age=0, must-revalidate`, `Content-Length`. Media type `application/json; charset=utf-8` for json, `application/octet-stream` for parquet. Supports `If-None-Match` (304) and single `Range` (206, 416).

- [ ] **Step 1: Write the failing tests**

```python
# tests/server/test_data_route.py
import json

import pytest

from viz.storage import get_storage


@pytest.fixture
def storage(settings):
    return get_storage(settings)


def test_json_data_full(client, storage):
    r = client.get("/api/data/sales/revenue-by-region")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-disposition"] == 'attachment; filename="data.json"'
    assert r.headers["cache-control"] == "private, max-age=0, must-revalidate"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["etag"].startswith('"')
    assert int(r.headers["content-length"]) == len(r.content)
    assert len(json.loads(r.content)) == 144


def test_etag_304(client):
    first = client.get("/api/data/sales/revenue-by-region")
    r = client.get("/api/data/sales/revenue-by-region", headers={"If-None-Match": first.headers["etag"]})
    assert r.status_code == 304
    assert r.content == b""


def test_range_request(client):
    full = client.get("/api/data/sales/revenue-by-region").content
    r = client.get("/api/data/sales/revenue-by-region", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.content == full[10:20]
    assert r.headers["content-range"] == f"bytes 10-19/{len(full)}"
    assert r.headers["content-length"] == "10"
    r = client.get("/api/data/sales/revenue-by-region", headers={"Range": "bytes=-5"})
    assert r.status_code == 206
    assert r.content == full[-5:]
    r = client.get("/api/data/sales/revenue-by-region", headers={"Range": f"bytes={len(full) - 3}-"})
    assert r.content == full[-3:]


def test_unsatisfiable_range_416(client):
    full = client.get("/api/data/sales/revenue-by-region").content
    r = client.get("/api/data/sales/revenue-by-region", headers={"Range": f"bytes={len(full) + 5}-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(full)}"


def test_malformed_range_is_ignored(client):
    r = client.get("/api/data/sales/revenue-by-region", headers={"Range": "items=1-2"})
    assert r.status_code == 200


def test_parquet_media_type_and_missing_file(client, storage):
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc.update({"id": "sales/big", "renderer": "vega-lite", "spec": {"data": {"name": "data"}, "mark": "bar"},
                "data": {**doc["data"], "format": "parquet", "lane": "large", "bytes": 4},
                "aggregate": "SELECT 1"})
    storage.put("viz/charts/sales/big/chart.json", json.dumps(doc).encode(), "application/json")
    assert client.get("/api/data/sales/big").status_code == 404   # chart exists, data file does not
    storage.put("viz/charts/sales/big/data.parquet", b"PAR1", "application/octet-stream")
    r = client.get("/api/data/sales/big")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"] == 'attachment; filename="data.parquet"'
    assert r.content == b"PAR1"


def test_data_for_invalid_chart_is_422(client, storage):
    storage.put("viz/charts/sales/bad/chart.json", b"{}", "application/json")
    assert client.get("/api/data/sales/bad").status_code == 422


def test_data_invalid_id_400_and_missing_404(client):
    assert client.get("/api/data/Bad").status_code == 400
    assert client.get("/api/data/sales/nope").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/server/test_data_route.py -v`
Expected: FAIL with 404 (route does not exist)

- [ ] **Step 3: Implement the data route**

Add to `viz/server/routes.py` (imports at top, route at bottom):

```python
import re

from fastapi.responses import Response, StreamingResponse

from ..ids import data_key

MEDIA_TYPES = {"json": "application/json; charset=utf-8", "parquet": "application/octet-stream"}
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None | str:
    """None: no usable range. 'unsatisfiable': 416. Otherwise (start, end) inclusive."""
    if not header:
        return None
    m = _RANGE.match(header.strip())
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return None
    first, last = m.group(1), m.group(2)
    if first == "":
        suffix = int(last)
        if suffix == 0:
            return "unsatisfiable"
        return max(size - suffix, 0), size - 1
    start = int(first)
    end = size - 1 if last == "" else min(int(last), size - 1)
    if start >= size or start > end:
        return "unsatisfiable"
    return start, end


@router.get("/data/{chart_id:path}")
def data(chart_id: str, request: Request):
    chart_id = _id(chart_id)
    doc = _document(load_chart, request, chart_id)
    settings = request.app.state.settings
    storage = request.app.state.storage
    fmt = doc["data"]["format"]
    key = data_key(settings.root_prefix, chart_id, fmt)
    try:
        info = storage.head(key)
    except NotFound:
        raise HTTPException(status_code=404, detail="data file not found")

    etag = f'"{info.etag}"'
    headers = {
        "ETag": etag,
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'attachment; filename="data.{fmt}"',
        "Cache-Control": "private, max-age=0, must-revalidate",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    rng = _parse_range(request.headers.get("range"), info.size)
    if rng == "unsatisfiable":
        headers["Content-Range"] = f"bytes */{info.size}"
        raise HTTPException(status_code=416, detail="range not satisfiable", headers=headers)
    if rng is None:
        headers["Content-Length"] = str(info.size)
        return StreamingResponse(storage.open(key), status_code=200, headers=headers, media_type=MEDIA_TYPES[fmt])

    start, end = rng
    headers["Content-Range"] = f"bytes {start}-{end}/{info.size}"
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(storage.open(key, start=start, end=end), status_code=206, headers=headers,
                             media_type=MEDIA_TYPES[fmt])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/server -v`
Expected: PASS (all). If `content-length` on the 200 response does not match, Starlette may be adding its own header for streaming responses; keep ours by setting it explicitly as above, which Starlette respects.

- [ ] **Step 5: Commit**

```bash
git add viz/server/routes.py tests/server/test_data_route.py
git commit -m "feat: streaming data route with ETag, Range and attachment headers"
```

---

### Task 12: Static front end serving and the server entry point

**Files:**
- Create: `viz/server/static.py`, `viz/server/__main__.py`, `tests/server/test_static.py`
- Modify: `viz/server/app.py`

**Interfaces:**
- Produces: `mount_spa(app: FastAPI, dist: Path) -> None`; `main() -> None` running uvicorn with `settings.host` and `settings.port`. Any non-`/api` path serves a file from `dist` if it exists, otherwise `dist/index.html`. With no `dist`, non-API paths return 404 JSON. Unknown `/api/...` paths return 404 JSON, never the SPA.

- [ ] **Step 1: Write the failing tests**

```python
# tests/server/test_static.py
from fastapi.testclient import TestClient

from viz.server.app import create_app


def test_no_dist_returns_404_json(client):
    r = client.get("/dashboards/sales/overview")
    assert r.status_code == 404
    assert r.json()["detail"] == "front end not built"


def test_unknown_api_path_is_404_not_spa(client):
    r = client.get("/api/nothing/here")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_spa_fallback_and_assets(settings, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>viz</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    settings.web_dist = dist
    client = TestClient(create_app(settings))

    r = client.get("/")
    assert r.status_code == 200 and "<title>viz</title>" in r.text
    r = client.get("/dashboards/sales/overview")
    assert r.status_code == 200 and "<title>viz</title>" in r.text
    r = client.get("/assets/app.js")
    assert r.status_code == 200 and r.text == "console.log(1)"
    r = client.get("/assets/../index.html")
    assert r.status_code in (200, 404)  # normalized by the client; must never escape dist
    assert r.headers["content-security-policy"]


def test_security_headers_on_static(settings, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    settings.web_dist = dist
    client = TestClient(create_app(settings))
    r = client.get("/anything")
    assert r.headers["x-frame-options"] == "DENY"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/server/test_static.py -v`
Expected: FAIL (`/dashboards/...` currently returns FastAPI's default 404 with `{"detail": "Not Found"}`)

- [ ] **Step 3: Implement**

```python
# viz/server/static.py
"""Serve the built front end. Every non-API path falls back to index.html."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse


def mount_spa(app: FastAPI, dist: Path) -> None:
    dist = Path(dist)
    index = dist / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"detail": "not found"}, status_code=404)
        if not index.is_file():
            return JSONResponse({"detail": "front end not built"}, status_code=404)
        if path:
            candidate = (dist / path).resolve()
            if candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
        return FileResponse(index)
```

```python
# viz/server/__main__.py
"""Run the server: `python -m viz.server` or `viz-server`."""
import uvicorn

from ..config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run("viz.server.app:create_app", factory=True, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
```

In `viz/server/app.py`, import and call after `include_router`:

```python
from .static import mount_spa
```

```python
    app.include_router(router, prefix="/api")
    mount_spa(app, settings.web_dist)
    return app
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -v`
Expected: PASS (all)

- [ ] **Step 5: Smoke-run the server against the sample bucket**

Run in the background: `viz-server`
Then: `curl -s http://127.0.0.1:8000/api/tree | head -c 300` and `curl -sI http://127.0.0.1:8000/api/data/sales/revenue-by-region`
Expected: JSON tree with a `sales` folder; headers include `content-security-policy` and `content-disposition: attachment; filename="data.json"`. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add viz/server/static.py viz/server/__main__.py viz/server/app.py tests/server/test_static.py
git commit -m "feat: SPA static serving and viz-server entry point"
```

---

## Self-review

**Spec coverage (sections this plan owns):**

| Spec item | Task |
|---|---|
| 4.1 layout, id pattern, derived data key | 2, 9 |
| 4.2 chart.json field rules, lane caps, closed `source`, `show_sql`, column-name pattern | 3 |
| 4.3 dashboard controls and layout | 3 |
| 4.4 `_folder.json` | 3, 9 |
| 4.5 schemas as single source of truth, fixtures | 3 |
| 5.1 four routes, id validation, tree cache TTL, 422 on validation | 10, 11, 9 |
| 5.1 configuration table, no Databricks vars in server | 6 |
| 5.1 IAM policies in `deploy/` | Plan 4 |
| 12.2 identity slot with access log, no CORS, trusted host, headers, streamed data with ETag/Range/attachment, source stripping, single-flight tree, size caps, id conflicts | 8, 9, 10, 11 |
| 12.6 `.gitignore`, synthetic sample bucket, gitleaks in CI | 1, 7 (CI check in Plan 4) |
| 8 storage suite on both backends via moto; server route tests incl. traversal | 4, 5, 10 |
| 9 repo layout (Python side) | 1 |

Gaps deliberately left for later plans: `web/` (Plan 2), `viz/publish` and `skills/` (Plan 3), `viz/refresh` scaffold, Dockerfile, Helm, CI, IAM policy files (Plan 4).

**Placeholder scan:** none. Every code step is complete.

**Type consistency:** `Storage.open(key, start, end)` is used with the same signature in Task 4, 5 and 11. `load_chart(storage, settings, id)` matches between Task 9 and 10/11. `TreeCache.get()` is async and awaited in Task 10. `Settings.web_dist` is defined in Task 6 and consumed in Task 12. `public_chart` output shape in Task 9 matches the assertion in Task 10.
