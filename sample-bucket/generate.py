"""Regenerate the sample bucket. Deterministic, synthetic, safe to commit.

Run from the repo root:  python sample-bucket/generate.py
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent / "viz"
SKILL_EXAMPLES = Path(__file__).resolve().parents[1] / "skills" / "publish-viz" / "examples"
AUTHOR = "sample@example.com"
STAMP = "2026-09-22T10:00:00Z"
REGIONS = ["EMEA", "NA", "APAC", "LATAM"]
COLUMNS = [
    {"name": "month", "type": "date"},
    {"name": "region", "type": "string"},
    {"name": "revenue", "type": "number"},
    {"name": "orders", "type": "integer"},
]

RENDERERS = ["vega-lite"]
PRODUCTS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
ORDER_LINES = 200_000
QUARTER_COLUMNS = [
    {"name": "quarter", "type": "string"},
    {"name": "region", "type": "string"},
    {"name": "orders", "type": "integer"},
]
LINE_COLUMNS = [
    {"name": "day", "type": "date"},
    {"name": "region", "type": "string"},
    {"name": "product", "type": "string"},
    {"name": "amount", "type": "number"},
]
LINE_AGGREGATE = "SELECT day, sum(amount) AS amount FROM data GROUP BY day ORDER BY day"


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


def chart_doc(chart_id, title, description, renderer, spec, data_rows, data_bytes, source=None,
              columns=COLUMNS, fmt="json", lane="small", aggregate=None, tags=("sales", "sample")):
    doc = {
        "schema_version": 1,
        "id": chart_id,
        "title": title,
        "description": description,
        "tags": list(tags),
        "author": AUTHOR,
        "created_at": STAMP,
        "updated_at": STAMP,
        "renderer": renderer,
        "spec": spec,
        "data": {"format": fmt, "lane": lane, "rows": data_rows, "bytes": data_bytes, "columns": columns},
        "aggregate": aggregate,
    }
    if source:
        doc["source"] = source
    return doc


def quarterly(data: list[dict]) -> list[dict]:
    totals: dict[tuple[str, str], int] = {}
    for r in data:
        year, month = r["month"][:4], int(r["month"][5:7])
        quarter = f"{year}-Q{(month - 1) // 3 + 1}"
        totals[(quarter, r["region"])] = totals.get((quarter, r["region"]), 0) + r["orders"]
    return [{"quarter": q, "region": region, "orders": n} for (q, region), n in sorted(totals.items())]


def order_lines() -> pa.Table:
    rng = random.Random(20260922)
    start = date(2024, 1, 1)
    lines = []
    for _ in range(ORDER_LINES):
        day = start + timedelta(days=rng.randrange(730))
        region = rng.choice(REGIONS)
        product = rng.choice(PRODUCTS)
        amount = round(rng.lognormvariate(4.5, 0.6), 2)
        lines.append((day, region, product, amount))
    lines.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    return pa.table({
        "day": pa.array([t[0] for t in lines], pa.date32()),
        "region": pa.array([t[1] for t in lines], pa.string()),
        "product": pa.array([t[2] for t in lines], pa.string()),
        "amount": pa.array([t[3] for t in lines], pa.float64()),
    })


def write_parquet(path: Path, table: pa.Table) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="snappy")
    return path.stat().st_size


def time_series_spec(renderer: str) -> dict:
    if renderer == "vega-lite":
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "data": {"name": "data"},
            "width": "container",
            "height": "container",
            "mark": {"type": "line", "point": True},
            "encoding": {
                "x": {"field": "month", "type": "temporal", "title": "Month"},
                "y": {"field": "revenue", "type": "quantitative", "title": "Revenue"},
                "color": {"field": "region", "type": "nominal", "title": "Region"},
                "tooltip": [
                    {"field": "month", "type": "temporal", "title": "Month"},
                    {"field": "region", "type": "nominal", "title": "Region"},
                    {"field": "revenue", "type": "quantitative", "title": "Revenue", "format": ",.0f"},
                ],
            },
        }


def grouped_bar_spec(renderer: str) -> dict:
    if renderer == "vega-lite":
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "data": {"name": "data"},
            "width": "container",
            "height": "container",
            "mark": "bar",
            "encoding": {
                "x": {"field": "quarter", "type": "ordinal", "title": "Quarter"},
                "xOffset": {"field": "region"},
                "y": {"field": "orders", "type": "quantitative", "title": "Orders"},
                "color": {"field": "region", "type": "nominal", "title": "Region"},
                "tooltip": [
                    {"field": "quarter", "type": "ordinal"},
                    {"field": "region", "type": "nominal"},
                    {"field": "orders", "type": "quantitative", "format": ","},
                ],
            },
        }


def order_lines_spec(renderer: str) -> dict:
    if renderer == "vega-lite":
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "data": {"name": "data"},
            "width": "container",
            "height": "container",
            "mark": "bar",
            "encoding": {
                "x": {"field": "day", "type": "temporal", "title": "Day"},
                "y": {"field": "amount", "type": "quantitative", "title": "Amount"},
                "tooltip": [
                    {"field": "day", "type": "temporal"},
                    {"field": "amount", "type": "quantitative", "format": ",.0f"},
                ],
            },
        }


def renderer_title(renderer: str) -> str:
    return {"vega-lite": "Vega-Lite"}[renderer]


def write_bakeoff(data: list[dict]) -> None:
    charts = ROOT / "charts" / "bakeoff"
    dashboards = ROOT / "dashboards" / "bakeoff"
    quarters = quarterly(data)
    lines = order_lines()

    write_json(charts / "_folder.json", {"schema_version": 1, "title": "Bake-off", "description": "The same four charts written for each renderer.", "order": 20})
    write_json(dashboards / "_folder.json", {"schema_version": 1, "title": "Bake-off", "description": "One dashboard per renderer. Pick a winner.", "order": 20})

    n = write_json(charts / "total-revenue" / "data.json", data)
    write_json(charts / "total-revenue" / "chart.json", chart_doc(
        "bakeoff/total-revenue", "Total revenue", "Sum of revenue over the selected period, with total orders.",
        "stat", {"value": "revenue", "agg": "sum", "format": "$,.0f", "compare": {"column": "orders", "agg": "sum"}},
        len(data), n, tags=("bakeoff", "sample"),
    ))

    for renderer in RENDERERS:
        folder = charts / renderer
        write_json(folder / "_folder.json", {"schema_version": 1, "title": renderer_title(renderer)})

        n = write_json(folder / "time-series" / "data.json", data)
        write_json(folder / "time-series" / "chart.json", chart_doc(
            f"bakeoff/{renderer}/time-series", f"Revenue by region, monthly ({renderer_title(renderer)})",
            "Monthly revenue per region. Filter with the Period and Region controls.",
            renderer, time_series_spec(renderer), len(data), n, tags=("bakeoff", "sample"),
        ))

        n = write_json(folder / "grouped-bar" / "data.json", quarters)
        write_json(folder / "grouped-bar" / "chart.json", chart_doc(
            f"bakeoff/{renderer}/grouped-bar", f"Orders by region, quarterly ({renderer_title(renderer)})",
            "Quarterly orders per region. Filter with the Region control.",
            renderer, grouped_bar_spec(renderer), len(quarters), n, columns=QUARTER_COLUMNS, tags=("bakeoff", "sample"),
        ))

        n = write_parquet(folder / "order-lines" / "data.parquet", lines)
        write_json(folder / "order-lines" / "chart.json", chart_doc(
            f"bakeoff/{renderer}/order-lines", f"Order amount per day ({renderer_title(renderer)})",
            f"{ORDER_LINES:,} synthetic order lines aggregated per day in the browser with DuckDB. Filter with the Days and Region controls.",
            renderer, order_lines_spec(renderer), lines.num_rows, n,
            columns=LINE_COLUMNS, fmt="parquet", lane="large", aggregate=LINE_AGGREGATE, tags=("bakeoff", "sample"),
        ))

        write_json(dashboards / f"{renderer}.json", {
            "schema_version": 1,
            "id": f"bakeoff/{renderer}",
            "title": f"Bake-off: {renderer_title(renderer)}",
            "description": f"The four bake-off charts rendered with {renderer_title(renderer)}. Synthetic data.",
            "tags": ["bakeoff", "sample"],
            "author": AUTHOR,
            "created_at": STAMP,
            "updated_at": STAMP,
            "controls": [
                {"id": "period", "type": "date-range", "label": "Period", "column": "month", "default": {"last": "12m"}},
                {"id": "days", "type": "date-range", "label": "Days", "column": "day", "default": None},
                {"id": "region", "type": "select", "label": "Region", "column": "region", "multi": True, "default": None},
            ],
            "layout": [
                {"chart": f"bakeoff/{renderer}/time-series", "w": 8, "h": 4},
                {"chart": "bakeoff/total-revenue", "w": 4, "h": 2},
                {"chart": f"bakeoff/{renderer}/grouped-bar", "w": 6, "h": 4},
                {"chart": f"bakeoff/{renderer}/order-lines", "w": 6, "h": 4},
                {"markdown": f"Rendered with **{renderer_title(renderer)}**. Same data and controls on every bake-off dashboard.", "w": 12, "h": 1},
            ],
        })


def write_examples(data: list[dict]) -> None:
    """Publish every chart form from the publish-viz skill, on the monthly dataset, plus a gallery."""
    charts = ROOT / "charts" / "examples"
    dashboards = ROOT / "dashboards" / "examples"
    write_json(charts / "_folder.json", {"schema_version": 1, "title": "Examples", "description": "The chart forms taught by the publish-viz skill.", "order": 30})
    write_json(dashboards / "_folder.json", {"schema_version": 1, "title": "Examples", "description": "A gallery of every chart form the publish-viz skill teaches.", "order": 30})

    layout = []
    for path in sorted(SKILL_EXAMPLES.glob("*.json")):
        example = json.loads(path.read_text(encoding="utf-8"))
        chart_id = f"examples/{path.stem}"
        n = write_json(charts / path.stem / "data.json", data)
        write_json(charts / path.stem / "chart.json", chart_doc(
            chart_id, example["title"], example["description"], example["renderer"], example["spec"],
            len(data), n, tags=("examples", "sample"),
        ))
        layout.append({"chart": chart_id, "w": 6, "h": 3})

    write_json(dashboards / "gallery.json", {
        "schema_version": 1,
        "id": "examples/gallery",
        "title": "Chart form gallery",
        "description": "Every example from the publish-viz skill's Vega-Lite guide, on synthetic data.",
        "tags": ["examples", "sample"],
        "author": AUTHOR,
        "created_at": STAMP,
        "updated_at": STAMP,
        "controls": [
            {"id": "period", "type": "date-range", "label": "Period", "column": "month", "default": None},
            {"id": "region", "type": "select", "label": "Region", "column": "region", "multi": True, "default": None},
        ],
        "layout": layout,
    })


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
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
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

    write_bakeoff(data)
    write_examples(data)


if __name__ == "__main__":
    main()
