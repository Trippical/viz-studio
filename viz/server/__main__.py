"""Run the server: `python -m viz.server` or `viz-server`."""
import argparse
import copy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from ..config import Settings

VIZ_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def log_config() -> dict:
    """uvicorn's own logging config plus the `viz` logger at INFO on stderr.

    Without this the root logger stays at WARNING and the viz.access lines
    (user, method, path, status per request) are never written."""
    config = copy.deepcopy(LOGGING_CONFIG)
    config["formatters"]["viz"] = {"format": VIZ_LOG_FORMAT}
    config["handlers"]["viz"] = {"class": "logging.StreamHandler", "formatter": "viz", "stream": "ext://sys.stderr"}
    config["loggers"]["viz"] = {"handlers": ["viz"], "level": "INFO", "propagate": False}
    return config


DESCRIPTION = """Serve the viz site (read-only API and web front end).

viz-server takes no options; it is configured only by environment variables:
  VIZ_STORAGE             local (default) or s3
  VIZ_LOCAL_DIR           folder used when VIZ_STORAGE=local (default ./sample-bucket)
  VIZ_S3_BUCKET           bucket used when VIZ_STORAGE=s3
  VIZ_ROOT_PREFIX         key prefix inside the bucket or folder (default viz/)
  VIZ_HOST                address to listen on (default 127.0.0.1)
  VIZ_PORT                port to listen on (default 8000)
  VIZ_ALLOWED_HOSTS       comma-separated Host header values to accept (default localhost,127.0.0.1)
  VIZ_REQUIRE_IDENTITY    true: every request except /api/health needs the identity header (default false)
  VIZ_AUTH_HEADER         the identity header set by the SSO proxy (default X-Forwarded-Email)
  VIZ_TREE_TTL_SECONDS    seconds before the folder tree is rebuilt (default 60)
  VIZ_MAX_DOCUMENT_BYTES  largest chart or dashboard document served (default 1048576)
  VIZ_WEB_DIST            the built front end (default ./web/dist)
"""


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """--help prints DESCRIPTION and exits 0; any other argument exits 2."""
    parser = argparse.ArgumentParser(prog="viz-server", description=DESCRIPTION,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    parse_args(argv)
    settings = Settings()
    uvicorn.run("viz.server.app:create_app", factory=True, host=settings.host, port=settings.port,
                log_config=log_config())


if __name__ == "__main__":
    main()
