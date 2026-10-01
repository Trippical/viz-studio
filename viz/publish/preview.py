"""viz preview: the unchanged read-only server pointed at the staging directory, on loopback.
It never reads VIZ_STORAGE; the staging directory is the bucket, with an empty root prefix."""
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from ..config import Settings
from ..server.app import create_app

LOOPBACK = ("127.0.0.1", "localhost", "::1")
LOOPBACK_ALLOWED_HOSTS = "localhost,127.0.0.1"


class PreviewError(ValueError):
    pass


def _allowed_hosts(host: str, allowed_hosts: str | None) -> str:
    """A host other than loopback shows staged, unpublished data to the network, so it
    needs an explicit Host allow-list (finding A23)."""
    if allowed_hosts:
        return allowed_hosts
    if host in LOOPBACK:
        return LOOPBACK_ALLOWED_HOSTS
    raise PreviewError(
        f"--host {host} makes the preview reachable from other machines; "
        "ask the user before passing --allowed-hosts with the host names viewers will use"
    )


def preview_settings(staging_root: Path, host: str = "127.0.0.1", port: int = 8000,
                     allowed_hosts: str | None = None) -> Settings:
    allowed = _allowed_hosts(host, allowed_hosts)
    return Settings(storage="local", local_dir=Path(staging_root), root_prefix="", allowed_hosts=allowed,
                    host=host, port=port, require_identity=False)


def build_preview_app(staging_root: Path, host: str = "127.0.0.1", port: int = 8000,
                      allowed_hosts: str | None = None) -> FastAPI:
    return create_app(preview_settings(staging_root, host, port, allowed_hosts))


def run_preview(staging_root: Path, host: str = "127.0.0.1", port: int = 8000,
                allowed_hosts: str | None = None) -> None:
    settings = preview_settings(staging_root, host, port, allowed_hosts)
    print(f"previewing {settings.local_dir} on http://{host}:{port}")
    uvicorn.run(create_app(settings), host=host, port=port)
