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
        self.conditions: list[dict] = []

    def put(self, key, data, content_type, *, if_match=None, if_none_match=False):
        self.puts.append(key)
        self.conditions.append({"if_match": if_match, "if_none_match": if_none_match})
        super().put(key, data, content_type, if_match=if_match, if_none_match=if_none_match)


class RacingStorage(LocalStorage):
    """Another publisher writes `target` just before our conditional PUT of it lands."""

    def __init__(self, root, target):
        super().__init__(root)
        self.target = target

    def put(self, key, data, content_type, *, if_match=None, if_none_match=False):
        if key == self.target and (if_match is not None or if_none_match):
            super().put(key, b'{"author": "rival@example.com"}', "application/json")
        super().put(key, data, content_type, if_match=if_match, if_none_match=if_none_match)


def _staged(staging_root, chart_id="sales/new-chart", author="tester@example.com"):
    table = pa.table({"month": [date(2024, 1, 1), date(2024, 2, 1)], "revenue": [1.5, 2.5]})
    return write_staged_chart(table, chart_id, staging_root, author=author, now=NOW)


def _staged_value(staging_root, revenue: float):
    table = pa.table({"month": [date(2024, 1, 1)], "revenue": [revenue]})
    return write_staged_chart(table, "sales/new-chart", staging_root, author="tester@example.com", now=NOW)


def _published_data_files(storage, chart_id="sales/new-chart"):
    prefix = f"viz/charts/{chart_id}/"
    names = [info.key[len(prefix):] for info in storage.list(prefix)]
    return sorted(name for name in names if name.startswith("data."))


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
    data_key = f"viz/charts/sales/new-chart/{staged.doc['data']['file']}"
    assert storage.puts == [data_key, "viz/charts/sales/new-chart/chart.json"]
    assert json.loads(storage.get("viz/charts/sales/new-chart/chart.json")) == staged.doc
    assert storage.get(data_key) == staged.data_path.read_bytes()
    assert capsys.readouterr().out.strip().startswith("published: sales/new-chart -> ")

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
    assert exc.value.errors == ["id exists: author tester@example.com, updated_at 2026-09-22T10:00:00Z; ask the user before passing --force to overwrite"]
    publish_chart(staged.dir, settings, storage, force=True)
    out = capsys.readouterr().out
    assert "overwriting: author tester@example.com, updated_at 2026-09-22T10:00:00Z" in out


def test_publish_removes_legacy_data_files(settings, storage, staging_root):
    storage.put("viz/charts/sales/new-chart/data.json", b"[]", "application/json")
    storage.put("viz/charts/sales/new-chart/data.parquet", b"PAR1", "application/octet-stream")
    staged = _staged(staging_root)
    publish_chart(staged.dir, settings, storage)
    storage.head(f"viz/charts/sales/new-chart/{staged.doc['data']['file']}")
    with pytest.raises(NotFound):
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
    assert capsys.readouterr().out.strip().startswith("published: sales/new-chart -> ")

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
    assert "ask the user before passing --allow-row-level" in capsys.readouterr().err
    assert main(["publish", str(staged.dir), "--allow-row-level"]) == 0


def test_chart_json_put_is_conditional(settings, bucket, staging_root):
    storage = RecordingStorage(bucket)
    staged = _staged(staging_root)
    publish_chart(staged.dir, settings, storage)
    assert storage.conditions[0] == {"if_match": None, "if_none_match": False}   # data file
    assert storage.conditions[1] == {"if_match": None, "if_none_match": True}    # new chart.json
    etag = storage.head("viz/charts/sales/new-chart/chart.json").etag
    publish_chart(staged.dir, settings, storage, force=True)
    assert storage.conditions[3] == {"if_match": etag, "if_none_match": False}   # overwrite


def test_new_chart_created_by_someone_else_meanwhile_is_refused(settings, bucket, staging_root):
    storage = RacingStorage(bucket, "viz/charts/sales/new-chart/chart.json")
    staged = _staged(staging_root)
    with pytest.raises(PublishRefused) as exc:
        publish_chart(staged.dir, settings, storage)
    assert exc.value.errors == ["sales/new-chart changed since you checked it; run the command again"]
    assert json.loads(storage.get("viz/charts/sales/new-chart/chart.json")) == {"author": "rival@example.com"}


def test_overwrite_of_a_chart_changed_meanwhile_is_refused(settings, bucket, staging_root):
    staged = _staged(staging_root)
    publish_chart(staged.dir, settings, LocalStorage(bucket))
    racing = RacingStorage(bucket, "viz/charts/sales/new-chart/chart.json")
    with pytest.raises(PublishRefused) as exc:
        publish_chart(staged.dir, settings, racing, force=True)
    assert exc.value.errors == ["sales/new-chart changed since you checked it; run the command again"]


def test_dashboard_changed_meanwhile_is_refused(settings, storage, bucket, staging_root):
    publish_chart(_staged(staging_root).dir, settings, storage)
    path = _dashboard_file(staging_root)
    racing = RacingStorage(bucket, "viz/dashboards/sales/board.json")
    with pytest.raises(PublishRefused) as exc:
        publish_dashboard(path, settings, racing)
    assert exc.value.errors == ["sales/board changed since you checked it; run the command again"]
    publish_dashboard(path, settings, LocalStorage(bucket), force=True)
    racing = RacingStorage(bucket, "viz/dashboards/sales/board.json")
    with pytest.raises(PublishRefused):
        publish_dashboard(path, settings, racing, force=True)


def test_publish_keeps_the_new_and_one_previous_data_file(settings, storage, staging_root):
    first = _staged_value(staging_root, 1.0)
    first_file = first.doc["data"]["file"]
    publish_chart(first.dir, settings, storage)
    assert _published_data_files(storage) == [first_file]

    second = _staged_value(staging_root, 2.0)
    second_file = second.doc["data"]["file"]
    publish_chart(second.dir, settings, storage, force=True)
    assert _published_data_files(storage) == sorted([first_file, second_file])

    third = _staged_value(staging_root, 3.0)
    third_file = third.doc["data"]["file"]
    publish_chart(third.dir, settings, storage, force=True)
    assert _published_data_files(storage) == sorted([second_file, third_file])


def test_republishing_the_same_bytes_keeps_one_data_file(settings, storage, staging_root):
    staged = _staged_value(staging_root, 1.0)
    publish_chart(staged.dir, settings, storage)
    publish_chart(staged.dir, settings, storage, force=True)
    assert _published_data_files(storage) == [staged.doc["data"]["file"]]


def test_a_reader_of_the_replaced_chart_json_can_still_fetch_its_data(settings, storage, staging_root):
    first = _staged_value(staging_root, 1.0)
    publish_chart(first.dir, settings, storage)
    old_doc = json.loads(storage.get("viz/charts/sales/new-chart/chart.json"))
    publish_chart(_staged_value(staging_root, 2.0).dir, settings, storage, force=True)
    assert json.loads(storage.get(f"viz/charts/sales/new-chart/{old_doc['data']['file']}")) == [
        {"month": "2024-01-01", "revenue": 1.0}
    ]
    r = TestClient(create_app(settings)).get("/api/data/sales/new-chart")
    assert r.json() == [{"month": "2024-01-01", "revenue": 2.0}]
