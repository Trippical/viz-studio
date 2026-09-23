import json
from datetime import date, datetime, timezone

import pyarrow as pa
import pytest

from viz.publish import staging
from viz.publish.cli import main
from viz.publish.staging import write_staged_chart
from viz.publish.validate import (
    check_aggregate, conflicting_ids, validate_dashboard_file, validate_staged_chart,
)

NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


def _table() -> pa.Table:
    return pa.table({
        "month": pa.array([date(2024, 1, 1), date(2024, 2, 1)]),
        "region": pa.array(["EMEA", "NA"]),
        "revenue": pa.array([100.5, 200.25]),
    })


def _staged(staging_root, chart_id="sales/new-chart", author="tester@example.com"):
    return write_staged_chart(_table(), chart_id, staging_root, author=author, now=NOW)


def _rewrite(staged, doc):
    staged.chart_path.write_text(json.dumps(doc), encoding="utf-8")


def test_valid_staged_chart(settings, storage, staging_root):
    staged = _staged(staging_root)
    assert validate_staged_chart(staged.dir, settings, storage) == []


def test_missing_and_broken_chart_json(settings, storage, staging_root):
    assert validate_staged_chart(staging_root / "charts" / "nope", settings, storage) == [
        f"{staging_root / 'charts' / 'nope' / 'chart.json'}: not found"
    ]
    staged = _staged(staging_root)
    staged.chart_path.write_text("{not json", encoding="utf-8")
    errors = validate_staged_chart(staged.dir, settings, storage)
    assert len(errors) == 1 and errors[0].startswith("chart.json: invalid JSON")


def test_schema_failure_is_reported_per_error(settings, storage, staging_root):
    staged = _staged(staging_root)
    doc = dict(staged.doc)
    del doc["title"]
    _rewrite(staged, doc)
    errors = validate_staged_chart(staged.dir, settings, storage)
    assert errors == ["chart.json: $: 'title' is a required property"]


def test_data_file_checks(settings, storage, staging_root):
    staged = _staged(staging_root)
    doc = json.loads(json.dumps(staged.doc))
    doc["data"]["bytes"] += 1
    doc["data"]["rows"] = 5
    doc["data"]["columns"][2]["type"] = "string"
    _rewrite(staged, doc)
    errors = validate_staged_chart(staged.dir, settings, storage)
    assert any(e.startswith("data.bytes: declared") for e in errors)
    assert any(e.startswith("data.rows: declared 5") for e in errors)
    assert any(e.startswith("data.columns/2/type: declared 'string', file has 'number'") for e in errors)

    doc = json.loads(json.dumps(staged.doc))
    doc["data"]["columns"][1]["name"] = "area"
    _rewrite(staged, doc)
    errors = validate_staged_chart(staged.dir, settings, storage)
    assert any(e.startswith("data.columns: declared names") for e in errors)

    staged.data_path.unlink()
    assert validate_staged_chart(staged.dir, settings, storage) == ["data.json: not found"]


def test_integer_file_column_satisfies_declared_number(settings, storage, staging_root):
    staged = _staged(staging_root)
    rows = [{"month": "2024-01-01", "region": "EMEA", "revenue": 100}, {"month": "2024-02-01", "region": "NA", "revenue": 200}]
    payload = json.dumps(rows).encode("utf-8")
    staged.data_path.write_bytes(payload)
    doc = json.loads(json.dumps(staged.doc))
    doc["data"]["bytes"] = len(payload)
    _rewrite(staged, doc)
    assert validate_staged_chart(staged.dir, settings, storage) == []


def test_author_must_match_identity(settings, storage, staging_root):
    staged = _staged(staging_root, author="someone@else")
    assert validate_staged_chart(staged.dir, settings, storage) == [
        "author 'someone@else' does not match the resolved identity 'tester@example.com'"
    ]


def test_id_conflicts_with_existing_charts(settings, storage, staging_root):
    assert conflicting_ids("sales/revenue-by-region/child", ["sales/revenue-by-region", "sales/total-revenue"]) == ["sales/revenue-by-region"]
    assert conflicting_ids("sales", ["sales/revenue-by-region", "sales/total-revenue"]) == ["sales/revenue-by-region", "sales/total-revenue"]
    assert conflicting_ids("sales/other", ["sales/revenue-by-region"]) == []
    staged = _staged(staging_root, chart_id="sales/revenue-by-region/child")
    assert validate_staged_chart(staged.dir, settings, storage) == [
        "id: 'sales/revenue-by-region/child' conflicts with existing chart 'sales/revenue-by-region'"
    ]


def test_directory_must_match_id(settings, storage, staging_root):
    staged = _staged(staging_root, chart_id="sales/one")
    doc = dict(staged.doc)
    doc["id"] = "sales/two"
    _rewrite(staged, doc)
    errors = validate_staged_chart(staged.dir, settings, storage)
    assert "id: chart.json says 'sales/two' but the directory is 'sales/one'" in errors


def test_large_lane_needs_allow_row_level_and_runs_the_aggregate(settings, storage, staging_root, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    staged = _staged(staging_root, chart_id="sales/large")
    assert staged.data_path.name == "data.parquet"
    assert validate_staged_chart(staged.dir, settings, storage) == [
        "large lane publishes row-level data; pass --allow-row-level to confirm"
    ]
    assert validate_staged_chart(staged.dir, settings, storage, allow_row_level=True) == []

    doc = dict(staged.doc)
    doc["aggregate"] = "SELECT region, sum(revenue) AS total FROM data GROUP BY region"
    _rewrite(staged, doc)
    assert validate_staged_chart(staged.dir, settings, storage, allow_row_level=True) == []


@pytest.mark.parametrize("aggregate", [
    "DELETE FROM data",
    "SELECT 1; SELECT 2",
    "SELECT nope FROM data",
    "SELECT * FROM read_csv('C:/nowhere.csv')",
    "INSTALL httpfs; SELECT 1",
    "not sql at all",
])
def test_check_aggregate_rejects(staging_root, aggregate, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    staged = _staged(staging_root, chart_id="sales/large")
    errors = check_aggregate(aggregate, staged.data_path)
    assert len(errors) == 1 and errors[0].startswith("aggregate:")


def test_check_aggregate_accepts_a_select(staging_root, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    staged = _staged(staging_root, chart_id="sales/large")
    assert check_aggregate("SELECT month, sum(revenue) AS total FROM data GROUP BY month ORDER BY month", staged.data_path) == []


def _dashboard(dashboard_id="sales/board", chart="sales/revenue-by-region", author="tester@example.com"):
    return {
        "schema_version": 1, "id": dashboard_id, "title": "Board", "author": author,
        "layout": [{"chart": chart, "w": 12, "h": 4}],
    }


def _write_dashboard(staging_root, doc, name="sales/board"):
    path = staging_root / "dashboards" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_dashboard_valid(settings, storage, staging_root):
    path = _write_dashboard(staging_root, _dashboard())
    assert validate_dashboard_file(path, settings, storage) == []


def test_dashboard_errors(settings, storage, staging_root):
    path = _write_dashboard(staging_root, _dashboard(chart="sales/missing"))
    assert validate_dashboard_file(path, settings, storage) == ["layout/0/chart: chart 'sales/missing' is not published"]

    path = _write_dashboard(staging_root, _dashboard(author="x@y"))
    assert validate_dashboard_file(path, settings, storage) == [
        "author 'x@y' does not match the resolved identity 'tester@example.com'"
    ]

    path = _write_dashboard(staging_root, _dashboard(dashboard_id="sales/other"))
    assert "id: dashboard says 'sales/other' but the file is 'sales/board'" in validate_dashboard_file(path, settings, storage)

    path.write_text("[1, 2]", encoding="utf-8")
    errors = validate_dashboard_file(path, settings, storage)
    assert len(errors) == 1 and errors[0].startswith("dashboard: ")


def test_validate_command(env, staging_root, capsys):
    staged = _staged(staging_root)
    assert main(["validate", str(staged.dir)]) == 0
    assert capsys.readouterr().out.strip() == f"ok: {staged.dir}"

    doc = dict(staged.doc)
    del doc["title"]
    _rewrite(staged, doc)
    assert main(["validate", str(staged.dir)]) == 1
    assert capsys.readouterr().err == "error: chart.json: $: 'title' is a required property\n"

    path = _write_dashboard(staging_root, _dashboard())
    assert main(["validate", str(path)]) == 0

    assert main(["validate", str(staging_root / "nowhere")]) == 2
    assert "error: path not found" in capsys.readouterr().err
