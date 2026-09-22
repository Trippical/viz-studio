import asyncio
import json
import sys

import pytest

from viz.server.tree import TreeCache, build_tree
from viz.storage import get_storage


@pytest.fixture
def storage(settings):
    return get_storage(settings)


def _find_folder(node, name):
    return next(f for f in node["folders"] if f["name"] == name)


def test_tree_shape(storage, settings):
    tree = build_tree(storage, settings)
    assert set(tree) == {"charts", "dashboards", "built_at"}
    sales = _find_folder(tree["charts"], "sales")
    assert sales["path"] == "sales"
    assert sales["title"] == "Sales"
    assert sales["order"] == 10
    ids = sorted(item["id"] for item in sales["items"])
    assert ids == ["sales/revenue-by-region", "sales/total-revenue"]
    chart = next(i for i in sales["items"] if i["id"] == "sales/total-revenue")
    assert chart["type"] == "chart"
    assert chart["renderer"] == "stat"
    assert chart["lane"] == "small"
    assert chart["static"] is True
    refreshable = next(i for i in sales["items"] if i["id"] == "sales/revenue-by-region")
    assert refreshable["static"] is False


def test_dashboard_node_carries_controls(storage, settings):
    tree = build_tree(storage, settings)
    sales = _find_folder(tree["dashboards"], "sales")
    dash = sales["items"][0]
    assert dash["type"] == "dashboard"
    assert dash["id"] == "sales/overview"
    assert [c["id"] for c in dash["controls"]] == ["period", "region"]


def test_folder_without_metadata_uses_slug(storage, settings):
    storage.put("viz/charts/misc/deep/thing/chart.json", b"{}", "application/json")
    tree = build_tree(storage, settings)
    misc = _find_folder(tree["charts"], "misc")
    assert misc["title"] is None
    assert misc["name"] == "misc"
    deep = _find_folder(misc, "deep")
    assert deep["items"][0]["id"] == "misc/deep/thing"
    assert "error" in deep["items"][0]


def test_folder_sorting_order_then_name(storage, settings):
    storage.put("viz/charts/zeta/_folder.json", json.dumps({"schema_version": 1, "order": 1}).encode(), "application/json")
    storage.put("viz/charts/alpha/x/chart.json", b"{}", "application/json")
    tree = build_tree(storage, settings)
    names = [f["name"] for f in tree["charts"]["folders"]]
    assert names == ["zeta", "sales", "alpha"]  # order 1, order 10, then unordered by name


def test_invalid_chart_becomes_error_node(storage, settings):
    storage.put("viz/charts/sales/bad/chart.json", b"{not json", "application/json")
    tree = build_tree(storage, settings)
    sales = _find_folder(tree["charts"], "sales")
    bad = next(i for i in sales["items"] if i["id"] == "sales/bad")
    assert "invalid JSON" in bad["error"]


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="NTFS is case-insensitive: writing 'Sales/chart.json' lands in the "
    "existing 'sales' directory instead of creating a distinct entry",
)
def test_invalid_id_becomes_error_node(storage, settings):
    storage.put("viz/charts/Sales/chart.json", b"{}", "application/json")
    tree = build_tree(storage, settings)
    bad = next(i for i in tree["charts"]["items"] if i["id"] == "Sales")
    assert "invalid id" in bad["error"]


def test_prefix_conflict_marks_both(storage, settings):
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc["id"] = "sales"
    storage.put("viz/charts/sales/chart.json", json.dumps(doc).encode(), "application/json")
    tree = build_tree(storage, settings)
    top = next(i for i in tree["charts"]["items"] if i["id"] == "sales")
    assert "conflicts" in top["error"]
    sales = _find_folder(tree["charts"], "sales")
    child = next(i for i in sales["items"] if i["id"] == "sales/total-revenue")
    assert "conflicts" in child["error"]


async def test_cache_builds_once_and_refreshes_in_background(storage, settings):
    settings.tree_ttl_seconds = 0
    cache = TreeCache(storage, settings)
    first = await cache.get()
    assert cache.builds == 1
    second = await cache.get()          # stale: returns old value, kicks off one refresh
    assert second is first
    await asyncio.sleep(0.2)
    assert cache.builds == 2
    third = await cache.get()
    assert third is not first


async def test_cache_single_flight_on_cold_start(storage, settings):
    cache = TreeCache(storage, settings)
    results = await asyncio.gather(*(cache.get() for _ in range(5)))
    assert cache.builds == 1
    assert all(r is results[0] for r in results)


async def test_cache_invalidate(storage, settings):
    cache = TreeCache(storage, settings)
    await cache.get()
    cache.invalidate()
    await cache.get()
    assert cache.builds == 2
