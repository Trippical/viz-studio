"""Rename a chart or dashboard id in the bucket and rewrite the dashboards that reference it."""
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from ..config import Settings
from ..ids import chart_key, dashboard_key, validate_id
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


def plan_move(old_id: str, new_id: str, settings: Settings, storage: Storage) -> MovePlan:
    validate_id(old_id)
    validate_id(new_id)
    if old_id == new_id:
        raise MoveError("old and new id are the same")
    root = settings.root_prefix

    if _exists(storage, chart_key(root, old_id)):
        if _exists(storage, chart_key(root, new_id)):
            raise MoveError(f"chart '{new_id}' already exists")
        others = [e for e in existing_chart_ids(storage, root) if e != old_id]
        for other in conflicting_ids(new_id, others):
            raise MoveError(f"'{new_id}' conflicts with existing chart '{other}'")
        old_prefix = f"{root}charts/{old_id}/"
        new_prefix = f"{root}charts/{new_id}/"
        keys = []
        for info in storage.list(old_prefix):
            rest = info.key[len(old_prefix):]
            if "/" in rest:
                continue  # a descendant id's files, not this chart's
            keys.append((info.key, new_prefix + rest))
        keys.sort(key=lambda pair: pair[0].endswith("/chart.json"))  # chart.json last
        affected = sorted(did for did, doc in _dashboards(storage, root) if _references(doc, old_id))
        return MovePlan("chart", old_id, new_id, keys, affected)

    if _exists(storage, dashboard_key(root, old_id)):
        if _exists(storage, dashboard_key(root, new_id)):
            raise MoveError(f"dashboard '{new_id}' already exists")
        return MovePlan("dashboard", old_id, new_id, [(dashboard_key(root, old_id), dashboard_key(root, new_id))], [])

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
    now = datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)
    for old_key, new_key in plan.keys:
        is_document = plan.kind == "dashboard" or old_key.endswith("/chart.json")
        if is_document:
            doc = json.loads(storage.get(old_key))
            doc["id"] = plan.new_id
            doc["updated_at"] = now
            _put_json(storage, new_key, doc)
        else:
            storage.copy(old_key, new_key)
    for dashboard_id in plan.affected_dashboards:
        key = dashboard_key(settings.root_prefix, dashboard_id)
        doc = json.loads(storage.get(key))
        for tile in doc.get("layout", []):
            if isinstance(tile, dict) and tile.get("chart") == plan.old_id:
                tile["chart"] = plan.new_id
        doc["updated_at"] = now
        _put_json(storage, key, doc)
    for old_key, _new_key in plan.keys:
        storage.delete(old_key)
