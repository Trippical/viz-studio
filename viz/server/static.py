"""Serve the built front end. Unknown non-API paths fall back to index.html.

Implemented as a 404 exception handler rather than a catch-all route, so
routes registered after create_app() still resolve normally.
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles


def mount_spa(app: FastAPI, dist: Path) -> None:
    dist = Path(dist)
    index = dist / "index.html"
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request: Request, exc: StarletteHTTPException):
        path = request.url.path
        is_api = path == "/api" or path.startswith("/api/")
        if exc.status_code == 404 and request.method in ("GET", "HEAD") and not is_api:
            if not index.is_file():
                return JSONResponse({"detail": "front end not built"}, status_code=404)
            rel = path.lstrip("/")
            if rel:
                candidate = (dist / rel).resolve()
                if candidate.is_file() and dist.resolve() in candidate.parents:
                    return FileResponse(candidate)
            return FileResponse(index)
        return await http_exception_handler(request, exc)
