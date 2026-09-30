"""Staged dashboard files: a new skeleton, or a copy of a published dashboard to edit.
Both stamp author and timestamps the same way `viz stage` stamps charts, so the
file passes the author check in `viz validate` without hand-editing."""
import json
from datetime import datetime
from pathlib import Path

from .. import strict_json
from ..config import Settings
from ..ids import dashboard_key, validate_id
from ..schemas import SchemaError, validate_dashboard
from ..storage import NotFound, Storage
from .staging import TIMESTAMP_FORMAT, dashboard_path, title_from_id

CHART_TILE_SIZE = {"w": 6, "h": 4}
PLACEHOLDER_MARKDOWN = "Describe what this dashboard answers."
PULLED_ETAG_SUFFIX = ".pulled-etag"


def pulled_etag_path(dashboard_file: Path) -> Path:
    """The file next to a staged dashboard that records which published version
    `viz pull-dashboard` copied: its ETag, one line (finding A25). The dashboard schema
    allows no extra keys, so the ETag cannot live inside the dashboard file."""
    dashboard_file = Path(dashboard_file)
    return dashboard_file.with_name(dashboard_file.name + PULLED_ETAG_SUFFIX)


def write_pulled_etag(dashboard_file: Path, etag: str) -> None:
    pulled_etag_path(dashboard_file).write_text(etag + "\n", encoding="utf-8", newline="\n")


def read_pulled_etag(dashboard_file: Path) -> str | None:
    path = pulled_etag_path(dashboard_file)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def clear_pulled_etag(dashboard_file: Path) -> None:
    pulled_etag_path(dashboard_file).unlink(missing_ok=True)


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


def pulled_dashboard(dashboard_id: str, settings: Settings, storage: Storage, author: str,
                     now: datetime) -> tuple[dict, str]:
    """The published dashboard restamped for editing, and the ETag of the version pulled.
    The ETag is read before the body: if the dashboard changes in between, the ETag is
    older than the body and the later publish is refused, never silently applied."""
    validate_id(dashboard_id)
    key = dashboard_key(settings.root_prefix, dashboard_id)
    try:
        etag = storage.head(key).etag
        raw = storage.get(key)
    except NotFound as err:
        raise DashboardError(f"dashboard '{dashboard_id}' is not published") from err
    try:
        doc = validate_dashboard(strict_json.loads(raw))
    except strict_json.InvalidJson as err:
        raise DashboardError(f"published dashboard '{dashboard_id}' is invalid: {err.describe('$')}") from err
    except (ValueError, SchemaError) as err:
        raise DashboardError(f"published dashboard '{dashboard_id}' is invalid: {err}") from err
    if doc["id"] != dashboard_id:
        raise DashboardError(f"published dashboard '{dashboard_id}' says its id is '{doc['id']}'")
    doc["author"] = author
    doc["updated_at"] = now.strftime(TIMESTAMP_FORMAT)
    return doc, etag


def write_staged_dashboard(doc: dict, staging_root: Path, force: bool = False) -> Path:
    path = dashboard_path(staging_root, doc["id"])
    if path.exists() and not force:
        raise DashboardError(f"{path} already exists; ask the user before passing --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path
