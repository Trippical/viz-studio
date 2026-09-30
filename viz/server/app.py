"""FastAPI application factory."""
from fastapi import FastAPI

from ..config import Settings
from ..storage import get_storage
from .compression import CompressionMiddleware
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

    # Last added runs outermost. Order: SecurityHeaders -> TrustedHost -> Identity -> Compression -> routes.
    # SecurityHeaders is outermost so every response leaving the app carries the
    # headers, including ones rejected by TrustedHost (400) and ones from an
    # unhandled exception in the router. The Host check skips GET and HEAD /api/health only.
    # Compression is innermost, wrapping the app/routes directly (finding A11): Identity and
    # SecurityHeaders are BaseHTTPMiddleware, which always re-streams a response as one or
    # more "more_body: True" chunks followed by an empty closing chunk. GZipMiddleware reads
    # that shape as an open-ended stream and compresses it unconditionally, so minimum_size
    # stops being honored for every response once Compression sits outside a BaseHTTPMiddleware
    # layer. Placed innermost, Compression sees the real single-message FileResponse/JSONResponse
    # the app produced, decides by their true size, and the compressed bytes and the
    # Content-Encoding/Content-Length headers it sets pass unchanged through the outer layers.
    app.add_middleware(CompressionMiddleware)
    app.add_middleware(IdentityMiddleware, header=settings.auth_header, require=settings.require_identity)
    app.add_middleware(TrustedHostExceptHealth, allowed_hosts=settings.allowed_hosts_list)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(router, prefix="/api")
    mount_spa(app, settings.web_dist)
    return app
