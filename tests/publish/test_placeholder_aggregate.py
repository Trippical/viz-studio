"""A large-lane chart cannot be published with the placeholder aggregate (finding A22)."""
import json
from datetime import date, datetime, timezone

import pyarrow as pa
import pytest

from viz.publish import staging
from viz.publish.cli import main
from viz.publish.staging import write_staged_chart
from viz.publish.validate import PLACEHOLDER_ERROR, is_placeholder_aggregate, validate_staged_chart

NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)
REAL = "SELECT month, sum(revenue) AS revenue FROM data GROUP BY month ORDER BY month"


def _large(staging_root, monkeypatch, chart_id="sales/large"):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    table = pa.table({"month": [date(2024, 1, 1), date(2024, 2, 1)], "revenue": [1.5, 2.5]})
    return write_staged_chart(table, chart_id, staging_root, author="tester@example.com", now=NOW)


def _set_aggregate(staged, aggregate):
    doc = json.loads(staged.chart_path.read_text(encoding="utf-8"))
    doc["aggregate"] = aggregate
    staged.chart_path.write_text(json.dumps(doc), encoding="utf-8")


@pytest.mark.parametrize("text", [
    "SELECT * FROM data LIMIT 1000",
    "select * from data limit 1000",
    "SELECT *  FROM data\nLIMIT 1000;",
    "  SELECT * FROM data LIMIT 1000  ",
])
def test_placeholder_variants(text):
    assert is_placeholder_aggregate(text)


def test_a_real_aggregate_is_not_the_placeholder():
    assert not is_placeholder_aggregate(REAL)
    assert not is_placeholder_aggregate("SELECT * FROM data LIMIT 100")


def test_validate_refuses_the_placeholder(settings, storage, staging_root, monkeypatch):
    staged = _large(staging_root, monkeypatch)
    assert validate_staged_chart(staged.dir, settings, storage, allow_row_level=True) == [PLACEHOLDER_ERROR]
    _set_aggregate(staged, REAL)
    assert validate_staged_chart(staged.dir, settings, storage, allow_row_level=True) == []


def test_publish_command_refuses_the_placeholder(env, staging_root, monkeypatch, capsys):
    staged = _large(staging_root, monkeypatch)
    assert main(["publish", str(staged.dir), "--allow-row-level"]) == 1
    assert "still the staging placeholder" in capsys.readouterr().err
