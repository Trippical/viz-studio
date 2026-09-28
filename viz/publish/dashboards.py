"""Staged dashboard files: a new skeleton, or a copy of a published dashboard to edit.
Both stamp author and timestamps the same way `viz stage` stamps charts, so the
file passes the author check in `viz validate` without hand-editing."""
import json
from datetime import datetime
from pathlib import Path

from ..config import Settings
from ..ids import dashboard_key, validate_id
from ..schemas import SchemaError, validate_dashboard
from ..storage import NotFound, Storage
from .staging import TIMESTAMP_FORMAT, dashboard_path, title_from_id

CHART_TILE_SIZE = {"w": 6, "h": 4}
PLACEHOLDER_MARKDOWN = "Describe what this dashboard answers."


class DashboardError(ValueError):
    pass


def new_dashboard(dashboard_id: str, chart_ids: list[str], title: str | None, author: str, now: datetime) -> dict:
    validate_id(dashboard_id)
    for chart_id in chart_ids:
        validate_id(chart_id)
    stamp = now.strftime(TIMESTAMP_FORMAT)
    layout = [{"chart": chart_id, **CHART_TILE_SIZE} for chart_id in chart_ids]
    if not layout:
        layout = [{"markdown": PLACEHOLDER_MARKDOWN, "w": 12, "h": 1}]
    doc = {
        "schema_version": 1,
        "id": dashboard_id,
        "title": title or title_from_id(dashboard_id),
        "author": author,
        "created_at": stamp,
        "updated_at": stamp,
        "controls": [],
        "layout": layout,
    }
    return validate_dashboard(doc)


def pulled_dashboard(dashboard_id: str, settings: Settings, storage: Storage, author: str, now: datetime) -> dict:
    validate_id(dashboard_id)
    try:
        raw = storage.get(dashboard_key(settings.root_prefix, dashboard_id))
    except NotFound as err:
        raise DashboardError(f"dashboard '{dashboard_id}' is not published") from err
    try:
        doc = validate_dashboard(json.loads(raw))
    except (ValueError, SchemaError) as err:
        raise DashboardError(f"published dashboard '{dashboard_id}' is invalid: {err}") from err
    if doc["id"] != dashboard_id:
        raise DashboardError(f"published dashboard '{dashboard_id}' says its id is '{doc['id']}'")
    doc["author"] = author
    doc["updated_at"] = now.strftime(TIMESTAMP_FORMAT)
    return doc


def write_staged_dashboard(doc: dict, staging_root: Path, force: bool = False) -> Path:
    path = dashboard_path(staging_root, doc["id"])
    if path.exists() and not force:
        raise DashboardError(f"{path} already exists; pass --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path
