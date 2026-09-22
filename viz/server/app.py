"""FastAPI application factory."""
from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..config import Settings
from ..storage import get_storage
from .middleware import IdentityMiddleware, SecurityHeadersMiddleware
from .routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    storage = get_storage(settings)

    app = FastAPI(title="viz-site", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.storage = storage

    # Last added runs outermost. Order: SecurityHeaders -> TrustedHost -> Identity -> routes.
    # SecurityHeaders is outermost so every response leaving the app carries the
    # headers, including ones rejected by TrustedHost (400) and ones from an
    # unhandled exception in the router.
    app.add_middleware(IdentityMiddleware, header=settings.auth_header)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(router, prefix="/api")
    return app
