"""Copy a validated staged chart or dashboard into the bucket. Data first, then the document."""
import json
import sys
from pathlib import Path

from ..config import Settings
from ..ids import chart_key, dashboard_key, data_key
from ..storage import NotFound, Storage
from .validate import read_document, validate_dashboard_file, validate_staged_chart

MEDIA_TYPES = {"json": "application/json", "parquet": "application/octet-stream"}


class PublishRefused(Exception):
    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _existing(storage: Storage, key: str) -> dict | None:
    try:
        raw = storage.get(key)
    except NotFound:
        return None
    try:
        doc = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _guard_overwrite(storage: Storage, key: str, force: bool, out) -> None:
    existing = _existing(storage, key)
    if existing is None:
        return
    author = existing.get("author", "unknown")
    updated = existing.get("updated_at", "unknown")
    if not force:
        raise PublishRefused([f"id exists: author {author}, updated_at {updated}; pass --force to overwrite"])
    print(f"overwriting: author {author}, updated_at {updated}", file=out)


def _delete_other_data_files(storage: Storage, root: str, chart_id: str, keep: set[str]) -> None:
    """Delete every data.* object directly under charts/<id>/ whose name is not in keep.
    Keys one level deeper belong to another chart id and are never touched."""
    prefix = f"{root}charts/{chart_id}/"
    for info in storage.list(prefix):
        name = info.key[len(prefix):]
        if "/" in name or not name.startswith("data.") or name in keep:
            continue
        storage.delete(info.key)


def publish_chart(chart_dir: Path, settings: Settings, storage: Storage, force: bool = False,
                  allow_row_level: bool = False, out=None) -> str:
    out = sys.stdout if out is None else out
    chart_dir = Path(chart_dir)
    errors = validate_staged_chart(chart_dir, settings, storage, allow_row_level=allow_row_level)
    if errors:
        raise PublishRefused(errors)
    doc, _ = read_document(chart_dir / "chart.json")
    chart_id = doc["id"]
    fmt = doc["data"]["format"]
    file_name = doc["data"]["file"]
    root = settings.root_prefix
    key = chart_key(root, chart_id)
    _guard_overwrite(storage, key, force, out)

    storage.put(data_key(root, chart_id, file_name), (chart_dir / file_name).read_bytes(), MEDIA_TYPES[fmt])
    storage.put(key, (chart_dir / "chart.json").read_bytes(), "application/json")
    _delete_other_data_files(storage, root, chart_id, keep={file_name})
    print(f"published: {chart_id}", file=out)
    return chart_id


def publish_dashboard(path: Path, settings: Settings, storage: Storage, force: bool = False, out=None) -> str:
    out = sys.stdout if out is None else out
    path = Path(path)
    errors = validate_dashboard_file(path, settings, storage)
    if errors:
        raise PublishRefused(errors)
    doc, _ = read_document(path)
    dashboard_id = doc["id"]
    key = dashboard_key(settings.root_prefix, dashboard_id)
    _guard_overwrite(storage, key, force, out)
    storage.put(key, path.read_bytes(), "application/json")
    print(f"published: {dashboard_id}", file=out)
    return dashboard_id
