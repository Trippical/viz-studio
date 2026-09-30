"""Response compression and long-lived caching for hashed front-end assets (finding A11)."""
import os

from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

IMMUTABLE = "public, max-age=31536000, immutable"
GZIP_MINIMUM_BYTES = 1024
GZIP_LEVEL = 6
# Served byte for byte, never gzipped (decided by the lead, plan 5c):
# /api/data/: the client checks Content-Length against the lane caps, Range
#   requests must keep working, and parquet is already compressed;
# /duckdb/ and *.wasm: the DuckDB module and its self-hosted extension, which
#   DuckDB-WASM fetches itself; compressing 34 MB per cold load costs CPU.
UNCOMPRESSED_PREFIXES = ("/api/data/", "/duckdb/")
UNCOMPRESSED_SUFFIXES = (".wasm",)


def is_never_compressed(path: str) -> bool:
    """True for paths whose responses are always sent uncompressed."""
    return path.startswith(UNCOMPRESSED_PREFIXES) or path.endswith(UNCOMPRESSED_SUFFIXES)


class ImmutableStaticFiles(StaticFiles):
    """StaticFiles for Vite's /assets. Vite names every file there by content
    hash, so a file with a given name never changes and may be cached for a year."""

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = IMMUTABLE
        return response


class CompressionMiddleware:
    """Gzip responses over 1 KB, except the paths is_never_compressed() names:
    data files under /api/data/, everything under /duckdb/, and any .wasm file."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=GZIP_MINIMUM_BYTES, compresslevel=GZIP_LEVEL)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and is_never_compressed(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        await self.gzip(scope, receive, send)
