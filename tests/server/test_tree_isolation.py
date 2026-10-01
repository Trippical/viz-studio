"""A1: one hostile or unreadable object in the bucket must not take down /api/tree."""
import json

import pytest

from viz import schemas
from viz.publish.validate import read_document
from viz.server.tree import build_tree
from viz.storage import get_storage


@pytest.fixture
def storage(settings):
    return get_storage(settings)


def _find_folder(node, name):
    return next(f for f in node["folders"] if f["name"] == name)


def _item(folder, item_id):
    return next(i for i in folder["items"] if i["id"] == item_id)


def _nested_arrays(depth: int) -> str:
    return "[" * depth + "]" * depth


def _chart_with_deep_spec(storage, depth: int) -> bytes:
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc["id"] = "sales/deep"
    text = json.dumps(doc)
    return text.replace('"spec": {', f'"spec": {{"x": {_nested_arrays(depth)}, ', 1).encode("utf-8")


def test_nesting_depth_check():
    assert schemas.nesting_depth_exceeds({"a": 1}, limit=1) is False
    assert schemas.nesting_depth_exceeds({"a": [1]}, limit=1) is True
    assert schemas.nesting_depth_exceeds(json.loads(_nested_arrays(64)), limit=64) is False
    assert schemas.nesting_depth_exceeds(json.loads(_nested_arrays(65)), limit=64) is True
    assert schemas.nesting_depth_exceeds(5) is False


def test_deep_document_is_a_schema_error_not_a_crash():
    doc = {"schema_version": 1, "spec": json.loads(_nested_arrays(300))}
    for validate in (schemas.validate_chart, schemas.validate_dashboard, schemas.validate_folder):
        with pytest.raises(schemas.SchemaError) as excinfo:
            validate(doc)
        assert excinfo.value.errors == [f"$: nesting deeper than {schemas.MAX_NESTING_DEPTH} levels"]


def test_every_sample_chart_is_under_the_depth_cap(storage, settings):
    for info in storage.list("viz/charts/"):
        if info.key.endswith("/chart.json"):
            assert not schemas.nesting_depth_exceeds(json.loads(storage.get(info.key))), info.key


@pytest.mark.parametrize("depth", [300, 100_000])
def test_deeply_nested_chart_becomes_an_error_node(storage, settings, depth):
    storage.put("viz/charts/sales/deep/chart.json", _chart_with_deep_spec(storage, depth), "application/json")
    tree = build_tree(storage, settings)
    sales = _find_folder(tree["charts"], "sales")
    node = _item(sales, "sales/deep")
    assert set(node) == {"type", "id", "error"}
    assert "nest" in node["error"]
    assert _item(sales, "sales/total-revenue")["title"] == "Total revenue"


def test_deeply_nested_chart_is_422_on_the_chart_route(client, storage):
    storage.put("viz/charts/sales/deep/chart.json", _chart_with_deep_spec(storage, 100_000), "application/json")
    assert client.get("/api/tree").status_code == 200
    r = client.get("/api/charts/sales/deep")
    assert r.status_code == 422
    assert "nested too deeply" in r.json()["detail"]["errors"][0]


def test_storage_error_on_one_chart_becomes_an_error_node(storage, settings, monkeypatch):
    real_get = storage.get

    def denied_get(key):
        if key.endswith("sales/total-revenue/chart.json"):
            raise PermissionError("AccessDenied: foreign KMS key")
        return real_get(key)

    monkeypatch.setattr(storage, "get", denied_get)
    tree = build_tree(storage, settings)
    sales = _find_folder(tree["charts"], "sales")
    assert _item(sales, "sales/total-revenue")["error"] == "could not load (PermissionError)"
    assert _item(sales, "sales/revenue-by-region")["title"] == "Revenue by region, monthly"


def test_storage_error_on_a_dashboard_and_a_folder_becomes_an_error(storage, settings, monkeypatch):
    real_get = storage.get

    def denied_get(key):
        if key.endswith("dashboards/sales/overview.json") or key.endswith("charts/sales/_folder.json"):
            raise RuntimeError("boom")
        return real_get(key)

    monkeypatch.setattr(storage, "get", denied_get)
    tree = build_tree(storage, settings)
    assert _item(_find_folder(tree["dashboards"], "sales"), "sales/overview")["error"] == "could not load (RuntimeError)"
    assert _find_folder(tree["charts"], "sales")["error"] == "could not load (RuntimeError)"


def test_tree_route_survives_a_storage_error(client, monkeypatch):
    app_storage = client.app.state.storage
    real_get = app_storage.get

    def denied_get(key):
        if key.endswith("sales/total-revenue/chart.json"):
            raise RuntimeError("AccessDenied")
        return real_get(key)

    monkeypatch.setattr(app_storage, "get", denied_get)
    r = client.get("/api/tree")
    assert r.status_code == 200


def test_cli_read_document_reports_deep_json(tmp_path):
    path = tmp_path / "chart.json"
    path.write_text(_nested_arrays(100_000), encoding="utf-8")
    doc, errors = read_document(path)
    assert doc is None
    assert errors == ["chart.json: invalid JSON (nested too deeply)"]
