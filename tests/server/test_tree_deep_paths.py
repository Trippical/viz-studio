"""Adopter fix A4: folder paths and item ids from the bucket are nested into the tree
only when they are valid ids, so a very deep key cannot exhaust recursion when the
tree is built or serialized.

Windows cannot create a 300-segment folder on disk, so the deep keys are added to the
storage in memory (the local backend is patched, not the tree code)."""
import pytest

from viz.server.tree import build_tree
from viz.storage import NotFound
from viz.storage.base import ObjectInfo



def _overlay(monkeypatch, storage, extra: dict[str, bytes]) -> None:
    """Make storage also hold the keys in extra."""
    real_list, real_head, real_get = storage.list, storage.head, storage.get

    def info(key):
        return ObjectInfo(key=key, size=len(extra[key]), etag="x", last_modified=None)

    def list_(prefix):
        added = [info(k) for k in extra if k.startswith(prefix)]
        return sorted(real_list(prefix) + added, key=lambda i: i.key)

    def head(key):
        return info(key) if key in extra else real_head(key)

    def get(key):
        return extra[key] if key in extra else real_get(key)

    monkeypatch.setattr(storage, "list", list_)
    monkeypatch.setattr(storage, "head", head)
    monkeypatch.setattr(storage, "get", get)


def _depth(node) -> int:
    return 1 + max((_depth(f) for f in node["folders"]), default=0)


@pytest.fixture
def storage(client):
    return client.app.state.storage


@pytest.fixture(params=[300, 1000])
def deep(request) -> str:
    """A 300-segment path (the adopter report) and a 1000-segment one, which made
    /api/tree answer 500 with RecursionError before the fix."""
    return "/".join(["a"] * request.param)


def test_folder_json_under_a_300_segment_prefix_does_not_break_the_tree(client, storage, settings, monkeypatch, deep):
    _overlay(monkeypatch, storage, {
        f"viz/charts/{deep}/_folder.json": b'{"schema_version": 1}',
        f"viz/dashboards/{deep}/_folder.json": b'{"schema_version": 1}',
    })
    r = client.get("/api/tree")
    assert r.status_code == 200
    tree = build_tree(storage, settings)
    assert _depth(tree["charts"]) < 10
    assert _depth(tree["dashboards"]) < 10
    assert any(f["name"] == "sales" for f in tree["charts"]["folders"])


def test_invalid_deep_item_ids_are_error_nodes_at_the_root(client, storage, settings, monkeypatch, deep):
    _overlay(monkeypatch, storage, {
        f"viz/charts/{deep}/chart.json": b"{}",
        f"viz/dashboards/{deep}.json": b"{}",
    })
    r = client.get("/api/tree")
    assert r.status_code == 200
    tree = build_tree(storage, settings)
    for kind in ("charts", "dashboards"):
        root = tree[kind]
        assert _depth(root) < 10
        node = next(i for i in root["items"] if i["id"] == deep)
        assert node["error"] == "invalid id"
