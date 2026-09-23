from fastapi.testclient import TestClient

from viz.server.app import create_app
from viz.server.middleware import CSP


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_security_headers_on_every_response(client):
    r = client.get("/api/health")
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cross-origin-resource-policy"] == "same-origin"
    assert r.headers["referrer-policy"] == "same-origin"
    assert r.headers["x-frame-options"] == "DENY"


def test_csp_exact_value():
    assert CSP == (
        "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
        "connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )


def test_untrusted_host_is_rejected(settings):
    app = create_app(settings)
    with TestClient(app, base_url="http://evil.example") as c:
        r = c.get("/api/health")
    assert r.status_code == 400


def test_no_cors_headers(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_identity_header_is_logged(client, caplog):
    with caplog.at_level("INFO", logger="viz.access"):
        client.get("/api/health", headers={"X-Forwarded-Email": "someone@example.com"})
    assert any("user=someone@example.com" in rec.getMessage() for rec in caplog.records)


def test_missing_identity_logs_anonymous(client, caplog):
    with caplog.at_level("INFO", logger="viz.access"):
        client.get("/api/health")
    assert any("user=-" in rec.getMessage() for rec in caplog.records)


def test_untrusted_host_response_still_has_security_headers(settings):
    app = create_app(settings)
    with TestClient(app, base_url="http://evil.example") as c:
        r = c.get("/api/health")
    assert r.status_code == 400
    assert r.headers["content-security-policy"] == CSP


def test_crash_gets_headers_and_access_log(settings, caplog):
    app = create_app(settings)

    @app.get("/api/boom")
    def boom():
        raise RuntimeError("boom")

    with caplog.at_level("INFO", logger="viz.access"):
        r = TestClient(app, raise_server_exceptions=False).get("/api/boom")
    assert r.status_code == 500
    assert r.json() == {"detail": "internal server error"}
    assert r.headers["content-security-policy"] == CSP
    assert any("status=500" in rec.getMessage() and "path=/api/boom" in rec.getMessage() for rec in caplog.records)
