import json
import sys
from datetime import date

import pyarrow as pa
import pytest

from viz.config import Settings
from viz.publish import query
from viz.publish.cli import main
from viz.publish.query import DeniedQuery, QueryError, read_sql_argument, resolve_warehouse, run_query

SQL = "SELECT month, region, revenue FROM sales.public.monthly"


class FakeCursor:
    def __init__(self, table, log):
        self.table = table
        self.log = log
        self.last = None

    def execute(self, sql):
        self.log.append(sql)
        self.last = sql

    def fetchone(self):
        assert "current_user" in self.last
        return ("dbx@example.com",)

    def fetchall_arrow(self):
        return self.table

    def close(self):
        self.log.append("cursor.close")


class FakeConnection:
    def __init__(self, table, log):
        self.table = table
        self.log = log

    def cursor(self):
        return FakeCursor(self.table, self.log)

    def close(self):
        self.log.append("connection.close")


@pytest.fixture
def fake(monkeypatch):
    """Installs a fake connector. `fake.kwargs` holds the connect() arguments, `fake.log` the calls."""
    class Fake:
        kwargs = None
        log = []
        # A DATE column comes back from Databricks as Arrow date32, not as a string.
        table = pa.table({"month": [date(2024, 1, 1)], "region": ["EMEA"], "revenue": [1.5]})

    def connect(**kwargs):
        Fake.kwargs = kwargs
        return FakeConnection(Fake.table, Fake.log)

    monkeypatch.setattr(query, "_connect", connect)
    return Fake


@pytest.fixture
def dbx_env(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://dbc-123.cloud.databricks.com/")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")


def test_settings_never_read_databricks_variables():
    assert not any(name.startswith("databricks") for name in Settings.model_fields)


def test_run_query_connects_and_returns_table_and_user(env, dbx_env, fake):
    table, user = run_query(SQL, Settings())
    assert user == "dbx@example.com"
    assert table.column_names == ["month", "region", "revenue"]
    assert fake.kwargs == {
        "server_hostname": "dbc-123.cloud.databricks.com",
        "http_path": "/sql/1.0/warehouses/wh1",
        "access_token": "dapi-test",
    }
    assert fake.log == ["SELECT current_user()", SQL, "cursor.close", "connection.close"]


def test_warehouse_flag_overrides_env(env, dbx_env, fake):
    run_query(SQL, Settings(), warehouse_id="wh2")
    assert fake.kwargs["http_path"] == "/sql/1.0/warehouses/wh2"
    assert resolve_warehouse(None) == "wh1"
    assert resolve_warehouse("wh9") == "wh9"


def test_missing_env_is_a_usage_error(env, fake, monkeypatch):
    for name in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(QueryError, match="DATABRICKS_WAREHOUSE_ID") as exc:
        run_query(SQL, Settings())
    assert exc.value.code == 2
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")
    with pytest.raises(QueryError, match="DATABRICKS_HOST is not set"):
        run_query(SQL, Settings())


def test_deny_list_refuses_before_connecting(env, dbx_env, fake, monkeypatch):
    monkeypatch.setenv("VIZ_QUERY_DENY", "sales.public")
    with pytest.raises(DeniedQuery) as exc:
        run_query(SQL, Settings())
    assert exc.value.refs == ["sales.public.monthly"]
    assert exc.value.code == 2
    assert fake.kwargs is None


def test_missing_connector_gives_install_hint(env, dbx_env, monkeypatch):
    monkeypatch.setattr(query, "_connect", None)
    monkeypatch.setitem(sys.modules, "databricks", None)
    monkeypatch.setitem(sys.modules, "databricks.sql", None)
    with pytest.raises(QueryError, match='pip install "viz-site\\[databricks\\]"'):
        run_query(SQL, Settings())


def test_read_sql_argument(tmp_path):
    assert read_sql_argument("SELECT 1") == "SELECT 1"
    path = tmp_path / "q.sql"
    path.write_text("SELECT 2\n", encoding="utf-8")
    assert read_sql_argument(f"@{path}") == "SELECT 2\n"
    with pytest.raises(QueryError, match="sql file not found"):
        read_sql_argument(f"@{tmp_path / 'missing.sql'}")


def test_query_command_stages_with_source_and_databricks_author(env, dbx_env, fake, staging_root, capsys):
    assert main(["query", "--sql", SQL, "--id", "sales/from-query"]) == 0
    out = capsys.readouterr().out
    assert "staged: " in out
    doc = json.loads((staging_root / "charts" / "sales" / "from-query" / "chart.json").read_text(encoding="utf-8"))
    assert doc["author"] == "dbx@example.com"
    assert doc["source"] == {"kind": "databricks-sql", "sql": SQL, "warehouse_id": "wh1"}
    assert doc["data"]["columns"] == [
        {"name": "month", "type": "date"}, {"name": "region", "type": "string"}, {"name": "revenue", "type": "number"},
    ]

    assert main(["query", "--sql", SQL, "--id", "sales/from-query", "--warehouse", "wh2"]) == 0
    doc = json.loads((staging_root / "charts" / "sales" / "from-query" / "chart.json").read_text(encoding="utf-8"))
    assert doc["source"]["warehouse_id"] == "wh2"


def test_query_command_deny_list_exit_code(env, dbx_env, fake, monkeypatch, capsys):
    monkeypatch.setenv("VIZ_QUERY_DENY", "sales")
    assert main(["query", "--sql", SQL, "--id", "sales/denied"]) == 2
    assert capsys.readouterr().err == "error: query refused by VIZ_QUERY_DENY: sales.public.monthly\n"


def test_query_command_drops_pii(env, dbx_env, fake, staging_root, capsys):
    fake.table = pa.table({"month": [date(2024, 1, 1)], "customer_email": ["a@b.c"], "revenue": [1.5]})
    assert main(["query", "--sql", SQL, "--id", "sales/pii", "--drop-columns", "customer_email"]) == 0
    doc = json.loads((staging_root / "charts" / "sales" / "pii" / "chart.json").read_text(encoding="utf-8"))
    assert [c["name"] for c in doc["data"]["columns"]] == ["month", "revenue"]
