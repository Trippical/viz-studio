"""Adopter fix A6: viz-server parses its arguments. --help prints and exits 0 without
starting the server; any other argument exits 2. With no arguments (the docker CMD)
it starts as before."""
import subprocess
import sys

import pytest

from viz.server import __main__ as server_main

SERVER_ENV_VARS = [
    "VIZ_STORAGE", "VIZ_LOCAL_DIR", "VIZ_S3_BUCKET", "VIZ_ROOT_PREFIX", "VIZ_HOST", "VIZ_PORT",
    "VIZ_ALLOWED_HOSTS", "VIZ_REQUIRE_IDENTITY", "VIZ_AUTH_HEADER", "VIZ_TREE_TTL_SECONDS",
    "VIZ_MAX_DOCUMENT_BYTES", "VIZ_WEB_DIST",
]


@pytest.fixture
def uvicorn_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(server_main.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    return calls


def test_help_prints_the_env_vars_and_exits_zero(uvicorn_calls, capsys):
    with pytest.raises(SystemExit) as excinfo:
        server_main.main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    for name in SERVER_ENV_VARS:
        assert name in out, name
    assert uvicorn_calls == []


def test_unknown_argument_exits_two(uvicorn_calls, capsys):
    with pytest.raises(SystemExit) as excinfo:
        server_main.main(["--port", "9000"])
    assert excinfo.value.code == 2
    assert "unrecognized arguments: --port 9000" in capsys.readouterr().err
    assert uvicorn_calls == []


def test_no_arguments_starts_the_server(uvicorn_calls):
    server_main.main([])
    assert len(uvicorn_calls) == 1


def test_help_in_a_real_process_does_not_start_the_server():
    result = subprocess.run([sys.executable, "-m", "viz.server", "--help"], capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 0, result.stderr
    assert "VIZ_STORAGE" in result.stdout
    assert "Uvicorn running" not in result.stderr
