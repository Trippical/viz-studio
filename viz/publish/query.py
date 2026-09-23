"""viz query: run SQL on Databricks and hand the Arrow result to staging.
This is the only module in the whole package that reads DATABRICKS_* variables."""
import os
from pathlib import Path

import pyarrow as pa

from ..config import Settings
from .denylist import denied_references

INSTALL_HINT = 'databricks-sql-connector is not installed; run: pip install "viz-site[databricks]"'


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


def read_sql_argument(value: str) -> str:
    if value.startswith("@"):
        path = Path(value[1:])
        if not path.is_file():
            raise QueryError(f"sql file not found: {path}", code=2)
        return path.read_text(encoding="utf-8")
    return value


def run_query(sql: str, settings: Settings, warehouse_id: str | None = None) -> tuple[pa.Table, str]:
    refs = denied_references(sql, settings.query_deny)
    if refs:
        raise DeniedQuery(refs)
    warehouse = resolve_warehouse(warehouse_id)
    host = _env("DATABRICKS_HOST").removeprefix("https://").removeprefix("http://").rstrip("/")
    token = _env("DATABRICKS_TOKEN")
    connect = _get_connect()
    try:
        connection = connect(server_hostname=host, http_path=f"/sql/1.0/warehouses/{warehouse}", access_token=token)
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
