# tests/test_web_assets.py
"""Pins the self-hosted DuckDB parquet extension to an exact, known build.

Finding M8 (final review, plan 2): the extension is fetched once and
committed under web/public/duckdb rather than downloaded at runtime, so a
silent swap of that file (a bad re-pin, a merge mistake) would ship a
different WASM binary to every viewer with no test noticing. This test pins
its exact size and hash so any change is caught here instead of in
production.
"""
import hashlib
from pathlib import Path

EXTENSION_PATH = (
    Path(__file__).resolve().parents[1]
    / "web"
    / "public"
    / "duckdb"
    / "v1.4.3"
    / "wasm_eh"
    / "parquet.duckdb_extension.wasm"
)

EXPECTED_SIZE = 3045039
EXPECTED_SHA256 = "22765c8f7dc741cda2b571a66ac7bb355295d7d69a6c37e5315b265672984f55"


def test_duckdb_parquet_extension_is_pinned():
    assert EXTENSION_PATH.is_file(), EXTENSION_PATH
    data = EXTENSION_PATH.read_bytes()
    assert len(data) == EXPECTED_SIZE
    assert hashlib.sha256(data).hexdigest() == EXPECTED_SHA256
