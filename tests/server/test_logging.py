"""A2: viz-server must actually write the viz.access lines (user, method, path, status)."""
import subprocess
import sys

from viz.server import __main__ as server_main

# Runs in a fresh interpreter so the logging configuration does not leak into other tests.
SCRIPT = """
import logging.config
import sys
from fastapi.testclient import TestClient
from viz.config import Settings
from viz.server.__main__ import log_config
from viz.server.app import create_app

logging.config.dictConfig(log_config())
settings = Settings(storage="local", local_dir=sys.argv[1], web_dist=sys.argv[1], allowed_hosts="testserver")
client = TestClient(create_app(settings))
client.get("/api/health", headers={"X-Forwarded-Email": "someone@example.com"})
logging.getLogger("viz.server").debug("debug lines stay hidden")
"""


def test_log_config_sends_viz_to_stderr_at_info():
    config = server_main.log_config()
    assert config["loggers"]["viz"] == {"handlers": ["viz"], "level": "INFO", "propagate": False}
    assert config["handlers"]["viz"]["stream"] == "ext://sys.stderr"
    assert "uvicorn" in config["loggers"], "uvicorn's own loggers must stay configured"


def test_main_passes_the_log_config_to_uvicorn(monkeypatch):
    calls = []
    monkeypatch.setattr(server_main.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    server_main.main([])
    assert calls[0]["log_config"] == server_main.log_config()
    assert calls[0]["factory"] is True


def test_access_lines_are_written_when_configured(tmp_path):
    result = subprocess.run([sys.executable, "-c", SCRIPT, str(tmp_path)], capture_output=True, text=True,
                            timeout=120)
    assert result.returncode == 0, result.stderr
    access = [line for line in result.stderr.splitlines() if " viz.access " in line]
    assert len(access) == 1, result.stderr
    assert "INFO" in access[0]
    assert "user=someone@example.com method=GET path=/api/health status=200" in access[0]
    assert "debug lines stay hidden" not in result.stderr
