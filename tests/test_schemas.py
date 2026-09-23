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


def test_malformed_data_block_is_schema_error_not_crash():
    doc = copy.deepcopy(load("chart-vegalite.json"))
    doc["data"] = None
    with pytest.raises(schemas.SchemaError):
        schemas.validate_chart(doc)


def test_unhashable_renderer_is_schema_error_not_crash():
    doc = copy.deepcopy(load("chart-vegalite.json"))
    doc["renderer"] = ["vega-lite"]
    with pytest.raises(schemas.SchemaError):
        schemas.validate_chart(doc)
