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
