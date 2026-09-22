"""Build the folder tree from storage and cache it with single-flight refresh."""
import asyncio
import logging
import time
from datetime import datetime, timezone

from ..config import Settings
from ..ids import InvalidId, is_ancestor, validate_id
from ..schemas import SchemaError
from ..storage import Storage
from .documents import DocumentTooLarge, load_chart, load_dashboard, load_folder

_log = logging.getLogger("viz.server")


def _folder_node(path: str) -> dict:
    return {"type": "folder", "path": path, "name": path.rsplit("/", 1)[-1] if path else "",
            "title": None, "description": None, "order": None, "error": None, "folders": [], "items": []}


def _chart_node(storage, settings, chart_id: str) -> dict:
    try:
        validate_id(chart_id)
        doc = load_chart(storage, settings, chart_id)
    except InvalidId:
        return {"type": "chart", "id": chart_id, "error": "invalid id"}
    except (SchemaError, DocumentTooLarge) as err:
        return {"type": "chart", "id": chart_id, "error": str(err)}
    return {
        "type": "chart", "id": chart_id, "title": doc["title"], "description": doc.get("description"),
        "tags": doc.get("tags", []), "renderer": doc["renderer"], "lane": doc["data"]["lane"],
        "static": "source" not in doc, "updated_at": doc.get("updated_at"),
    }


def _dashboard_node(storage, settings, dashboard_id: str) -> dict:
    try:
        validate_id(dashboard_id)
        doc = load_dashboard(storage, settings, dashboard_id)
    except InvalidId:
        return {"type": "dashboard", "id": dashboard_id, "error": "invalid id"}
    except (SchemaError, DocumentTooLarge) as err:
        return {"type": "dashboard", "id": dashboard_id, "error": str(err)}
    return {
        "type": "dashboard", "id": dashboard_id, "title": doc["title"], "description": doc.get("description"),
        "tags": doc.get("tags", []), "controls": doc.get("controls", []), "updated_at": doc.get("updated_at"),
    }


def _mark_conflicts(nodes: list[dict]) -> None:
    ids = [n["id"] for n in nodes]
    for i, node in enumerate(list(nodes)):
        others = [other for other in ids if other != node["id"] and (is_ancestor(node["id"], other) or is_ancestor(other, node["id"]))]
        if others:
            nodes[i] = {"type": node["type"], "id": node["id"], "error": f"id conflicts with {', '.join(sorted(others))}"}


def _assemble(kind: str, storage, settings, items: list[dict], folder_paths: set[str]) -> dict:
    root = _folder_node("")
    index = {"": root}

    def folder_for(path: str) -> dict:
        if path in index:
            return index[path]
        parent_path = path.rsplit("/", 1)[0] if "/" in path else ""
        parent = folder_for(parent_path)
        node = _folder_node(path)
        parent["folders"].append(node)
        index[path] = node
        return node

    for path in sorted(folder_paths):
        folder_for(path)
    for item in items:
        parent_path = item["id"].rsplit("/", 1)[0] if "/" in item["id"] else ""
        folder_for(parent_path)["items"].append(item)

    for path, node in index.items():
        if path not in folder_paths and path != "":
            continue
        try:
            meta = load_folder(storage, settings, kind, path)
        except (SchemaError, DocumentTooLarge) as err:
            node["error"] = str(err)
            continue
        if meta:
            node["title"] = meta.get("title")
            node["description"] = meta.get("description")
            node["order"] = meta.get("order")

    def sort(node: dict) -> None:
        node["folders"].sort(key=lambda f: (f["order"] is None, f["order"] if f["order"] is not None else 0, f["title"] or f["name"]))
        node["items"].sort(key=lambda i: (i.get("title") or i["id"]).lower())
        for child in node["folders"]:
            sort(child)

    sort(root)
    return root


def build_tree(storage: Storage, settings: Settings) -> dict:
    root = settings.root_prefix
    charts_prefix = f"{root}charts/"
    dashboards_prefix = f"{root}dashboards/"

    chart_ids, chart_folders = [], set()
    for obj in storage.list(charts_prefix):
        rel = obj.key[len(charts_prefix):]
        if rel.endswith("/chart.json"):
            chart_ids.append(rel[: -len("/chart.json")])
        elif rel.endswith("_folder.json"):
            chart_folders.add(rel[: -len("_folder.json")].rstrip("/"))

    dashboard_ids, dashboard_folders = [], set()
    for obj in storage.list(dashboards_prefix):
        rel = obj.key[len(dashboards_prefix):]
        if rel.endswith("_folder.json"):
            dashboard_folders.add(rel[: -len("_folder.json")].rstrip("/"))
        elif rel.endswith(".json"):
            dashboard_ids.append(rel[: -len(".json")])

    charts = [_chart_node(storage, settings, cid) for cid in chart_ids]
    _mark_conflicts(charts)
    dashboards = [_dashboard_node(storage, settings, did) for did in dashboard_ids]
    _mark_conflicts(dashboards)

    return {
        "charts": _assemble("charts", storage, settings, charts, chart_folders),
        "dashboards": _assemble("dashboards", storage, settings, dashboards, dashboard_folders),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


class TreeCache:
    """Serve the last tree; rebuild in the background when stale; never rebuild twice at once."""

    def __init__(self, storage: Storage, settings: Settings):
        self.storage = storage
        self.settings = settings
        self.builds = 0
        self._value: dict | None = None
        self._built_at = 0.0
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None
        self._generation = 0

    def _build(self) -> dict:
        self.builds += 1
        return build_tree(self.storage, self.settings)

    async def get(self) -> dict:
        if self._value is None:
            async with self._lock:
                if self._value is None:
                    self._value = await asyncio.to_thread(self._build)
                    self._built_at = time.monotonic()
            return self._value
        stale = time.monotonic() - self._built_at >= self.settings.tree_ttl_seconds
        if stale and (self._refresh_task is None or self._refresh_task.done()):
            self._refresh_task = asyncio.create_task(self._refresh())
        return self._value

    async def _refresh(self) -> None:
        generation = self._generation
        try:
            value = await asyncio.to_thread(self._build)
        except Exception:
            _log.exception("tree refresh failed")
            return
        if self._generation == generation:
            self._value = value
            self._built_at = time.monotonic()

    def invalidate(self) -> None:
        self._value = None
        self._generation += 1
