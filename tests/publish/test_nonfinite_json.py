"""Adopter fixes A1 and A2 on the publisher side: every reader of a bucket or staged
document refuses NaN, Infinity and integers too long to parse, as a validation error."""
import json
from datetime import datetime, timezone

import pytest

from viz.publish.cli import main
from viz.publish.dashboards import DashboardError, pulled_dashboard
from viz.publish.move import _dashboards
from viz.publish.publish import _existing
from viz.publish.validate import read_document
from viz.storage import NotFound

NON_FINITE = "not valid JSON: NaN/Infinity is not allowed"


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
def test_read_document_refuses_non_finite_numbers(tmp_path, constant):
    path = tmp_path / "chart.json"
    path.write_text('{"schema_version": 1, "x": ' + constant + "}", encoding="utf-8")
    doc, errors = read_document(path)
    assert doc is None
    assert errors == [f"chart.json: {NON_FINITE}"]


def test_read_document_refuses_a_huge_integer(tmp_path):
    path = tmp_path / "dash.json"
    path.write_text('{"x": ' + "9" * 5000 + "}", encoding="utf-8")
    doc, errors = read_document(path)
    assert doc is None
    assert len(errors) == 1 and errors[0].startswith("dash.json: invalid JSON (")


def test_existing_treats_an_unparseable_published_document_as_empty(storage):
    key = "viz/dashboards/sales/overview.json"
    storage.put(key, b'{"x": ' + b"9" * 5000 + b"}", "application/json")
    doc, etag = _existing(storage, key)
    assert doc == {} and etag
    storage.put(key, b'{"x": NaN}', "application/json")
    doc, etag = _existing(storage, key)
    assert doc == {} and etag


def test_move_refuses_a_chart_with_nan(env, storage, capsys):
    key = "viz/charts/sales/revenue-by-region/chart.json"
    text = storage.get(key).decode("utf-8").replace('"schema_version": 1', '"schema_version": 1, "x": NaN', 1)
    storage.put(key, text.encode("utf-8"), "application/json")
    assert main(["move", "sales/revenue-by-region", "sales/emea/revenue", "--yes"]) == 1
    assert NON_FINITE in capsys.readouterr().err
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/emea/revenue/chart.json")


def test_move_skips_an_unparseable_dashboard_when_scanning_references(settings, storage):
    storage.put("viz/dashboards/sales/huge.json", b'{"x": ' + b"9" * 5000 + b"}", "application/json")
    storage.put("viz/dashboards/sales/nan.json", b'{"x": NaN}', "application/json")
    ids = [doc_id for doc_id, _ in _dashboards(storage, settings.root_prefix)]
    assert "sales/overview" in ids
    assert "sales/huge" not in ids and "sales/nan" not in ids


def test_pull_dashboard_refuses_nan(settings, storage):
    key = "viz/dashboards/sales/overview.json"
    doc = json.loads(storage.get(key))
    doc["controls"] = [{"id": "amount", "type": "number-range", "label": "Amount", "column": "revenue",
                        "default": {"min": 0, "max": 1}}]
    text = json.dumps(doc).replace('"min": 0', '"min": NaN', 1)
    storage.put(key, text.encode("utf-8"), "application/json")
    with pytest.raises(DashboardError) as excinfo:
        pulled_dashboard("sales/overview", settings, storage, "tester@example.com", datetime.now(timezone.utc))
    assert NON_FINITE in str(excinfo.value)
