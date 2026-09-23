"""stage -> validate -> publish -> read through the server API -> move -> dashboards follow."""
import json

from fastapi.testclient import TestClient

from viz.publish.cli import main
from viz.server.app import create_app


def _dashboard(dashboard_id, chart):
    return {
        "schema_version": 1, "id": dashboard_id, "title": "Daily orders", "author": "tester@example.com",
        "controls": [{"id": "period", "type": "date-range", "label": "Period", "column": "day", "default": None}],
        "layout": [{"chart": chart, "w": 12, "h": 4}, {"markdown": "Synthetic.", "w": 12, "h": 1}],
    }


def test_paved_path_end_to_end(env, settings, staging_root, tmp_path, capsys):
    csv = tmp_path / "orders.csv"
    csv.write_text("day,orders,revenue\n2024-01-01,3,10.5\n2024-01-02,4,20\n2024-01-03,5,30.25\n", encoding="utf-8")

    # stage
    assert main(["stage", "--from", str(csv), "--id", "ops/orders-by-day"]) == 0
    chart_dir = staging_root / "charts" / "ops" / "orders-by-day"
    assert (chart_dir / "chart.json").is_file() and (chart_dir / "data.json").is_file()

    # validate and publish
    assert main(["validate", str(chart_dir)]) == 0
    assert main(["publish", str(chart_dir)]) == 0
    capsys.readouterr()

    # read back through the unchanged server
    client = TestClient(create_app(settings))
    r = client.get("/api/charts/ops/orders-by-day")
    assert r.status_code == 200
    assert r.json()["data"]["rows"] == 3
    assert r.json()["data"]["columns"] == [
        {"name": "day", "type": "date"}, {"name": "orders", "type": "integer"}, {"name": "revenue", "type": "number"},
    ]
    r = client.get("/api/data/ops/orders-by-day")
    assert r.status_code == 200 and len(r.json()) == 3
    tree = client.get("/api/tree").json()
    assert "ops" in [f["name"] for f in tree["charts"]["folders"]]

    # a dashboard that references it
    board = staging_root / "dashboards" / "ops" / "daily.json"
    board.parent.mkdir(parents=True)
    board.write_text(json.dumps(_dashboard("ops/daily", "ops/orders-by-day")), encoding="utf-8")
    assert main(["validate", str(board)]) == 0
    assert main(["publish", str(board)]) == 0
    assert client.get("/api/dashboards/ops/daily").status_code == 200

    # move the chart; the dashboard follows; the old id is gone
    assert main(["move", "ops/orders-by-day", "ops/orders/by-day", "--yes"]) == 0
    assert client.get("/api/charts/ops/orders-by-day").status_code == 404
    assert client.get("/api/data/ops/orders-by-day").status_code == 404
    assert client.get("/api/charts/ops/orders/by-day").status_code == 200
    assert client.get("/api/data/ops/orders/by-day").status_code == 200
    assert client.get("/api/dashboards/ops/daily").json()["layout"][0]["chart"] == "ops/orders/by-day"

    # a second dashboard referencing the new id validates and publishes
    board2 = staging_root / "dashboards" / "ops" / "daily-2.json"
    board2.write_text(json.dumps(_dashboard("ops/daily-2", "ops/orders/by-day")), encoding="utf-8")
    assert main(["publish", str(board2)]) == 0
    assert client.get("/api/dashboards/ops/daily-2").status_code == 200

    # republishing the staged chart under its original id needs no --force now that it was moved away
    assert main(["publish", str(chart_dir)]) == 0
    assert client.get("/api/charts/ops/orders-by-day").status_code == 200
