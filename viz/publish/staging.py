"""The staging directory: a bucket with an empty root prefix, under ./.viz-staging by default.
A chart stages at charts/<id>/{chart.json,data.json|data.parquet}; a dashboard at dashboards/<id>.json."""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ..ids import validate_id
from .infer import infer_columns, rows_from_table

SMALL_MAX_ROWS = 100_000
SMALL_MAX_BYTES = 20_971_520
LARGE_MAX_BYTES = 209_715_200
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
VEGA_LITE_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"
LARGE_DEFAULT_AGGREGATE = "SELECT * FROM data LIMIT 1000"


class LaneError(ValueError):
    pass


@dataclass
class StagedChart:
    dir: Path
    chart_path: Path
    data_path: Path
    doc: dict


def chart_dir(staging_root: Path, chart_id: str) -> Path:
    validate_id(chart_id)
    return Path(staging_root) / "charts" / chart_id


def dashboard_path(staging_root: Path, dashboard_id: str) -> Path:
    validate_id(dashboard_id)
    return Path(staging_root) / "dashboards" / f"{dashboard_id}.json"


def title_from_id(chart_id: str) -> str:
    return chart_id.rsplit("/", 1)[-1].replace("-", " ").capitalize()


def default_spec(columns: list[dict]) -> dict:
    first = columns[0]
    x_type = "temporal" if first["type"] in ("date", "timestamp") else "nominal"
    numeric = [c for c in columns if c["type"] in ("number", "integer")]
    y_field = numeric[0]["name"] if numeric else first["name"]
    return {
        "$schema": VEGA_LITE_SCHEMA,
        "data": {"name": "data"},
        "mark": "bar",
        "encoding": {
            "x": {"field": first["name"], "type": x_type},
            "y": {"field": y_field, "type": "quantitative"},
        },
    }


def skeleton(chart_id, columns, fmt, lane, rows, nbytes, author, now, source=None) -> dict:
    stamp = now.strftime(TIMESTAMP_FORMAT)
    doc = {
        "schema_version": 1,
        "id": chart_id,
        "title": title_from_id(chart_id),
        "author": author,
        "created_at": stamp,
        "updated_at": stamp,
        "renderer": "vega-lite",
        "spec": default_spec(columns),
        "data": {"format": fmt, "lane": lane, "rows": rows, "bytes": nbytes, "columns": columns},
        "aggregate": None if lane == "small" else LARGE_DEFAULT_AGGREGATE,
    }
    if source is not None:
        doc["source"] = source
    return doc


def _write_bytes(path: Path, payload: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)


def write_staged_chart(table: pa.Table, chart_id: str, staging_root: Path, *, author: str, now: datetime,
                       source: dict | None = None) -> StagedChart:
    if table.num_columns == 0:
        raise LaneError("table has no columns")
    columns = infer_columns(table)
    directory = chart_dir(staging_root, chart_id)
    directory.mkdir(parents=True, exist_ok=True)
    for stale in ("data.json", "data.parquet"):
        (directory / stale).unlink(missing_ok=True)

    payload = json.dumps(rows_from_table(table), ensure_ascii=False).encode("utf-8")
    if len(table) <= SMALL_MAX_ROWS and len(payload) <= SMALL_MAX_BYTES:
        fmt, lane = "json", "small"
        data_path = directory / "data.json"
        _write_bytes(data_path, payload)
    else:
        fmt, lane = "parquet", "large"
        data_path = directory / "data.parquet"
        pq.write_table(table, data_path)
        if data_path.stat().st_size > LARGE_MAX_BYTES:
            size = data_path.stat().st_size
            data_path.unlink()
            raise LaneError(f"parquet file is {size} bytes, over the large-lane cap of {LARGE_MAX_BYTES} bytes")

    doc = skeleton(chart_id, columns, fmt, lane, len(table), data_path.stat().st_size, author, now, source)
    chart_path = directory / "chart.json"
    _write_bytes(chart_path, (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return StagedChart(dir=directory, chart_path=chart_path, data_path=data_path, doc=doc)


def column_summary(table: pa.Table) -> str:
    columns = infer_columns(table)
    rows = rows_from_table(table.slice(0, 3))
    lines = [f"{'column':<24} {'type':<10} {'non-null':>8}  samples"]
    for col in columns:
        non_null = len(table) - table.column(col["name"]).null_count
        samples = ", ".join(str(r[col["name"]]) for r in rows if r[col["name"]] is not None)
        lines.append(f"{col['name']:<24} {col['type']:<10} {non_null:>8}  {samples}")
    return "\n".join(lines)
