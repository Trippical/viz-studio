"""Rename a chart or dashboard id in the bucket and rewrite the dashboards that reference it."""
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from ..config import Settings
from ..ids import chart_key, dashboard_key, validate_id
from ..schemas import SchemaError, validate_chart, validate_dashboard
from ..storage import NotFound, Storage
from .staging import TIMESTAMP_FORMAT
from .validate import conflicting_ids, existing_chart_ids


class MoveError(ValueError):
    pass


@dataclass
class MovePlan:
    kind: str
    old_id: str
    new_id: str
    keys: list[tuple[str, str]]
    affected_dashboards: list[str]


def _exists(storage: Storage, key: str) -> bool:
    try:
        storage.head(key)
    except NotFound:
        return False
    return True


def _dashboards(storage: Storage, root: str) -> list[tuple[str, dict]]:
    prefix = f"{root}dashboards/"
    out = []
    for info in storage.list(prefix):
        if not info.key.endswith(".json") or info.key.endswith("_folder.json"):
            continue
        try:
            doc = json.loads(storage.get(info.key))
        except (UnicodeDecodeError, json.JSONDecodeError, NotFound):
            continue
        if isinstance(doc, dict):
            out.append((info.key[len(prefix):-5], doc))
    return out


def _references(doc: dict, chart_id: str) -> bool:
    layout = doc.get("layout")
    if not isinstance(layout, list):
        return False
    return any(isinstance(t, dict) and t.get("chart") == chart_id for t in layout)


def _load_doc(storage: Storage, key: str) -> dict:
    """Read and parse a document key as untrusted content: it must be a JSON object."""
    try:
        doc = json.loads(storage.get(key))
    except json.JSONDecodeError as err:
        raise MoveError(f"{key}: invalid JSON ({err})") from err
    if not isinstance(doc, dict):
        raise MoveError(f"{key}: not a JSON object")
    return doc


def _validate_rewritten(kind: str, key: str, doc: dict, new_id: str) -> None:
    """The document as it will be written after the rename: same content, new id."""
    candidate = dict(doc)
    candidate["id"] = new_id
    validator = validate_chart if kind == "chart" else validate_dashboard
    try:
        validator(candidate)
    except SchemaError as err:
        raise MoveError(f"{key}: {'; '.join(err.errors)}") from err


def _validate_dashboard_reference(key: str, doc: dict, old_id: str, new_id: str) -> None:
    """A dashboard that references the moving chart, with the reference rewritten."""
    candidate = json.loads(json.dumps(doc))
    layout = candidate.get("layout")
    if isinstance(layout, list):
        for tile in layout:
            if isinstance(tile, dict) and tile.get("chart") == old_id:
                tile["chart"] = new_id
    try:
        validate_dashboard(candidate)
    except SchemaError as err:
        raise MoveError(f"{key}: {'; '.join(err.errors)}") from err


def _pick_kind(storage: Storage, root: str, old_id: str, kind: str | None) -> str:
    """Which object to move. An id can be both a chart and a dashboard; then the caller
    must say which with --kind (finding A26)."""
    is_chart = _exists(storage, chart_key(root, old_id))
    is_dashboard = _exists(storage, dashboard_key(root, old_id))
    if kind == "chart":
        if not is_chart:
            raise MoveError(f"no chart with id '{old_id}'")
        return "chart"
    if kind == "dashboard":
        if not is_dashboard:
            raise MoveError(f"no dashboard with id '{old_id}'")
        return "dashboard"
    if kind is not None:
        raise MoveError(f"unknown kind '{kind}'; use chart or dashboard")
    if is_chart and is_dashboard:
        raise MoveError(f"'{old_id}' is both a chart and a dashboard; pass --kind chart or --kind dashboard")
    if is_chart:
        return "chart"
    if is_dashboard:
        return "dashboard"
    raise MoveError(f"no chart or dashboard with id '{old_id}'")


def plan_move(old_id: str, new_id: str, settings: Settings, storage: Storage, kind: str | None = None) -> MovePlan:
    validate_id(old_id)
    validate_id(new_id)
    if old_id == new_id:
        raise MoveError("old and new id are the same")
    root = settings.root_prefix
    kind = _pick_kind(storage, root, old_id, kind)

    if kind == "chart":
        if _exists(storage, chart_key(root, new_id)):
            raise MoveError(f"chart '{new_id}' already exists")
        others = [e for e in existing_chart_ids(storage, root) if e != old_id]
        for other in conflicting_ids(new_id, others):
            raise MoveError(f"'{new_id}' conflicts with existing chart '{other}'")
        old_prefix = f"{root}charts/{old_id}/"
        new_prefix = f"{root}charts/{new_id}/"
        chart_json_key = f"{old_prefix}chart.json"
        chart_doc = _load_doc(storage, chart_json_key)
        _validate_rewritten("chart", chart_json_key, chart_doc, new_id)
        keys = []
        for info in storage.list(old_prefix):
            rest = info.key[len(old_prefix):]
            if "/" in rest:
                continue  # a descendant id's files, not this chart's
            keys.append((info.key, new_prefix + rest))
        keys.sort(key=lambda pair: pair[0].endswith("/chart.json"))  # chart.json last
        affected_docs = [(did, doc) for did, doc in _dashboards(storage, root) if _references(doc, old_id)]
        for dashboard_id, doc in affected_docs:
            _validate_dashboard_reference(dashboard_key(root, dashboard_id), doc, old_id, new_id)
        affected = sorted(did for did, doc in affected_docs)
        return MovePlan("chart", old_id, new_id, keys, affected)

    if kind == "dashboard":
        if _exists(storage, dashboard_key(root, new_id)):
            raise MoveError(f"dashboard '{new_id}' already exists")
        old_key = dashboard_key(root, old_id)
        doc = _load_doc(storage, old_key)
        _validate_rewritten("dashboard", old_key, doc, new_id)
        return MovePlan("dashboard", old_id, new_id, [(old_key, dashboard_key(root, new_id))], [])

    raise MoveError(f"no chart or dashboard with id '{old_id}'")


def describe(plan: MovePlan) -> str:
    lines = [f"move {plan.kind} '{plan.old_id}' -> '{plan.new_id}'"]
    for old_key, new_key in plan.keys:
        lines.append(f"  {old_key} -> {new_key}")
    if plan.affected_dashboards:
        lines.append("dashboards to rewrite: " + ", ".join(plan.affected_dashboards))
    elif plan.kind == "chart":
        lines.append("no dashboards reference it")
    return "\n".join(lines)


def _put_json(storage: Storage, key: str, doc: dict) -> None:
    storage.put(key, (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), "application/json")


def apply_move(plan: MovePlan, settings: Settings, storage: Storage) -> None:
    """Read and validate every document that will be rewritten before writing or copying
    anything, so an invalid moving document or a broken referencing dashboard leaves the
    bucket untouched."""
    now = datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)
    root = settings.root_prefix

    rewritten: dict[str, dict] = {}
    for old_key, new_key in plan.keys:
        is_document = plan.kind == "dashboard" or old_key.endswith("/chart.json")
        if not is_document:
            continue
        doc = _load_doc(storage, old_key)
        _validate_rewritten(plan.kind, old_key, doc, plan.new_id)
        doc = dict(doc)
        doc["id"] = plan.new_id
        doc["updated_at"] = now
        rewritten[old_key] = doc

    affected_docs: dict[str, dict] = {}
    for dashboard_id in plan.affected_dashboards:
        key = dashboard_key(root, dashboard_id)
        doc = _load_doc(storage, key)
        _validate_dashboard_reference(key, doc, plan.old_id, plan.new_id)
        for tile in doc.get("layout", []):
            if isinstance(tile, dict) and tile.get("chart") == plan.old_id:
                tile["chart"] = plan.new_id
        doc["updated_at"] = now
        affected_docs[key] = doc

    for old_key, new_key in plan.keys:
        if old_key in rewritten:
            _put_json(storage, new_key, rewritten[old_key])
        else:
            storage.copy(old_key, new_key)
    for key, doc in affected_docs.items():
        _put_json(storage, key, doc)
    for old_key, _new_key in plan.keys:
        storage.delete(old_key)
