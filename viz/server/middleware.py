"""Security headers on every response, and the identity slot."""
import logging
import time

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

CSP = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
    "connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}

access_log = logging.getLogger("viz.access")
error_log = logging.getLogger("viz.server")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Outermost middleware: every response leaving the app carries these headers,
    including ones rejected by TrustedHost and ones from an unhandled exception."""

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            error_log.exception("unhandled error on %s %s", request.method, request.url.path)
            response = JSONResponse({"detail": "internal server error"}, status_code=500)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response


class IdentityMiddleware(BaseHTTPMiddleware):
    """Reads the identity header set by an upstream SSO proxy. No-op without one.

    This is the auth slot: a real deployment puts the site behind a proxy that
    sets the header, and this middleware records it. Nothing here enforces.
    """

    def __init__(self, app, header: str):
        super().__init__(app)
        self.header = header

    async def dispatch(self, request: Request, call_next):
        user = request.headers.get(self.header) or None
        request.state.user = user
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            access_log.info(
                "user=%s method=%s path=%s status=%s ms=%.1f",
                user or "-", request.method, request.url.path, 500, elapsed_ms,
            )
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        access_log.info(
            "user=%s method=%s path=%s status=%s ms=%.1f",
            user or "-", request.method, request.url.path, response.status_code, elapsed_ms,
        )
        return response
