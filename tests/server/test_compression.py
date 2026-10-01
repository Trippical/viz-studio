"""Finding A11: hashed assets are cached for a year, responses over 1 KB are
gzipped; data files, .wasm files and everything under /duckdb/ never are."""
from fastapi.testclient import TestClient

from viz.server.app import create_app
from viz.server.compression import GZIP_MINIMUM_BYTES, IMMUTABLE, is_never_compressed

GZIP = {"Accept-Encoding": "gzip"}
BIG_JS = "console.log('viz');\n" * 200
WASM = b"\x00asm\x01\x00\x00\x00" + b"\x00" * 4096


def _dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>viz</title>" + "<!-- pad -->" * 200, encoding="utf-8")
    (dist / "assets" / "app-3f2a1b.js").write_text(BIG_JS, encoding="utf-8", newline="")
    (dist / "assets" / "tiny-9c8d7e.js").write_text("1", encoding="utf-8")
    (dist / "assets" / "duckdb-eh-1a2b3c.wasm").write_bytes(WASM)
    extension = dist / "duckdb" / "v1.4.3" / "wasm_eh"
    extension.mkdir(parents=True)
    (extension / "parquet.duckdb_extension.wasm").write_bytes(WASM)
    (extension / "notes.txt").write_text("duckdb " * 400, encoding="utf-8")
    return dist


def _client(settings, tmp_path):
    settings.web_dist = _dist(tmp_path)
    return TestClient(create_app(settings))


def test_constants():
    assert IMMUTABLE == "public, max-age=31536000, immutable"
    assert GZIP_MINIMUM_BYTES == 1024


def test_hashed_assets_are_immutable(settings, tmp_path):
    client = _client(settings, tmp_path)
    for path in ("/assets/app-3f2a1b.js", "/assets/tiny-9c8d7e.js", "/assets/duckdb-eh-1a2b3c.wasm"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == IMMUTABLE, path


def test_index_html_is_not_immutable(settings, tmp_path):
    client = _client(settings, tmp_path)
    for path in ("/", "/d/sales/overview"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "immutable" not in r.headers.get("cache-control", ""), path


def test_responses_over_one_kilobyte_are_gzipped(settings, tmp_path):
    client = _client(settings, tmp_path)
    r = client.get("/assets/app-3f2a1b.js", headers=GZIP)
    assert r.headers["content-encoding"] == "gzip"
    assert r.text == BIG_JS
    assert r.headers["cache-control"] == IMMUTABLE
    r = client.get("/api/tree", headers=GZIP)
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "gzip"
    assert r.headers["content-security-policy"]


def test_never_compressed_paths():
    for path in ("/api/data/sales/x", "/duckdb/v1.4.3/wasm_eh/parquet.duckdb_extension.wasm",
                 "/duckdb/v1.4.3/wasm_eh/notes.txt", "/assets/duckdb-eh-1a2b3c.wasm"):
        assert is_never_compressed(path), path
    for path in ("/assets/app-3f2a1b.js", "/api/tree", "/", "/d/sales/overview", "/api/dataset"):
        assert not is_never_compressed(path), path


def test_wasm_and_duckdb_files_are_never_gzipped(settings, tmp_path):
    client = _client(settings, tmp_path)
    r = client.get("/assets/duckdb-eh-1a2b3c.wasm", headers=GZIP)
    assert r.status_code == 200
    assert "content-encoding" not in r.headers
    assert r.headers["content-type"] == "application/wasm"
    assert r.headers["cache-control"] == IMMUTABLE
    assert r.content == WASM
    for path in ("/duckdb/v1.4.3/wasm_eh/parquet.duckdb_extension.wasm", "/duckdb/v1.4.3/wasm_eh/notes.txt"):
        r = client.get(path, headers=GZIP)
        assert r.status_code == 200, path
        assert "content-encoding" not in r.headers, path
        assert int(r.headers["content-length"]) > GZIP_MINIMUM_BYTES, path
        assert int(r.headers["content-length"]) == len(r.content), path


def test_small_responses_are_not_gzipped(settings, tmp_path):
    client = _client(settings, tmp_path)
    r = client.get("/assets/tiny-9c8d7e.js", headers=GZIP)
    assert "content-encoding" not in r.headers
    r = client.get("/api/health", headers=GZIP)
    assert "content-encoding" not in r.headers


def test_data_files_are_never_gzipped(settings, tmp_path):
    client = _client(settings, tmp_path)
    for chart_id in ("bakeoff/vega-lite/time-series", "bakeoff/vega-lite/order-lines"):
        r = client.get(f"/api/data/{chart_id}", headers=GZIP)
        assert r.status_code == 200, chart_id
        assert "content-encoding" not in r.headers, chart_id
        assert int(r.headers["content-length"]) == len(r.content), chart_id
        assert int(r.headers["content-length"]) > GZIP_MINIMUM_BYTES, chart_id
