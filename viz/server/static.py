"""Serve the built front end. Unknown non-API paths fall back to index.html.

Implemented as a 404 exception handler rather than a catch-all route, so
routes registered after create_app() still resolve normally.
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .compression import ImmutableStaticFiles


def mount_spa(app: FastAPI, dist: Path) -> None:
    dist = Path(dist)
    index = dist / "index.html"
    assets = dist / "assets"
    # Mount /assets unconditionally: viz-server can start before `vite build`
    # has run (e.g. under Playwright's webServer, which starts before its
    # globalSetup builds the front end). check_dir=False lets StaticFiles
    # mount against a directory that does not exist yet; files that appear
    # under it later are served normally once they exist.
    app.mount("/assets", ImmutableStaticFiles(directory=assets, check_dir=False), name="assets")

    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request: Request, exc: StarletteHTTPException):
        path = request.url.path
        is_api = path == "/api" or path.startswith("/api/")
        is_assets = path == "/assets" or path.startswith("/assets/")
        if exc.status_code == 404 and request.method in ("GET", "HEAD") and not is_api and not is_assets:
            if not index.is_file():
                return JSONResponse({"detail": "front end not built"}, status_code=404)
            rel = path.lstrip("/")
            if rel:
                candidate = (dist / rel).resolve()
                if candidate.is_file() and dist.resolve() in candidate.parents:
                    return FileResponse(candidate)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return await http_exception_handler(request, exc)
