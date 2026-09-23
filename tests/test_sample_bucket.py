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
        assert doc["author"] == "sample@example.com"
        for tile in doc["layout"]:
            if "chart" in tile:
                assert (ROOT / "charts" / tile["chart"] / "chart.json").is_file()


def test_every_folder_validates():
    folders = _docs("charts", "_folder.json") + _docs("dashboards", "_folder.json")
    assert len(folders) >= 2
    for path in folders:
        schemas.validate_folder(json.loads(path.read_text(encoding="utf-8")))
