import json
from datetime import date, datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from viz import schemas
from viz.publish import staging
from viz.publish.staging import (
    LaneError, StagedChart, chart_dir, column_summary, dashboard_path, default_spec, title_from_id,
    write_staged_chart,
)

NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


def _table(n: int = 3) -> pa.Table:
    return pa.table({
        "month": pa.array([date(2024, m + 1, 1) for m in range(n)]),
        "region": pa.array(["EMEA"] * n),
        "revenue": pa.array([100.5 * (i + 1) for i in range(n)]),
    })


def test_paths(tmp_path):
    assert chart_dir(tmp_path, "sales/a-b") == tmp_path / "charts" / "sales" / "a-b"
    assert dashboard_path(tmp_path, "sales/board") == tmp_path / "dashboards" / "sales" / "board.json"
    with pytest.raises(ValueError):
        chart_dir(tmp_path, "Bad Id")


def test_title_from_id():
    assert title_from_id("sales/emea/revenue-by-region") == "Revenue by region"
    assert title_from_id("x") == "X"


def test_default_spec_binds_first_temporal_and_first_numeric():
    spec = default_spec([{"name": "month", "type": "date"}, {"name": "region", "type": "string"}, {"name": "revenue", "type": "number"}])
    assert spec["data"] == {"name": "data"}
    assert spec["mark"] == "bar"
    assert spec["encoding"]["x"] == {"field": "month", "type": "temporal"}
    assert spec["encoding"]["y"] == {"field": "revenue", "type": "quantitative"}


def test_default_spec_without_numeric_column_uses_first_column():
    spec = default_spec([{"name": "region", "type": "string"}, {"name": "flag", "type": "boolean"}])
    assert spec["encoding"]["x"] == {"field": "region", "type": "nominal"}
    assert spec["encoding"]["y"] == {"field": "region", "type": "quantitative"}


def test_write_small_lane(tmp_path):
    staged = write_staged_chart(_table(), "sales/test-chart", tmp_path, author="tester@example.com", now=NOW)
    assert isinstance(staged, StagedChart)
    assert staged.dir == tmp_path / "charts" / "sales" / "test-chart"
    assert staged.data_path.name == "data.json"
    assert staged.chart_path.name == "chart.json"
    doc = json.loads(staged.chart_path.read_text(encoding="utf-8"))
    assert doc == staged.doc
    schemas.validate_chart(doc)
    assert doc["id"] == "sales/test-chart"
    assert doc["title"] == "Test chart"
    assert doc["author"] == "tester@example.com"
    assert doc["created_at"] == doc["updated_at"] == "2026-09-22T10:00:00Z"
    assert doc["renderer"] == "vega-lite"
    assert doc["data"] == {
        "format": "json", "lane": "small", "rows": 3, "bytes": staged.data_path.stat().st_size,
        "columns": [{"name": "month", "type": "date"}, {"name": "region", "type": "string"}, {"name": "revenue", "type": "number"}],
    }
    assert doc["aggregate"] is None
    assert "source" not in doc
    rows = json.loads(staged.data_path.read_text(encoding="utf-8"))
    assert rows[0] == {"month": "2024-01-01", "region": "EMEA", "revenue": 100.5}


def test_write_with_source(tmp_path):
    source = {"kind": "databricks-sql", "sql": "SELECT 1", "warehouse_id": "sample"}
    staged = write_staged_chart(_table(), "sales/with-source", tmp_path, author="a@b", now=NOW, source=source)
    assert staged.doc["source"] == source
    schemas.validate_chart(staged.doc)


def test_large_lane_by_row_count(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 2)
    staged = write_staged_chart(_table(3), "sales/big", tmp_path, author="a@b", now=NOW)
    assert staged.data_path.name == "data.parquet"
    assert staged.doc["data"]["format"] == "parquet"
    assert staged.doc["data"]["lane"] == "large"
    assert staged.doc["data"]["rows"] == 3
    assert staged.doc["data"]["bytes"] == staged.data_path.stat().st_size
    assert staged.doc["aggregate"] == "SELECT * FROM data LIMIT 1000"
    assert pq.read_metadata(staged.data_path).num_rows == 3
    schemas.validate_chart(staged.doc)


def test_large_lane_by_byte_size(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_BYTES", 10)
    staged = write_staged_chart(_table(), "sales/big-bytes", tmp_path, author="a@b", now=NOW)
    assert staged.data_path.name == "data.parquet"


def test_parquet_over_cap_is_refused_and_cleaned_up(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    monkeypatch.setattr(staging, "LARGE_MAX_BYTES", 10)
    with pytest.raises(LaneError, match="209715200|10 bytes"):
        write_staged_chart(_table(), "sales/too-big", tmp_path, author="a@b", now=NOW)
    assert not (tmp_path / "charts" / "sales" / "too-big" / "data.parquet").exists()
    assert not (tmp_path / "charts" / "sales" / "too-big" / "chart.json").exists()


def test_restaging_removes_the_other_format(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    write_staged_chart(_table(), "sales/again", tmp_path, author="a@b", now=NOW)
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 100)
    staged = write_staged_chart(_table(), "sales/again", tmp_path, author="a@b", now=NOW)
    assert staged.data_path.name == "data.json"
    assert not (staged.dir / "data.parquet").exists()


def test_empty_table_is_refused(tmp_path):
    with pytest.raises(LaneError, match="no columns"):
        write_staged_chart(pa.table({}), "sales/empty", tmp_path, author="a@b", now=NOW)


def test_failed_restage_leaves_no_dangling_chart_json(tmp_path, monkeypatch):
    staged = write_staged_chart(_table(), "sales/restage", tmp_path, author="tester@example.com", now=NOW)
    assert staged.data_path.name == "data.json" and staged.chart_path.is_file()
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    monkeypatch.setattr(staging, "LARGE_MAX_BYTES", 10)
    with pytest.raises(LaneError):
        write_staged_chart(_table(), "sales/restage", tmp_path, author="tester@example.com", now=NOW)
    assert not (staged.dir / "chart.json").exists()
    assert not (staged.dir / "data.parquet").exists()


def test_column_summary(tmp_path):
    text = column_summary(_table())
    lines = text.splitlines()
    assert lines[0].split() == ["column", "type", "non-null", "samples"]
    assert lines[1].startswith("month")
    assert "date" in lines[1] and "3" in lines[1] and "2024-01-01" in lines[1]
    assert lines[3].startswith("revenue") and "100.5" in lines[3]


def test_default_spec_uses_the_vega_lite_v6_schema():
    spec = default_spec([{"name": "month", "type": "date"}, {"name": "revenue", "type": "number"}])
    assert spec["$schema"] == "https://vega.github.io/schema/vega-lite/v6.json"
