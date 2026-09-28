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


RENDERERS = ("vega-lite",)


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


SKILL_EXAMPLES = Path(__file__).resolve().parents[1] / "skills" / "publish-viz" / "examples"


def _examples():
    return sorted(SKILL_EXAMPLES.glob("*.json"))


def test_skill_examples_exist():
    assert len(_examples()) == 11


def test_every_skill_example_is_published_in_the_gallery():
    gallery = json.loads((ROOT / "dashboards" / "examples" / "gallery.json").read_text(encoding="utf-8"))
    assert [t["chart"] for t in gallery["layout"]] == [f"examples/{p.stem}" for p in _examples()]
    for path in _examples():
        example = json.loads(path.read_text(encoding="utf-8"))
        assert set(example) == {"title", "description", "renderer", "spec"}
        doc = json.loads((ROOT / "charts" / "examples" / path.stem / "chart.json").read_text(encoding="utf-8"))
        assert doc["title"] == example["title"]
        assert doc["renderer"] == example["renderer"]
        assert doc["spec"] == example["spec"]


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def test_date_axes_use_utc_time_units():
    for path in _examples():
        example = json.loads(path.read_text(encoding="utf-8"))
        for obj in _walk(example["spec"]):
            if obj.get("field") == "month":
                assert str(obj.get("timeUnit", "")).startswith("utc"), f"{path.name}: {obj}"


def test_vega_lite_examples_use_the_v6_schema():
    for path in _examples():
        example = json.loads(path.read_text(encoding="utf-8"))
        if example["renderer"] == "vega-lite":
            assert example["spec"]["$schema"] == "https://vega.github.io/schema/vega-lite/v6.json", path.name


def test_axis_and_legend_formats_name_a_type():
    # A d3-format with no type letter (for example ",") lets Vega's tick
    # formatter pick its own precision, which prints 4.5e+4 on an axis.
    for path in _examples():
        example = json.loads(path.read_text(encoding="utf-8"))
        for obj in _walk(example["spec"]):
            for key in ("axis", "legend"):
                fmt = obj.get(key, {}).get("format") if isinstance(obj.get(key), dict) else None
                if fmt is not None:
                    assert fmt[-1] in "efgrsp%dbcoxXn", f"{path.name}: {key} format {fmt!r} has no type letter"
