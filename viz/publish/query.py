"""viz query: run SQL on Databricks and hand the Arrow result to staging.
This is the only module in the whole package that reads DATABRICKS_* variables."""
import os
from pathlib import Path

import pyarrow as pa

from ..config import Settings
from .denylist import denied_references

INSTALL_HINT = (
    'databricks-sql-connector is not installed; from your viz-site checkout run: '
    'pip install -e ".[databricks]" (see docs/work-setup.md)'
)


class QueryError(Exception):
    def __init__(self, message: str, code: int = 2):
        self.code = code
        super().__init__(message)


class DeniedQuery(QueryError):
    def __init__(self, refs: list[str]):
        self.refs = list(refs)
        super().__init__("query refused by VIZ_QUERY_DENY: " + ", ".join(self.refs), code=2)


# None in production: the connector is imported lazily on first use. Tests set this to a fake.
_connect = None


def _get_connect():
    if _connect is not None:
        return _connect
    try:
        from databricks import sql as dbsql
    except ImportError as err:
        raise QueryError(INSTALL_HINT, code=2) from err
    return dbsql.connect


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise QueryError(f"{name} is not set", code=2)
    return value


def resolve_warehouse(warehouse_id: str | None) -> str:
    warehouse = warehouse_id or os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not warehouse:
        raise QueryError("no warehouse: pass --warehouse or set DATABRICKS_WAREHOUSE_ID", code=2)
    return warehouse


def read_sql_file(path: str) -> str:
    """The SQL in a file. `--sql-file` exists because PowerShell treats a leading @ as an
    operator, so `--sql @query.sql` does not work there (finding A16)."""
    sql_path = Path(path)
    if not sql_path.is_file():
        raise QueryError(f"sql file not found: {sql_path}", code=2)
    try:
        return sql_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as err:
        raise QueryError(f"sql file {sql_path} is not UTF-8 text; save it as UTF-8 ({err})", code=2) from err


def read_sql_argument(value: str) -> str:
    if value.startswith("@"):
        return read_sql_file(value[1:])
    return value


def databricks_configured() -> bool:
    """True when the variables `viz query` needs to reach Databricks are set."""
    return bool(os.environ.get("DATABRICKS_HOST")) and bool(os.environ.get("DATABRICKS_TOKEN"))


def databricks_login_available(warehouse_id: str | None = None) -> bool:
    """True when the CLI stamps the Databricks login as `author` (finding A19):
    DATABRICKS_HOST, DATABRICKS_TOKEN and a warehouse are all set. The warehouse is
    warehouse_id when the caller has one (the warehouse a `viz query` chart ran on),
    else DATABRICKS_WAREHOUSE_ID. Makes no connection."""
    return databricks_configured() and bool(warehouse_id or os.environ.get("DATABRICKS_WAREHOUSE_ID"))


def _connection_args(warehouse_id: str | None) -> dict:
    warehouse = resolve_warehouse(warehouse_id)
    host = _env("DATABRICKS_HOST").removeprefix("https://").removeprefix("http://").rstrip("/")
    token = _env("DATABRICKS_TOKEN")
    return {"server_hostname": host, "http_path": f"/sql/1.0/warehouses/{warehouse}", "access_token": token}


def current_user(warehouse_id: str | None = None) -> str:
    """The Databricks login the configured token belongs to. `viz validate` uses it to
    confirm the author `viz query` stamped (spec 12.4)."""
    args = _connection_args(warehouse_id)
    connect = _get_connect()
    try:
        connection = connect(**args)
        try:
            cursor = connection.cursor()
            try:
                cursor.execute("SELECT current_user()")
                return cursor.fetchone()[0]
            finally:
                cursor.close()
        finally:
            connection.close()
    except QueryError:
        raise
    except Exception as err:
        raise QueryError(f"could not read the Databricks user: {err}", code=2) from err


def run_query(sql: str, settings: Settings, warehouse_id: str | None = None) -> tuple[pa.Table, str]:
    refs = denied_references(sql, settings.query_deny)
    if refs:
        raise DeniedQuery(refs)
    args = _connection_args(warehouse_id)
    connect = _get_connect()
    try:
        connection = connect(**args)
        try:
            cursor = connection.cursor()
            try:
                cursor.execute("SELECT current_user()")
                user = cursor.fetchone()[0]
                cursor.execute(sql)
                table = cursor.fetchall_arrow()
            finally:
                cursor.close()
        finally:
            connection.close()
    except QueryError:
        raise
    except Exception as err:
        raise QueryError(f"query failed: {err}", code=2) from err
    return table, user
