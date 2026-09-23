import json
from datetime import date, datetime, timezone

import pyarrow as pa
import pytest
from fastapi.testclient import TestClient

from viz.publish import staging
from viz.publish.cli import main
from viz.publish.publish import PublishRefused, publish_chart, publish_dashboard
from viz.publish.staging import write_staged_chart
from viz.server.app import create_app
from viz.storage import NotFound
from viz.storage.local import LocalStorage

NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


class RecordingStorage(LocalStorage):
    def __init__(self, root):
        super().__init__(root)
        self.puts: list[str] = []

    def put(self, key, data, content_type):
        self.puts.append(key)
        super().put(key, data, content_type)


def _staged(staging_root, chart_id="sales/new-chart", author="tester@example.com"):
    table = pa.table({"month": [date(2024, 1, 1), date(2024, 2, 1)], "revenue": [1.5, 2.5]})
    return write_staged_chart(table, chart_id, staging_root, author=author, now=NOW)


def _dashboard_file(staging_root, chart="sales/new-chart", dashboard_id="sales/board"):
    path = staging_root / "dashboards" / f"{dashboard_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1, "id": dashboard_id, "title": "Board", "author": "tester@example.com",
        "layout": [{"chart": chart, "w": 12, "h": 4}],
    }), encoding="utf-8")
    return path


def test_publish_chart_puts_data_then_document(settings, bucket, staging_root, capsys):
    storage = RecordingStorage(bucket)
    staged = _staged(staging_root)
    assert publish_chart(staged.dir, settings, storage) == "sales/new-chart"
    assert storage.puts == ["viz/charts/sales/new-chart/data.json", "viz/charts/sales/new-chart/chart.json"]
    assert json.loads(storage.get("viz/charts/sales/new-chart/chart.json")) == staged.doc
    assert storage.get("viz/charts/sales/new-chart/data.json") == staged.data_path.read_bytes()
    assert capsys.readouterr().out.strip() == "published: sales/new-chart"

    r = TestClient(create_app(settings)).get("/api/charts/sales/new-chart")
    assert r.status_code == 200 and r.json()["title"] == "New chart"


def test_publish_refuses_invalid(settings, storage, staging_root):
    staged = _staged(staging_root, author="someone@else")
    with pytest.raises(PublishRefused) as exc:
        publish_chart(staged.dir, settings, storage)
    assert exc.value.errors == ["author 'someone@else' does not match the resolved identity 'tester@example.com'"]
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/new-chart/chart.json")


def test_publish_refuses_overwrite_without_force(settings, storage, staging_root, capsys):
    staged = _staged(staging_root)
    publish_chart(staged.dir, settings, storage)
    with pytest.raises(PublishRefused) as exc:
        publish_chart(staged.dir, settings, storage)
    assert exc.value.errors == ["id exists: author tester@example.com, updated_at 2026-09-22T10:00:00Z; pass --force to overwrite"]
    publish_chart(staged.dir, settings, storage, force=True)
    out = capsys.readouterr().out
    assert "overwriting: author tester@example.com, updated_at 2026-09-22T10:00:00Z" in out


def test_publish_removes_stale_data_of_the_other_format(settings, storage, staging_root, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    big = _staged(staging_root)
    publish_chart(big.dir, settings, storage, allow_row_level=True)
    storage.head("viz/charts/sales/new-chart/data.parquet")
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 100_000)
    small = _staged(staging_root)
    publish_chart(small.dir, settings, storage, force=True)
    storage.head("viz/charts/sales/new-chart/data.json")
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/new-chart/data.parquet")


def test_publish_dashboard(settings, storage, staging_root, capsys):
    publish_chart(_staged(staging_root).dir, settings, storage)
    path = _dashboard_file(staging_root)
    assert publish_dashboard(path, settings, storage) == "sales/board"
    assert json.loads(storage.get("viz/dashboards/sales/board.json"))["id"] == "sales/board"
    assert "published: sales/board" in capsys.readouterr().out
    with pytest.raises(PublishRefused, match="id exists"):
        publish_dashboard(path, settings, storage)

    missing = _dashboard_file(staging_root, chart="sales/missing", dashboard_id="sales/broken")
    with pytest.raises(PublishRefused) as exc:
        publish_dashboard(missing, settings, storage)
    assert exc.value.errors == ["layout/0/chart: chart 'sales/missing' is not published"]


def test_publish_command(env, staging_root, capsys, monkeypatch):
    staged = _staged(staging_root)
    assert main(["publish", str(staged.dir)]) == 0
    assert capsys.readouterr().out.strip() == "published: sales/new-chart"

    assert main(["publish", str(staged.dir)]) == 1
    assert capsys.readouterr().err.startswith("error: id exists: author tester@example.com")

    monkeypatch.setenv("VIZ_FORCE", "1")
    assert main(["publish", str(staged.dir)]) == 1, "an environment variable must never stand in for --force"

    assert main(["publish", str(staged.dir), "--force"]) == 0

    assert main(["publish", str(staging_root / "nowhere")]) == 2
    assert "error: path not found" in capsys.readouterr().err

    path = _dashboard_file(staging_root)
    assert main(["publish", str(path)]) == 0


def test_publish_command_large_lane_needs_flag(env, staging_root, capsys, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    staged = _staged(staging_root, chart_id="sales/large")
    assert main(["publish", str(staged.dir)]) == 1
    assert "pass --allow-row-level" in capsys.readouterr().err
    assert main(["publish", str(staged.dir), "--allow-row-level"]) == 0
