"""Opt-in: runs a real query against a real warehouse. Never runs on pull requests."""
import json
import os

import pytest

from viz.publish.cli import main

REQUIRED = ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID")

pytestmark = pytest.mark.skipif(
    os.environ.get("VIZ_INTEGRATION") != "1" or not all(os.environ.get(v) for v in REQUIRED),
    reason="set VIZ_INTEGRATION=1 and DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_WAREHOUSE_ID to run",
)


def test_query_against_a_real_warehouse(env, staging_root):
    assert main(["query", "--sql", "SELECT 1 AS one, 'a' AS letter", "--id", "integration/one"]) == 0
    doc = json.loads((staging_root / "charts" / "integration" / "one" / "chart.json").read_text(encoding="utf-8"))
    assert doc["data"]["rows"] == 1
    assert doc["data"]["columns"] == [{"name": "one", "type": "integer"}, {"name": "letter", "type": "string"}]
    assert "@" in doc["author"]
