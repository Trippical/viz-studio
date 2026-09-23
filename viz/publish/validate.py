"""Everything `viz validate` checks beyond the JSON Schema. Every function returns
a list of error strings; an empty list means valid."""
import json
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from ..config import Settings
from ..ids import chart_key, is_ancestor
from ..schemas import SchemaError, validate_chart, validate_dashboard
from ..storage import NotFound, Storage
from .identity import check_author
from .infer import UnsupportedColumn, infer_columns, table_from_file
from .staging import LARGE_MAX_BYTES, SMALL_MAX_BYTES, SMALL_MAX_ROWS

DUCKDB_LOCKDOWN = (
    "SET autoinstall_known_extensions=false",
    "SET autoload_known_extensions=false",
    "SET enable_external_access=false",
    "SET memory_limit='512MB'",
    "SET lock_configuration=true",
)


def read_document(path: Path) -> tuple[dict | None, list[str]]:
    path = Path(path)
    if not path.is_file():
        return None, [f"{path}: not found"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        return None, [f"{path.name}: invalid JSON ({err})"]
    return doc, []


def existing_chart_ids(storage: Storage, root: str) -> list[str]:
    prefix = f"{root}charts/"
    suffix = "/chart.json"
    out = []
    for info in storage.list(prefix):
        if info.key.endswith(suffix):
            out.append(info.key[len(prefix):-len(suffix)])
    return out


def conflicting_ids(chart_id: str, existing: list[str]) -> list[str]:
    return sorted(e for e in existing if e != chart_id and (is_ancestor(chart_id, e) or is_ancestor(e, chart_id)))


def _id_from_path(path: Path, kind: str) -> str | None:
    """The id implied by a path under a `charts` or `dashboards` directory, or None."""
    parts = list(Path(path).parts)
    if kind not in parts:
        return None
    tail = parts[len(parts) - parts[::-1].index(kind):]
    if kind == "dashboards" and tail and tail[-1].endswith(".json"):
        tail[-1] = tail[-1][:-5]
    return "/".join(tail) if tail else None


def check_aggregate(aggregate: str, parquet_path: Path) -> list[str]:
    """Parse and run the large-lane aggregate in a native DuckDB with no file, network
    or extension access. The table is registered before the connection is locked."""
    con = duckdb.connect()
    try:
        con.register("data", pq.read_table(parquet_path))
        for statement in DUCKDB_LOCKDOWN:
            con.execute(statement)
        try:
            serialized = json.loads(con.execute("SELECT json_serialize_sql(?)", [aggregate]).fetchone()[0])
        except duckdb.Error as err:
            return [f"aggregate: {err}"]
        if serialized.get("error"):
            return [f"aggregate: {serialized.get('error_message', 'cannot parse')}"]
        statements = serialized.get("statements", [])
        if len(statements) != 1 or statements[0].get("node", {}).get("type") != "SELECT_NODE":
            return ["aggregate: must be a single SELECT statement"]
        try:
            con.execute(f"SELECT * FROM ({aggregate}) LIMIT 1").fetchall()
        except duckdb.Error as err:
            return [f"aggregate: {err}"]
    finally:
        con.close()
    return []


def _compare_columns(declared: list[dict], inferred: list[dict]) -> list[str]:
    declared_names = [c["name"] for c in declared]
    inferred_names = [c["name"] for c in inferred]
    if declared_names != inferred_names:
        return [f"data.columns: declared names {declared_names} differ from file names {inferred_names}"]
    errors = []
    for i, (d, f) in enumerate(zip(declared, inferred)):
        if d["type"] == f["type"]:
            continue
        if d["type"] == "number" and f["type"] == "integer":
            continue
        errors.append(f"data.columns/{i}/type: declared '{d['type']}', file has '{f['type']}'")
    return errors


def validate_staged_chart(chart_dir: Path, settings: Settings, storage: Storage, allow_row_level: bool = False) -> list[str]:
    chart_dir = Path(chart_dir)
    doc, errors = read_document(chart_dir / "chart.json")
    if doc is None:
        return errors
    try:
        validate_chart(doc)
    except SchemaError as err:
        return [f"chart.json: {e}" for e in err.errors]

    implied = _id_from_path(chart_dir, "charts")
    if implied is not None and implied != doc["id"]:
        errors.append(f"id: chart.json says '{doc['id']}' but the directory is '{implied}'")

    data = doc["data"]
    fmt, lane = data["format"], data["lane"]
    data_path = chart_dir / f"data.{fmt}"
    if not data_path.is_file():
        return errors + [f"data.{fmt}: not found"]
    size = data_path.stat().st_size
    if size != data["bytes"]:
        errors.append(f"data.bytes: declared {data['bytes']}, file is {size} bytes")

    if fmt == "json":
        try:
            table = table_from_file(data_path)
        except (UnsupportedColumn, ValueError) as err:
            return errors + [f"data.json: {err}"]
        rows = len(table)
    else:
        rows = pq.read_metadata(data_path).num_rows
        table = pq.read_table(data_path)
    if rows != data["rows"]:
        errors.append(f"data.rows: declared {data['rows']}, file has {rows}")
    try:
        errors += _compare_columns(data["columns"], infer_columns(table))
    except UnsupportedColumn as err:
        errors.append(f"data.{fmt}: {err}")

    if lane == "small" and (rows > SMALL_MAX_ROWS or size > SMALL_MAX_BYTES):
        errors.append(f"data: small lane allows at most {SMALL_MAX_ROWS} rows and {SMALL_MAX_BYTES} bytes")
    if lane == "large" and size > LARGE_MAX_BYTES:
        errors.append(f"data: large lane allows at most {LARGE_MAX_BYTES} bytes")

    errors += check_author(doc, settings)
    for other in conflicting_ids(doc["id"], existing_chart_ids(storage, settings.root_prefix)):
        errors.append(f"id: '{doc['id']}' conflicts with existing chart '{other}'")

    if lane == "large":
        if not allow_row_level:
            errors.append("large lane publishes row-level data; pass --allow-row-level to confirm")
        else:
            errors += check_aggregate(doc["aggregate"], data_path)
    return errors


def validate_dashboard_file(path: Path, settings: Settings, storage: Storage) -> list[str]:
    path = Path(path)
    doc, errors = read_document(path)
    if doc is None:
        return errors
    try:
        validate_dashboard(doc)
    except SchemaError as err:
        return [f"dashboard: {e}" for e in err.errors]
    implied = _id_from_path(path, "dashboards")
    if implied is not None and implied != doc["id"]:
        errors.append(f"id: dashboard says '{doc['id']}' but the file is '{implied}'")
    for i, tile in enumerate(doc["layout"]):
        if "chart" not in tile:
            continue
        try:
            storage.head(chart_key(settings.root_prefix, tile["chart"]))
        except NotFound:
            errors.append(f"layout/{i}/chart: chart '{tile['chart']}' is not published")
    errors += check_author(doc, settings)
    return errors
