"""The CI docker smoke script. It must fail when the wasm request falls back to
index.html and when the folder tree has no dashboards (finding A27)."""
import importlib.util
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from viz.config import Settings
from viz.server.app import create_app

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / ".github" / "scripts" / "docker_smoke.py"
SAMPLE = REPO / "sample-bucket"
WASM = REPO / "web" / "public" / "duckdb" / "v1.4.3" / "wasm_eh" / "parquet.duckdb_extension.wasm"
BASE = "http://localhost:8000"


@pytest.fixture
def smoke():
    spec = importlib.util.spec_from_file_location("docker_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dist(tmp_path: Path, with_wasm: bool) -> Path:
    """A minimal built front end: index.html, and optionally the self-hosted extension."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>viz</title>", encoding="utf-8")
    if with_wasm:
        target = dist / "duckdb" / "v1.4.3" / "wasm_eh" / "parquet.duckdb_extension.wasm"
        target.parent.mkdir(parents=True)
        shutil.copyfile(WASM, target)
    return dist


def _fetch_via(dist: Path, bucket: Path):
    """A stand-in for docker_smoke.fetch that asks the real app through TestClient."""
    settings = Settings(storage="local", local_dir=bucket, root_prefix="viz/", web_dist=dist,
                        allowed_hosts="testserver")
    client = TestClient(create_app(settings))

    def fetch(url: str):
        response = client.get(url.removeprefix(BASE))
        return response.status_code, response.headers.get("content-type", ""), response.content

    return fetch


def test_extension_path_matches_the_shipped_file(smoke):
    assert (REPO / "web" / "public" / smoke.EXTENSION_PATH.lstrip("/")).is_file()


def test_is_wasm_accepts_the_real_extension(smoke):
    assert smoke.is_wasm("application/octet-stream", WASM.read_bytes()[:64])
    assert smoke.is_wasm("application/wasm", b"\x00asm\x01\x00\x00\x00")


def test_is_wasm_rejects_the_spa_fallback(smoke):
    assert not smoke.is_wasm("text/html; charset=utf-8", b"<!doctype html><title>viz</title>")


def test_count_dashboards_walks_nested_folders_and_skips_errors(smoke):
    tree = {
        "items": [{"type": "dashboard", "id": "a", "error": None}],
        "folders": [{
            "items": [
                {"type": "dashboard", "id": "b/c"},
                {"type": "dashboard", "id": "b/d", "error": "not found"},
                {"type": "chart", "id": "b/e"},
            ],
            "folders": [],
        }],
    }
    assert smoke.count_dashboards(tree) == 2


def test_main_passes_against_the_real_app_and_sample_bucket(smoke, tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "fetch", _fetch_via(_dist(tmp_path, with_wasm=True), SAMPLE))
    assert smoke.main(["docker_smoke.py", BASE]) == 0


def test_main_fails_when_the_wasm_falls_back_to_index_html(smoke, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(smoke, "fetch", _fetch_via(_dist(tmp_path, with_wasm=False), SAMPLE))
    assert smoke.main(["docker_smoke.py", BASE]) == 1
    assert "is not WebAssembly" in capsys.readouterr().out


def test_main_fails_on_an_empty_bucket(smoke, tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty"
    (empty / "viz" / "charts").mkdir(parents=True)
    (empty / "viz" / "dashboards").mkdir(parents=True)
    monkeypatch.setattr(smoke, "fetch", _fetch_via(_dist(tmp_path, with_wasm=True), empty))
    assert smoke.main(["docker_smoke.py", BASE]) == 1
    assert "lists no dashboards" in capsys.readouterr().out
