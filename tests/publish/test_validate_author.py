"""viz validate confirms the Databricks login that viz query stamped as author."""
import json

import pyarrow as pa
import pytest

from viz.publish import query
from viz.publish.cli import main

SQL = "SELECT region, sum(revenue) AS revenue FROM sales.public.monthly GROUP BY region"


class FakeCursor:
    def __init__(self, calls):
        self.calls = calls
        self.last = None

    def execute(self, sql):
        self.calls.append(sql)
        self.last = sql

    def fetchone(self):
        return ("dbx@example.com",)

    def fetchall_arrow(self):
        return pa.table({"region": ["EMEA", "NA"], "revenue": [1.5, 2.5]})

    def close(self):
        pass


class FakeConnection:
    def __init__(self, calls):
        self.calls = calls

    def cursor(self):
        return FakeCursor(self.calls)

    def close(self):
        pass


@pytest.fixture
def dbx(monkeypatch):
    calls = []
    monkeypatch.setattr(query, "_connect", lambda **kwargs: FakeConnection(calls))
    monkeypatch.setenv("DATABRICKS_HOST", "https://dbc-123.cloud.databricks.com/")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")
    return calls


def _chart_dir(staging_root):
    return staging_root / "charts" / "sales" / "by-region"


def test_query_chart_validates_with_the_databricks_login(env, staging_root, dbx, capsys):
    # env sets VIZ_AUTHOR=tester@example.com, which differs from the Databricks login.
    assert main(["query", "--sql", SQL, "--id", "sales/by-region"]) == 0
    assert json.loads((_chart_dir(staging_root) / "chart.json").read_text(encoding="utf-8"))["author"] == "dbx@example.com"
    capsys.readouterr()
    assert main(["validate", str(_chart_dir(staging_root))]) == 0, capsys.readouterr().err


def test_hand_edited_author_still_fails(env, staging_root, dbx, capsys):
    assert main(["query", "--sql", SQL, "--id", "sales/by-region"]) == 0
    path = _chart_dir(staging_root) / "chart.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["author"] = "someone-else@example.com"
    path.write_text(json.dumps(doc), encoding="utf-8")
    capsys.readouterr()
    assert main(["validate", str(_chart_dir(staging_root))]) == 1
    assert "does not match the resolved identity 'dbx@example.com'" in capsys.readouterr().err


def test_without_databricks_variables_validation_falls_back_to_viz_author(env, staging_root, dbx, monkeypatch, capsys):
    assert main(["query", "--sql", SQL, "--id", "sales/by-region"]) == 0
    monkeypatch.delenv("DATABRICKS_HOST")
    monkeypatch.delenv("DATABRICKS_TOKEN")
    capsys.readouterr()
    assert main(["validate", str(_chart_dir(staging_root))]) == 1
    assert "does not match the resolved identity 'tester@example.com'" in capsys.readouterr().err


def test_unreachable_databricks_is_a_validation_error(env, staging_root, dbx, monkeypatch, capsys):
    assert main(["query", "--sql", SQL, "--id", "sales/by-region"]) == 0

    def refuse(**kwargs):
        raise ConnectionError("warehouse unreachable")

    monkeypatch.setattr(query, "_connect", refuse)
    capsys.readouterr()
    assert main(["validate", str(_chart_dir(staging_root))]) == 1
    err = capsys.readouterr().err
    assert "author: could not confirm the Databricks user:" in err
    assert "Traceback" not in err


def test_staged_file_chart_is_stamped_and_confirmed_with_the_databricks_login(env, staging_root, dbx, tmp_path):
    csv = tmp_path / "rows.csv"
    csv.write_text("region,revenue\nEMEA,1.5\n", encoding="utf-8")
    assert main(["stage", "--from", str(csv), "--id", "sales/from-file"]) == 0
    chart_dir = staging_root / "charts" / "sales" / "from-file"
    assert json.loads((chart_dir / "chart.json").read_text(encoding="utf-8"))["author"] == "dbx@example.com"
    assert main(["validate", str(chart_dir)]) == 0


def test_databricks_configured(monkeypatch):
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    assert query.databricks_configured() is False
    monkeypatch.setenv("DATABRICKS_HOST", "https://x.example.com")
    assert query.databricks_configured() is False
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    assert query.databricks_configured() is True


def test_query_with_the_warehouse_flag_validates_without_the_variable(env, staging_root, dbx, monkeypatch, capsys):
    # The warehouse recorded in source.warehouse_id counts as the third variable.
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID")
    assert main(["query", "--sql", SQL, "--warehouse", "wh1", "--id", "sales/by-region"]) == 0
    doc = json.loads((_chart_dir(staging_root) / "chart.json").read_text(encoding="utf-8"))
    assert doc["author"] == "dbx@example.com"
    assert doc["source"]["warehouse_id"] == "wh1"
    capsys.readouterr()
    assert main(["validate", str(_chart_dir(staging_root))]) == 0, capsys.readouterr().err


def test_databricks_login_available_needs_all_three(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://x.example.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)
    assert query.databricks_login_available() is False
    assert query.databricks_login_available("wh1") is True
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")
    assert query.databricks_login_available() is True
    monkeypatch.delenv("DATABRICKS_TOKEN")
    assert query.databricks_login_available() is False
