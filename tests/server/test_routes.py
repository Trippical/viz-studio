import json

import pytest

from viz.storage import get_storage


@pytest.fixture
def storage(settings):
    return get_storage(settings)


def test_tree(client):
    r = client.get("/api/tree")
    assert r.status_code == 200
    body = r.json()
    assert body["charts"]["type"] == "folder"
    assert [f["name"] for f in body["dashboards"]["folders"]] == ["sales"]


def test_dashboard(client):
    r = client.get("/api/dashboards/sales/overview")
    assert r.status_code == 200
    assert r.json()["id"] == "sales/overview"


def test_chart_strips_sql_unless_show_sql(client, storage):
    r = client.get("/api/charts/sales/revenue-by-region")
    assert r.status_code == 200
    assert r.json()["source"]["sql"].startswith("SELECT")  # sample sets show_sql true

    doc = json.loads(storage.get("viz/charts/sales/revenue-by-region/chart.json"))
    doc["source"].pop("show_sql")
    storage.put("viz/charts/sales/revenue-by-region/chart.json", json.dumps(doc).encode(), "application/json")
    r = client.get("/api/charts/sales/revenue-by-region")
    assert r.status_code == 200
    assert r.json()["source"] == {"kind": "databricks-sql", "schedule": "0 6 * * *", "show_sql": False}


@pytest.mark.parametrize("path", ["/api/charts/Sales", "/api/charts/a//b", "/api/dashboards/sales/..%2Fx", "/api/charts/a%2F..%2Fb"])
def test_invalid_ids_are_400(client, path):
    r = client.get(path)
    assert r.status_code == 400


def test_missing_is_404(client):
    assert client.get("/api/charts/sales/nope").status_code == 404
    assert client.get("/api/dashboards/sales/nope").status_code == 404


def test_invalid_document_is_422_with_errors(client, storage):
    storage.put("viz/charts/sales/bad/chart.json", b'{"schema_version": 1}', "application/json")
    r = client.get("/api/charts/sales/bad")
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    assert any("required" in e for e in errors)


def test_too_large_is_413(client, storage, settings):
    big = json.dumps({"schema_version": 1, "pad": "x" * (settings.max_document_bytes + 10)}).encode()
    storage.put("viz/charts/sales/big/chart.json", big, "application/json")
    assert client.get("/api/charts/sales/big").status_code == 413


def test_id_mismatch_is_422(client, storage):
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    storage.put("viz/charts/sales/copy/chart.json", json.dumps(doc).encode(), "application/json")
    r = client.get("/api/charts/sales/copy")
    assert r.status_code == 422
    assert "expected 'sales/copy'" in r.json()["detail"]["errors"][0]


def test_tree_reflects_new_chart_after_ttl(client, storage, settings):
    r1 = client.get("/api/tree")
    assert all(i["id"] != "sales/new" for i in r1.json()["charts"]["folders"][0]["items"])
    client.app.state.tree.invalidate()
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc["id"] = "sales/new"
    storage.put("viz/charts/sales/new/chart.json", json.dumps(doc).encode(), "application/json")
    r2 = client.get("/api/tree")
    assert any(i["id"] == "sales/new" for i in r2.json()["charts"]["folders"][0]["items"])
