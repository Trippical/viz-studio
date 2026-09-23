"""viz preview: the unchanged read-only server pointed at the staging directory, on loopback.
It never reads VIZ_STORAGE; the staging directory is the bucket, with an empty root prefix."""
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from ..config import Settings
from ..server.app import create_app

LOOPBACK = ("127.0.0.1", "localhost", "::1")


def preview_settings(staging_root: Path, host: str = "127.0.0.1", port: int = 8000) -> Settings:
    allowed = "localhost,127.0.0.1" if host in LOOPBACK else "*"
    return Settings(storage="local", local_dir=Path(staging_root), root_prefix="", allowed_hosts=allowed,
                    host=host, port=port)


def build_preview_app(staging_root: Path, host: str = "127.0.0.1", port: int = 8000) -> FastAPI:
    return create_app(preview_settings(staging_root, host, port))


def run_preview(staging_root: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    settings = preview_settings(staging_root, host, port)
    print(f"previewing {settings.local_dir} on http://{host}:{port}")
    uvicorn.run(create_app(settings), host=host, port=port)
