"""viz move --kind picks the chart or the dashboard when an id is both (finding A26)."""
import json

import pytest

from viz.publish.cli import main
from viz.publish.move import MoveError, plan_move
from viz.storage import NotFound

BOTH = "sales/revenue-by-region"  # a chart in the sample bucket


def _add_dashboard_with_the_chart_id(storage):
    doc = json.loads(storage.get("viz/dashboards/sales/overview.json"))
    doc["id"] = BOTH
    storage.put(f"viz/dashboards/{BOTH}.json", json.dumps(doc).encode("utf-8"), "application/json")


def test_an_id_that_is_both_needs_kind(settings, storage):
    _add_dashboard_with_the_chart_id(storage)
    with pytest.raises(MoveError, match="is both a chart and a dashboard; pass --kind chart or --kind dashboard"):
        plan_move(BOTH, "sales/renamed", settings, storage)


def test_kind_dashboard_plans_only_the_dashboard(settings, storage):
    _add_dashboard_with_the_chart_id(storage)
    plan = plan_move(BOTH, "sales/renamed", settings, storage, kind="dashboard")
    assert plan.kind == "dashboard"
    assert plan.keys == [(f"viz/dashboards/{BOTH}.json", "viz/dashboards/sales/renamed.json")]


def test_kind_chart_plans_only_the_chart(settings, storage):
    _add_dashboard_with_the_chart_id(storage)
    plan = plan_move(BOTH, "sales/renamed", settings, storage, kind="chart")
    assert plan.kind == "chart"
    assert all(old.startswith(f"viz/charts/{BOTH}/") for old, _new in plan.keys)


def test_kind_that_does_not_exist(settings, storage):
    with pytest.raises(MoveError, match="no dashboard with id 'sales/revenue-by-region'"):
        plan_move(BOTH, "sales/renamed", settings, storage, kind="dashboard")
    with pytest.raises(MoveError, match="no chart with id 'sales/overview'"):
        plan_move("sales/overview", "sales/renamed", settings, storage, kind="chart")


def test_move_command_kind_flag(env, storage, capsys):
    _add_dashboard_with_the_chart_id(storage)
    assert main(["move", BOTH, "sales/renamed", "--yes"]) == 1
    assert "--kind" in capsys.readouterr().err
    assert main(["move", BOTH, "sales/renamed", "--kind", "dashboard", "--yes"]) == 0
    storage.head("viz/dashboards/sales/renamed.json")
    storage.head(f"viz/charts/{BOTH}/chart.json")  # the chart did not move
    with pytest.raises(NotFound):
        storage.head(f"viz/dashboards/{BOTH}.json")
