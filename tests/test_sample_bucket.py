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
        declared = {c["name"] for c in doc["data"]["columns"]}
        if doc["data"]["format"] == "json":
            rows = json.loads(data_path.read_text(encoding="utf-8"))
            assert len(rows) == doc["data"]["rows"]
            assert set(rows[0]) == declared
        else:
            import pyarrow.parquet as pq

            meta = pq.read_metadata(data_path)
            assert meta.num_rows == doc["data"]["rows"]
            assert set(pq.read_schema(data_path).names) == declared


def test_every_dashboard_validates_and_references_existing_charts():
    dashboards = [p for p in _docs("dashboards", "*.json") if p.name != "_folder.json"]
    assert len(dashboards) >= 1
    for path in dashboards:
        doc = schemas.validate_dashboard(json.loads(path.read_text(encoding="utf-8")))
        assert doc["author"] == "sample@example.com"
        for tile in doc["layout"]:
            if "chart" in tile:
                assert (ROOT / "charts" / tile["chart"] / "chart.json").is_file()


def test_every_folder_validates():
    folders = _docs("charts", "_folder.json") + _docs("dashboards", "_folder.json")
    assert len(folders) >= 2
    for path in folders:
        schemas.validate_folder(json.loads(path.read_text(encoding="utf-8")))


RENDERERS = ("vega-lite", "plotly", "echarts")


def test_bakeoff_samples_exist_for_every_renderer():
    for renderer in RENDERERS:
        for chart in ("time-series", "grouped-bar", "order-lines"):
            path = ROOT / "charts" / "bakeoff" / renderer / chart / "chart.json"
            assert path.is_file(), path
            doc = json.loads(path.read_text(encoding="utf-8"))
            assert doc["renderer"] == renderer
            if chart == "order-lines":
                assert doc["data"]["lane"] == "large" and doc["data"]["format"] == "parquet"
                assert doc["aggregate"].startswith("SELECT day, sum(amount) AS amount")
            else:
                assert doc["data"]["lane"] == "small"
        dashboard = json.loads((ROOT / "dashboards" / "bakeoff" / f"{renderer}.json").read_text(encoding="utf-8"))
        chart_ids = [t["chart"] for t in dashboard["layout"] if "chart" in t]
        assert chart_ids == [
            f"bakeoff/{renderer}/time-series",
            "bakeoff/total-revenue",
            f"bakeoff/{renderer}/grouped-bar",
            f"bakeoff/{renderer}/order-lines",
        ]
        assert [c["id"] for c in dashboard["controls"]] == ["period", "days", "region"]
    stat = json.loads((ROOT / "charts" / "bakeoff" / "total-revenue" / "chart.json").read_text(encoding="utf-8"))
    assert stat["renderer"] == "stat"


def test_parquet_sample_is_under_the_large_lane_cap():
    for renderer in RENDERERS:
        path = ROOT / "charts" / "bakeoff" / renderer / "order-lines" / "data.parquet"
        assert path.stat().st_size < 209715200
