import json

import pytest
from fastapi.testclient import TestClient

from viz.publish.cli import main
from viz.publish.move import MoveError, MovePlan, apply_move, describe, plan_move
from viz.server.app import create_app
from viz.storage import NotFound


def test_plan_chart_move(settings, storage):
    plan = plan_move("sales/revenue-by-region", "sales/emea/revenue", settings, storage)
    assert isinstance(plan, MovePlan)
    assert plan.kind == "chart"
    assert plan.keys == [
        ("viz/charts/sales/revenue-by-region/data.json", "viz/charts/sales/emea/revenue/data.json"),
        ("viz/charts/sales/revenue-by-region/chart.json", "viz/charts/sales/emea/revenue/chart.json"),
    ]
    assert plan.affected_dashboards == ["sales/overview"]
    text = describe(plan)
    assert "move chart 'sales/revenue-by-region' -> 'sales/emea/revenue'" in text
    assert "sales/overview" in text


def test_apply_chart_move_rewrites_dashboards(settings, storage):
    before = json.loads(storage.get("viz/dashboards/sales/overview.json"))
    plan = plan_move("sales/revenue-by-region", "sales/emea/revenue", settings, storage)
    apply_move(plan, settings, storage)

    doc = json.loads(storage.get("viz/charts/sales/emea/revenue/chart.json"))
    assert doc["id"] == "sales/emea/revenue"
    assert doc["updated_at"] != before["updated_at"]
    storage.head("viz/charts/sales/emea/revenue/data.json")
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/revenue-by-region/chart.json")
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/revenue-by-region/data.json")

    after = json.loads(storage.get("viz/dashboards/sales/overview.json"))
    assert [t.get("chart") for t in after["layout"]] == ["sales/emea/revenue", "sales/total-revenue", None]
    assert after["updated_at"] != before["updated_at"]

    client = TestClient(create_app(settings))
    assert client.get("/api/charts/sales/revenue-by-region").status_code == 404
    assert client.get("/api/charts/sales/emea/revenue").status_code == 200
    assert client.get("/api/data/sales/emea/revenue").status_code == 200
    assert client.get("/api/dashboards/sales/overview").json()["layout"][0]["chart"] == "sales/emea/revenue"


def test_plan_and_apply_dashboard_move(settings, storage):
    plan = plan_move("sales/overview", "sales/main", settings, storage)
    assert plan.kind == "dashboard"
    assert plan.keys == [("viz/dashboards/sales/overview.json", "viz/dashboards/sales/main.json")]
    assert plan.affected_dashboards == []
    apply_move(plan, settings, storage)
    assert json.loads(storage.get("viz/dashboards/sales/main.json"))["id"] == "sales/main"
    with pytest.raises(NotFound):
        storage.head("viz/dashboards/sales/overview.json")


def test_plan_move_refusals(settings, storage):
    with pytest.raises(MoveError, match="same"):
        plan_move("sales/overview", "sales/overview", settings, storage)
    with pytest.raises(MoveError, match="no chart or dashboard with id 'sales/nope'"):
        plan_move("sales/nope", "sales/x", settings, storage)
    with pytest.raises(MoveError, match="already exists"):
        plan_move("sales/revenue-by-region", "sales/total-revenue", settings, storage)
    with pytest.raises(MoveError, match="conflicts"):
        plan_move("sales/revenue-by-region", "sales/total-revenue/sub", settings, storage)
    with pytest.raises(MoveError, match="dashboard 'sales/overview' already exists"):
        storage.put("viz/dashboards/sales/second.json", storage.get("viz/dashboards/sales/overview.json"), "application/json")
        plan_move("sales/second", "sales/overview", settings, storage)


def test_move_command_requires_yes(env, storage, capsys, monkeypatch):
    assert main(["move", "sales/revenue-by-region", "sales/emea/revenue"]) == 1
    captured = capsys.readouterr()
    assert "sales/overview" in captured.out
    assert "pass --yes to apply" in captured.err
    storage.head("viz/charts/sales/revenue-by-region/chart.json")

    monkeypatch.setenv("VIZ_YES", "1")
    assert main(["move", "sales/revenue-by-region", "sales/emea/revenue"]) == 1, "an environment variable must never stand in for --yes"
    capsys.readouterr()

    assert main(["move", "sales/revenue-by-region", "sales/emea/revenue", "--yes"]) == 0
    assert "moved: sales/revenue-by-region -> sales/emea/revenue" in capsys.readouterr().out
    storage.head("viz/charts/sales/emea/revenue/chart.json")

    assert main(["move", "sales/nope", "sales/x", "--yes"]) == 1
    assert "error: no chart or dashboard" in capsys.readouterr().err
    assert main(["move", "Bad", "sales/x", "--yes"]) == 1
    assert "error: invalid id" in capsys.readouterr().err


def test_move_refuses_a_non_object_chart_document(env, storage, capsys):
    storage.put("viz/charts/sales/revenue-by-region/chart.json", b"[1, 2]", "application/json")
    assert main(["move", "sales/revenue-by-region", "sales/emea/revenue", "--yes"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "not a JSON object" in err
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/emea/revenue/chart.json")


def test_move_reports_but_does_not_write_a_broken_referencing_dashboard(env, storage, capsys):
    doc = json.loads(storage.get("viz/dashboards/sales/overview.json"))
    del doc["title"]  # title is required by the dashboard schema
    storage.put("viz/dashboards/sales/overview.json", json.dumps(doc).encode("utf-8"), "application/json")

    assert main(["move", "sales/revenue-by-region", "sales/emea/revenue", "--yes"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "sales/overview" in err

    # the move was refused before any write: neither the chart nor the dashboard moved or changed
    storage.head("viz/charts/sales/revenue-by-region/chart.json")
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/emea/revenue/chart.json")
    assert json.loads(storage.get("viz/dashboards/sales/overview.json")) == doc
