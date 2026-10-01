"""CI smoke test for the container image. Standard library only: the docker job
has no project virtualenv.

Usage, from the repo root, with the container listening on port 8000:
    python3 .github/scripts/docker_smoke.py http://localhost:8000

Checks, in order:
1. /api/health answers 200 (retried for up to 30 seconds while the container starts).
2. The self-hosted DuckDB parquet extension is served as WebAssembly. An unknown
   path falls back to index.html with status 200, so a 200 alone proves nothing.
3. /api/tree is JSON and lists at least one dashboard without an error, which
   proves the mounted sample bucket is being read.
"""
import json
import sys
import time
import urllib.error
import urllib.request

EXTENSION_PATH = "/duckdb/v1.4.3/wasm_eh/parquet.duckdb_extension.wasm"
WASM_MAGIC = b"\x00asm"


def fetch(url: str) -> tuple[int, str, bytes]:
    """GET url. Returns (status, content type, body). HTTP error statuses are returned, not raised."""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers.get("Content-Type", ""), err.read()


def is_wasm(content_type: str, body: bytes) -> bool:
    """True when the response is WebAssembly: the application/wasm type or the wasm magic bytes."""
    media_type = content_type.split(";")[0].strip().lower()
    return media_type == "application/wasm" or body[:4] == WASM_MAGIC


def count_dashboards(folder: dict) -> int:
    """Dashboards without an error in a /api/tree folder node and all of its sub-folders."""
    count = 0
    for item in folder.get("items", []):
        if item.get("type") == "dashboard" and not item.get("error"):
            count += 1
    for child in folder.get("folders", []):
        count += count_dashboards(child)
    return count


def wait_for_health(base: str, attempts: int = 30) -> bool:
    for _ in range(attempts):
        try:
            status, _, _ = fetch(base + "/api/health")
        except OSError:
            status = 0
        if status == 200:
            return True
        time.sleep(1)
    return False


def main(argv: list[str]) -> int:
    base = argv[1].rstrip("/")
    if not wait_for_health(base):
        print("FAIL: /api/health never answered 200")
        return 1
    print("ok   /api/health")

    status, content_type, body = fetch(base + EXTENSION_PATH)
    if status != 200 or not is_wasm(content_type, body):
        print(f"FAIL: {EXTENSION_PATH} is not WebAssembly "
              f"(status {status}, Content-Type {content_type!r}, first bytes {body[:16]!r})")
        return 1
    print(f"ok   {EXTENSION_PATH}: {len(body)} bytes, Content-Type {content_type!r}")

    status, content_type, body = fetch(base + "/api/tree")
    if status != 200 or not content_type.startswith("application/json"):
        print(f"FAIL: /api/tree answered status {status} with Content-Type {content_type!r}")
        return 1
    dashboards = count_dashboards(json.loads(body)["dashboards"])
    if dashboards < 1:
        print("FAIL: /api/tree lists no dashboards; is the sample bucket mounted at VIZ_LOCAL_DIR?")
        return 1
    print(f"ok   /api/tree lists {dashboards} dashboards")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
