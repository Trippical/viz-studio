"""Adopter fixes A1 and A2: NaN, Infinity and huge integers in a bucket document.

Python's json accepts NaN and Infinity, but Starlette cannot encode them, so one such
document made /api/tree answer 500 for everyone. A 5000-digit integer makes json.loads
raise a plain ValueError. Both must become a validation error on that one document."""
import json

import pytest

from viz.schemas import SchemaError
from viz.server import documents
from viz.server.tree import build_tree
from viz.storage import get_storage

NON_FINITE = "not valid JSON: NaN/Infinity is not allowed"


@pytest.fixture
def storage(settings):
    return get_storage(settings)


def _find_folder(node, name):
    return next(f for f in node["folders"] if f["name"] == name)


def _item(folder, item_id):
    return next(i for i in folder["items"] if i["id"] == item_id)


def _dashboard_with_number_range_default(storage, default_text: str) -> bytes:
    doc = json.loads(storage.get("viz/dashboards/sales/overview.json"))
    doc["id"] = "sales/bad"
    doc["controls"] = [{"id": "amount", "type": "number-range", "label": "Amount", "column": "revenue",
                        "default": {"min": 0, "max": 1}}]
    text = json.dumps(doc)
    return text.replace('"min": 0', f'"min": {default_text}', 1).encode("utf-8")


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
def test_non_finite_number_in_a_dashboard_is_one_error_node(client, storage, settings, constant):
    storage.put("viz/dashboards/sales/bad.json", _dashboard_with_number_range_default(storage, constant),
                "application/json")
    tree = build_tree(storage, settings)
    node = _item(_find_folder(tree["dashboards"], "sales"), "sales/bad")
    assert set(node) == {"type", "id", "error"}
    assert NON_FINITE in node["error"]
    assert _item(_find_folder(tree["dashboards"], "sales"), "sales/overview")["title"] == "Sales overview"

    assert client.get("/api/tree").status_code == 200
    r = client.get("/api/dashboards/sales/bad")
    assert r.status_code == 422
    assert NON_FINITE in r.json()["detail"]["errors"][0]


def test_non_finite_number_in_a_chart_and_a_folder(client, storage, settings):
    chart = storage.get("viz/charts/sales/total-revenue/chart.json").decode("utf-8")
    chart = chart.replace('"schema_version": 1', '"schema_version": 1, "x": NaN', 1)
    chart = chart.replace('"id": "sales/total-revenue"', '"id": "sales/nan"', 1)
    storage.put("viz/charts/sales/nan/chart.json", chart.encode("utf-8"), "application/json")
    storage.put("viz/charts/sales/_folder.json", b'{"schema_version": 1, "title": "Sales", "order": -Infinity}',
                "application/json")

    assert client.get("/api/tree").status_code == 200
    tree = build_tree(storage, settings)
    sales = _find_folder(tree["charts"], "sales")
    assert NON_FINITE in sales["error"]
    assert NON_FINITE in _item(sales, "sales/nan")["error"]
    assert client.get("/api/charts/sales/nan").status_code == 422


def test_huge_integer_is_a_schema_error_not_a_crash(client, storage, settings):
    storage.put("viz/dashboards/sales/bad.json", _dashboard_with_number_range_default(storage, "9" * 5000),
                "application/json")
    with pytest.raises(SchemaError) as excinfo:
        documents.load_dashboard(storage, settings, "sales/bad")
    assert excinfo.value.errors[0].startswith("$: invalid JSON (")

    assert client.get("/api/tree").status_code == 200
    r = client.get("/api/dashboards/sales/bad")
    assert r.status_code == 422
    node = _item(_find_folder(build_tree(storage, settings)["dashboards"], "sales"), "sales/bad")
    assert set(node) == {"type", "id", "error"}
