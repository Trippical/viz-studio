"""Everything `viz validate` checks beyond the JSON Schema. Every function returns
a list of error strings; an empty list means valid."""
import json
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from ..config import Settings
from ..ids import chart_key, data_file_name, is_ancestor
from ..schemas import SchemaError, validate_chart, validate_dashboard
from ..storage import NotFound, Storage
from .identity import check_author
from .query import QueryError, current_user, databricks_configured
from .infer import UnsupportedColumn, infer_columns, table_from_file
from .staging import LARGE_MAX_BYTES, SMALL_MAX_BYTES, SMALL_MAX_ROWS, file_sha256

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
    except RecursionError:
        return None, [f"{path.name}: invalid JSON (nested too deeply)"]
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


def _id_from_path(path: Path, kind: str, doc_id: str) -> str | None:
    """The id implied by a path under a `charts` or `dashboards` directory, or None.

    doc_id is the id the document declares. When the path ends with <kind>/<doc_id>,
    that is the answer, even if doc_id itself has a `charts` or `dashboards` segment
    (for example `team/charts/revenue`). Otherwise the id is everything after the
    last <kind> directory, which is what the error message reports."""
    parts = list(Path(path).parts)
    if kind == "dashboards" and parts and parts[-1].endswith(".json"):
        parts[-1] = parts[-1][:-5]
    id_parts = doc_id.split("/")
    n = len(id_parts)
    if len(parts) > n and parts[-n:] == id_parts and parts[-n - 1] == kind:
        return doc_id
    if kind not in parts:
        return None
    tail = parts[len(parts) - parts[::-1].index(kind):]
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


def _check_chart_author(doc: dict, settings: Settings) -> list[str]:
    """A chart staged by `viz query` carries the Databricks login as its author. When the
    Databricks variables are set, confirm that login; otherwise check VIZ_AUTHOR as usual."""
    source = doc.get("source") or {}
    if source.get("kind") != "databricks-sql" or not databricks_configured():
        return check_author(doc, settings)
    try:
        user = current_user(source.get("warehouse_id"))
    except QueryError as err:
        return [f"author: could not confirm the Databricks user: {err}"]
    return check_author(doc, settings, databricks_user=user)


def validate_staged_chart(chart_dir: Path, settings: Settings, storage: Storage, allow_row_level: bool = False) -> list[str]:
    chart_dir = Path(chart_dir)
    doc, errors = read_document(chart_dir / "chart.json")
    if doc is None:
        return errors
    try:
        validate_chart(doc)
    except SchemaError as err:
        return [f"chart.json: {e}" for e in err.errors]

    implied = _id_from_path(chart_dir, "charts", doc["id"])
    if implied is not None and implied != doc["id"]:
        errors.append(f"id: chart.json says '{doc['id']}' but the directory is '{implied}'")

    data = doc["data"]
    fmt, lane, file_name = data["format"], data["lane"], data["file"]
    data_path = chart_dir / file_name
    if not data_path.is_file():
        return errors + [f"{file_name}: not found"]
    expected_name = data_file_name(file_sha256(data_path), fmt)
    if expected_name != file_name:
        errors.append(f"data.file: '{file_name}' does not match the file's SHA-256; it should be named '{expected_name}'")
    others = sorted(p.name for p in chart_dir.glob("data.*") if p.name != file_name)
    if others:
        errors.append(f"data: the staged directory holds other data files ({', '.join(others)}); keep only '{file_name}'")
    size = data_path.stat().st_size
    if size != data["bytes"]:
        errors.append(f"data.bytes: declared {data['bytes']}, file is {size} bytes")

    if fmt == "json":
        try:
            table = table_from_file(data_path)
        except (UnsupportedColumn, ValueError) as err:
            return errors + [f"{file_name}: {err}"]
        rows = len(table)
    else:
        try:
            rows = pq.read_metadata(data_path).num_rows
            table = pq.read_table(data_path)
        except (pa.ArrowException, OSError, ValueError) as err:
            return errors + [f"{file_name}: {err}"]
    if rows != data["rows"]:
        errors.append(f"data.rows: declared {data['rows']}, file has {rows}")
    try:
        errors += _compare_columns(data["columns"], infer_columns(table))
    except UnsupportedColumn as err:
        errors.append(f"{file_name}: {err}")

    if lane == "small" and (rows > SMALL_MAX_ROWS or size > SMALL_MAX_BYTES):
        errors.append(f"data: small lane allows at most {SMALL_MAX_ROWS} rows and {SMALL_MAX_BYTES} bytes")
    if lane == "large" and size > LARGE_MAX_BYTES:
        errors.append(f"data: large lane allows at most {LARGE_MAX_BYTES} bytes")

    errors += _check_chart_author(doc, settings)
    for other in conflicting_ids(doc["id"], existing_chart_ids(storage, settings.root_prefix)):
        errors.append(f"id: '{doc['id']}' conflicts with existing chart '{other}'")

    if lane == "large":
        if not allow_row_level:
            errors.append("large lane publishes row-level data; ask the user before passing --allow-row-level to confirm")
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
    implied = _id_from_path(path, "dashboards", doc["id"])
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
