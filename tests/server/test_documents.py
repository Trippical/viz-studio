import json

import pytest

from viz.schemas import SchemaError
from viz.server import documents
from viz.storage import NotFound, get_storage


@pytest.fixture
def storage(settings):
    return get_storage(settings)


def test_load_chart(storage, settings):
    doc = documents.load_chart(storage, settings, "sales/revenue-by-region")
    assert doc["id"] == "sales/revenue-by-region"
    assert doc["renderer"] == "vega-lite"


def test_load_dashboard(storage, settings):
    doc = documents.load_dashboard(storage, settings, "sales/overview")
    assert doc["layout"][0]["chart"] == "sales/revenue-by-region"


def test_load_folder_present_and_absent(storage, settings):
    assert documents.load_folder(storage, settings, "charts", "sales")["title"] == "Sales"
    assert documents.load_folder(storage, settings, "charts", "") is None


def test_missing_chart(storage, settings):
    with pytest.raises(NotFound):
        documents.load_chart(storage, settings, "sales/nope")


def test_invalid_json_is_schema_error(storage, settings):
    storage.put("viz/charts/broken/chart.json", b"{not json", "application/json")
    with pytest.raises(SchemaError) as excinfo:
        documents.load_chart(storage, settings, "broken")
    assert "invalid JSON" in str(excinfo.value)


def test_id_mismatch_is_schema_error(storage, settings):
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    storage.put("viz/charts/sales/copy/chart.json", json.dumps(doc).encode(), "application/json")
    with pytest.raises(SchemaError) as excinfo:
        documents.load_chart(storage, settings, "sales/copy")
    assert "expected 'sales/copy'" in str(excinfo.value)


def test_too_large_document(storage, settings):
    big = json.dumps({"schema_version": 1, "pad": "x" * (settings.max_document_bytes + 10)}).encode()
    storage.put("viz/charts/big/chart.json", big, "application/json")
    with pytest.raises(documents.DocumentTooLarge):
        documents.load_chart(storage, settings, "big")


def test_public_chart_strips_sql_by_default():
    doc = {"id": "a", "source": {"kind": "databricks-sql", "sql": "SELECT 1", "warehouse_id": "w", "schedule": "0 6 * * *"}}
    out = documents.public_chart(doc)
    assert out["source"] == {"kind": "databricks-sql", "schedule": "0 6 * * *", "show_sql": False}
    assert "sql" in doc["source"], "input must not be mutated"


def test_public_chart_keeps_sql_when_show_sql():
    doc = {"id": "a", "source": {"kind": "databricks-sql", "sql": "SELECT 1", "warehouse_id": "w", "show_sql": True}}
    out = documents.public_chart(doc)
    assert out["source"]["sql"] == "SELECT 1"
    assert out["source"]["warehouse_id"] == "w"


def test_public_chart_without_source_is_unchanged():
    doc = {"id": "a", "title": "t"}
    assert documents.public_chart(doc) == doc
