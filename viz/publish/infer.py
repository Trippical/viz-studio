"""Column type inference from Arrow tables, and conversions between tables,
JSON-safe rows and files. Everything the publisher knows about types is here."""
import json
import math
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

COLUMN_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})?$")


class UnsupportedColumn(ValueError):
    pass


def contract_type(arrow_type: pa.DataType) -> str:
    t = arrow_type
    if pa.types.is_boolean(t):
        return "boolean"
    if pa.types.is_integer(t):
        return "integer"
    if pa.types.is_floating(t) or pa.types.is_decimal(t):
        return "number"
    if pa.types.is_date(t):
        return "date"
    if pa.types.is_timestamp(t):
        return "timestamp"
    if pa.types.is_string(t) or pa.types.is_large_string(t) or pa.types.is_null(t):
        return "string"
    raise UnsupportedColumn(f"unsupported column type {t}")


def infer_columns(table: pa.Table) -> list[dict]:
    out = []
    for field in table.schema:
        if not COLUMN_NAME.match(field.name):
            raise UnsupportedColumn(f"column name {field.name!r} must match {COLUMN_NAME.pattern}")
        try:
            ctype = contract_type(field.type)
        except UnsupportedColumn as err:
            raise UnsupportedColumn(f"column {field.name!r}: {err}") from err
        out.append({"name": field.name, "type": ctype})
    return out


def _json_value(value):
    if value is None:
        return None
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, datetime):  # before date: datetime is a subclass of date
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def rows_from_table(table: pa.Table) -> list[dict]:
    return [{k: _json_value(v) for k, v in row.items()} for row in table.to_pylist()]


def _parse_timestamp(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _promote_strings(table: pa.Table) -> pa.Table:
    """String columns whose every non-null value is an ISO date or timestamp become typed columns."""
    for i, field in enumerate(table.schema):
        if not (pa.types.is_string(field.type) or pa.types.is_large_string(field.type)):
            continue
        values = table.column(i).to_pylist()
        present = [v for v in values if v is not None]
        if not present:
            continue
        if all(_ISO_DATE.match(v) for v in present):
            new = pa.array([None if v is None else date.fromisoformat(v) for v in values], pa.date32())
        elif all(_ISO_TIMESTAMP.match(v) for v in present):
            new = pa.array([None if v is None else _parse_timestamp(v) for v in values], pa.timestamp("us", tz="UTC"))
        else:
            continue
        table = table.set_column(i, field.name, new)
    return table


def table_from_rows(rows: list[dict]) -> pa.Table:
    try:
        table = pa.Table.from_pylist(rows)
    except (OverflowError, pa.ArrowInvalid, pa.ArrowTypeError) as err:
        raise UnsupportedColumn(f"cannot infer column types from rows: {err}") from err
    return _promote_strings(table)


def table_from_file(path: Path) -> pa.Table:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _promote_strings(pacsv.read_csv(path))
    if suffix == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise UnsupportedColumn(f"{path.name}: JSON input must be an array of objects")
        return table_from_rows(rows)
    if suffix == ".parquet":
        return pq.read_table(path)
    raise UnsupportedColumn(f"unsupported input file type {suffix!r}; use .csv, .json or .parquet")
