"""Security headers on every response, and the identity slot."""
import logging
import time

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

HEALTH_PATH = "/api/health"
# Load balancers and kubelet probes use GET; some load balancers use HEAD.
HEALTH_METHODS = ("GET", "HEAD")

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


class TrustedHostExceptHealth:
    """The Host allow-list for every request except GET and HEAD /api/health.

    Load balancer health checks (for example an AWS ALB in IP mode) send the pod IP as
    the Host header, which is never in the allow-list. The health route returns a
    constant and reads nothing, so it is answered before the Host check. Every other
    path, including /api/health with any other method, goes through TrustedHostMiddleware.
    """

    def __init__(self, app: ASGIApp, allowed_hosts: list[str]):
        self.app = app
        self.checked = TrustedHostMiddleware(app, allowed_hosts=allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] == "http" and scope.get("method") in HEALTH_METHODS
                and scope.get("path") == HEALTH_PATH):
            await self.app(scope, receive, send)
            return
        await self.checked(scope, receive, send)


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
