"""Load and validate one document from storage. The only way the server reads JSON."""
import json
from typing import Callable

from ..config import Settings
from ..ids import chart_key, dashboard_key, folder_key
from ..schemas import SchemaError, validate_chart, validate_dashboard, validate_folder
from ..storage import NotFound, Storage


class DocumentTooLarge(ValueError):
    pass


def _read(storage: Storage, settings: Settings, key: str) -> dict:
    info = storage.head(key)
    if info.size > settings.max_document_bytes:
        raise DocumentTooLarge(f"{key}: {info.size} bytes exceeds {settings.max_document_bytes}")
    raw = storage.get(key)
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SchemaError([f"$: invalid JSON ({err})"]) from err


def _load(storage, settings, key, validate: Callable[[dict], dict], expected_id: str) -> dict:
    doc = validate(_read(storage, settings, key))
    if doc.get("id") != expected_id:
        raise SchemaError([f"id: expected {expected_id!r}, found {doc.get('id')!r}"])
    return doc


def load_chart(storage: Storage, settings: Settings, chart_id: str) -> dict:
    return _load(storage, settings, chart_key(settings.root_prefix, chart_id), validate_chart, chart_id)


def load_dashboard(storage: Storage, settings: Settings, dashboard_id: str) -> dict:
    return _load(storage, settings, dashboard_key(settings.root_prefix, dashboard_id), validate_dashboard, dashboard_id)


def load_folder(storage: Storage, settings: Settings, kind: str, folder: str) -> dict | None:
    try:
        return validate_folder(_read(storage, settings, folder_key(settings.root_prefix, kind, folder)))
    except NotFound:
        return None


def public_chart(doc: dict) -> dict:
    """The chart as the API returns it. SQL text stays in the bucket unless show_sql."""
    source = doc.get("source")
    if not source or source.get("show_sql"):
        return doc
    out = dict(doc)
    public = {"kind": source.get("kind"), "show_sql": False}
    if "schedule" in source:
        public["schedule"] = source["schedule"]
    out["source"] = public
    return out
