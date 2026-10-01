"""Refresher scaffold (spec section 7). v1 only lists what a refresher would run.
The v2 spec defines execution, overwrite semantics, failure handling and concurrency;
it must honour spec section 12.7. Nothing here connects to Databricks."""
import logging

from .. import strict_json
from ..config import Settings
from ..schemas import SchemaError, validate_chart
from ..storage import Storage

log = logging.getLogger("viz.refresh")


def plan(settings: Settings, storage: Storage) -> list[dict]:
    """Every published chart with a `source` block, with its schedule. Invalid charts are skipped."""
    prefix = f"{settings.root_prefix}charts/"
    items = []
    for info in storage.list(prefix):
        if not info.key.endswith("/chart.json"):
            continue
        try:
            doc = validate_chart(strict_json.loads(storage.get(info.key)))
        except (ValueError, SchemaError) as err:
            log.warning("skipping %s: %s", info.key, err)
            continue
        source = doc.get("source")
        if not source:
            continue
        items.append({"id": doc["id"], "schedule": source.get("schedule"), "warehouse_id": source.get("warehouse_id")})
    return sorted(items, key=lambda item: item["id"])
