"""FastAPI application factory."""
from fastapi import FastAPI

from ..config import Settings
from ..storage import get_storage
from .middleware import IdentityMiddleware, SecurityHeadersMiddleware, TrustedHostExceptHealth
from .routes import router
from .static import mount_spa
from .tree import TreeCache


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    storage = get_storage(settings)

    app = FastAPI(title="viz-site", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.storage = storage
    app.state.tree = TreeCache(storage, settings)

    # Last added runs outermost. Order: SecurityHeaders -> TrustedHost -> Identity -> routes.
    # SecurityHeaders is outermost so every response leaving the app carries the
    # headers, including ones rejected by TrustedHost (400) and ones from an
    # unhandled exception in the router. The Host check skips GET and HEAD /api/health only.
    app.add_middleware(IdentityMiddleware, header=settings.auth_header, require=settings.require_identity)
    app.add_middleware(TrustedHostExceptHealth, allowed_hosts=settings.allowed_hosts_list)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(router, prefix="/api")
    mount_spa(app, settings.web_dist)
    return app
