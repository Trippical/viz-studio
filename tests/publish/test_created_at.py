"""Republishing an id keeps the created_at of the first publish (finding A20)."""
import json
from datetime import date, datetime, timezone

import pyarrow as pa

from viz.publish.publish import publish_chart, publish_dashboard
from viz.publish.staging import write_staged_chart

FIRST = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
SECOND = datetime(2026, 9, 29, 9, 30, 0, tzinfo=timezone.utc)
KEY = "viz/charts/sales/kept/chart.json"
BOARD_KEY = "viz/dashboards/sales/kept-board.json"


def _stage(staging_root, now):
    table = pa.table({"month": [date(2024, 1, 1), date(2024, 2, 1)], "revenue": [1.5, 2.5]})
    return write_staged_chart(table, "sales/kept", staging_root, author="tester@example.com", now=now)


def _board(staging_root, stamp):
    path = staging_root / "dashboards" / "sales" / "kept-board.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1, "id": "sales/kept-board", "title": "Kept", "author": "tester@example.com",
        "created_at": stamp, "updated_at": stamp,
        "layout": [{"chart": "sales/revenue-by-region", "w": 12, "h": 4}],
    }), encoding="utf-8")
    return path


def test_republish_keeps_the_first_created_at(settings, storage, staging_root):
    publish_chart(_stage(staging_root, FIRST).dir, settings, storage)
    staged = _stage(staging_root, SECOND)
    publish_chart(staged.dir, settings, storage, force=True)
    doc = json.loads(storage.get(KEY))
    assert doc["created_at"] == "2026-09-01T08:00:00Z"
    assert doc["updated_at"] == "2026-09-29T09:30:00Z"
    assert storage.get(KEY) == staged.chart_path.read_bytes(), "the bucket holds exactly the staged bytes"


def test_first_publish_leaves_the_staged_file_alone(settings, storage, staging_root):
    staged = _stage(staging_root, SECOND)
    before = staged.chart_path.read_bytes()
    publish_chart(staged.dir, settings, storage)
    assert staged.chart_path.read_bytes() == before
    assert json.loads(storage.get(KEY))["created_at"] == "2026-09-29T09:30:00Z"


def test_republish_ignores_a_malformed_created_at(settings, storage, staging_root):
    publish_chart(_stage(staging_root, FIRST).dir, settings, storage)
    doc = json.loads(storage.get(KEY))
    doc["created_at"] = "<img src=x onerror=alert(1)>"
    storage.put(KEY, json.dumps(doc).encode("utf-8"), "application/json")
    publish_chart(_stage(staging_root, SECOND).dir, settings, storage, force=True)
    assert json.loads(storage.get(KEY))["created_at"] == "2026-09-29T09:30:00Z"


def test_dashboard_republish_keeps_the_first_created_at(settings, storage, staging_root):
    publish_dashboard(_board(staging_root, "2026-09-01T08:00:00Z"), settings, storage)
    path = _board(staging_root, "2026-09-29T09:30:00Z")
    publish_dashboard(path, settings, storage, force=True)
    doc = json.loads(storage.get(BOARD_KEY))
    assert doc["created_at"] == "2026-09-01T08:00:00Z"
    assert doc["updated_at"] == "2026-09-29T09:30:00Z"
    assert storage.get(BOARD_KEY) == path.read_bytes()
