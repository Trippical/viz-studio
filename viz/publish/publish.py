"""Copy a validated staged chart or dashboard into the bucket.

A chart publish is three steps (hardening decision B2):
1. PUT the data file under its content-addressed key. Same bytes, same key, so a retry is harmless.
2. PUT chart.json conditionally. This is the single commit point: a new chart is written only if
   no chart.json exists (if_none_match); an overwrite only if chart.json still has the ETag read
   during the overwrite guard (if_match). Readers see the old chart or the new one, never a
   chart.json whose data file is missing.
3. Delete every other data.* object of the chart except the file the replaced chart.json named,
   so a reader still holding the old chart.json can fetch its data. One generation is kept.
"""
import json
import re
import sys
from pathlib import Path

from ..config import Settings
from ..ids import DATA_FILE_PATTERN, chart_key, dashboard_key, data_key
from ..storage import NotFound, PreconditionFailed, Storage
from .validate import read_document, validate_dashboard_file, validate_staged_chart

MEDIA_TYPES = {"json": "application/json", "parquet": "application/octet-stream"}


class PublishRefused(Exception):
    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _existing(storage: Storage, key: str) -> tuple[dict | None, str | None]:
    """The published document at key and the ETag it was read with, or (None, None).
    The ETag is read before the body: if the object changes in between, the later
    conditional PUT fails instead of overwriting something nobody was shown."""
    try:
        etag = storage.head(key).etag
        raw = storage.get(key)
    except NotFound:
        return None, None
    try:
        doc = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return {}, etag
    return (doc if isinstance(doc, dict) else {}), etag


def _guard_overwrite(storage: Storage, key: str, force: bool, out) -> tuple[dict | None, str | None]:
    """Refuse to overwrite without force. Returns the existing document and its ETag,
    or (None, None) when nothing is published at key."""
    existing, etag = _existing(storage, key)
    if existing is None:
        return None, None
    author = existing.get("author", "unknown")
    updated = existing.get("updated_at", "unknown")
    if not force:
        raise PublishRefused([f"id exists: author {author}, updated_at {updated}; ask the user before passing --force to overwrite"])
    print(f"overwriting: author {author}, updated_at {updated}", file=out)
    return existing, etag


def _commit(storage: Storage, key: str, payload: bytes, doc_id: str, etag: str | None) -> None:
    """The conditional PUT that makes a publish visible. etag None means a new document."""
    try:
        if etag is None:
            storage.put(key, payload, "application/json", if_none_match=True)
        else:
            storage.put(key, payload, "application/json", if_match=etag)
    except PreconditionFailed as err:
        raise PublishRefused([f"{doc_id} changed since you checked it; run the command again"]) from err


def _named_data_file(doc: dict | None) -> str | None:
    """The data.file a published chart.json names, if it is a valid content-addressed name."""
    if not isinstance(doc, dict):
        return None
    data = doc.get("data")
    name = data.get("file") if isinstance(data, dict) else None
    if isinstance(name, str) and DATA_FILE_PATTERN.fullmatch(name):
        return name
    return None


def _delete_other_data_files(storage: Storage, root: str, chart_id: str, keep: set[str]) -> None:
    """Delete every data.* object directly under charts/<id>/ whose name is not in keep.
    Keys one level deeper belong to another chart id and are never touched."""
    prefix = f"{root}charts/{chart_id}/"
    for info in storage.list(prefix):
        name = info.key[len(prefix):]
        if "/" in name or not name.startswith("data.") or name in keep:
            continue
        storage.delete(info.key)


def destination(settings: Settings, key: str) -> str:
    """Where a key lives, for the success line: s3://<bucket>/<key>, or a local file path."""
    if settings.storage == "s3":
        return f"s3://{settings.s3_bucket}/{key}"
    return str((Path(settings.local_dir) / key).resolve())


CREATED_AT_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


def keep_created_at(existing: dict | None, staged_file: Path) -> None:
    """Republishing an id keeps the created_at of the published document (finding A20).
    `existing` is the document the overwrite guard read (None for a new id). The staged
    file is rewritten before the upload, so the bytes in the bucket still equal the staged
    file byte for byte. The published value is untrusted: it is copied only when it is a
    plain UTC timestamp such as 2026-09-29T10:00:00Z."""
    if not isinstance(existing, dict):
        return
    created = existing.get("created_at")
    if not isinstance(created, str) or not CREATED_AT_PATTERN.fullmatch(created):
        return
    staged_file = Path(staged_file)
    doc = json.loads(staged_file.read_text(encoding="utf-8"))
    if doc.get("created_at") == created:
        return
    doc["created_at"] = created
    tmp = staged_file.with_name(staged_file.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(staged_file)


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
    existing, etag = _guard_overwrite(storage, key, force, out)
    keep_created_at(existing, chart_dir / "chart.json")

    storage.put(data_key(root, chart_id, file_name), (chart_dir / file_name).read_bytes(), MEDIA_TYPES[fmt])
    _commit(storage, key, (chart_dir / "chart.json").read_bytes(), chart_id, etag)
    keep = {file_name}
    previous = _named_data_file(existing)
    if previous is not None:
        keep.add(previous)
    _delete_other_data_files(storage, root, chart_id, keep)
    print(f"published: {chart_id} -> {destination(settings, key)}", file=out)
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
    existing, etag = _guard_overwrite(storage, key, force, out)
    keep_created_at(existing, path)
    _commit(storage, key, path.read_bytes(), dashboard_id, etag)
    print(f"published: {dashboard_id} -> {destination(settings, key)}", file=out)
    return dashboard_id
