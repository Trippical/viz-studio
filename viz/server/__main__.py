"""Run the server: `python -m viz.server` or `viz-server`."""
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


def main() -> None:
    settings = Settings()
    uvicorn.run("viz.server.app:create_app", factory=True, host=settings.host, port=settings.port,
                log_config=log_config())


if __name__ == "__main__":
    main()
