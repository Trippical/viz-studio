"""`viz-refresh` or `python -m viz.refresh`: print the refresh plan and exit. Runs nothing."""
import logging
import sys

from ..config import Settings
from ..storage import get_storage
from . import plan


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = Settings()
    items = plan(settings, get_storage(settings))
    for item in items:
        print(f"{item['id']}\tschedule={item['schedule'] or '-'}\twarehouse={item['warehouse_id'] or '-'}")
    print(f"{len(items)} refreshable chart(s); v1 does not run refreshes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
