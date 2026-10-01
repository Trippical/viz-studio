from fastapi.testclient import TestClient

from viz.config import Settings
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
        r = c.get("/api/tree")
    assert r.status_code == 400


def test_health_is_answered_for_any_host(settings):
    # A load balancer health check sends the pod IP as Host (A29), with GET or HEAD.
    with TestClient(create_app(settings), base_url="http://10.1.2.3:8000") as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
        assert r.headers["content-security-policy"] == CSP
        head = c.head("/api/health")
        assert head.status_code == 200
        assert head.headers["content-security-policy"] == CSP
        assert c.get("/api/tree").status_code == 400
        assert c.get("/api/health/").status_code == 400
        assert c.get("/api/healthz").status_code == 400
        assert c.post("/api/health").status_code == 400
        assert c.get("/").status_code == 400


def test_head_health_is_answered_on_an_allowed_host(client):
    r = client.head("/api/health")
    assert r.status_code == 200
    assert r.content == b""


def test_default_allowed_hosts_do_not_include_the_test_client_host(bucket, monkeypatch):
    monkeypatch.delenv("VIZ_ALLOWED_HOSTS", raising=False)
    settings = Settings(storage="local", local_dir=bucket, web_dist=bucket / "no-web-dist")
    assert "testserver" not in settings.allowed_hosts_list
    assert TestClient(create_app(settings)).get("/api/tree").status_code == 400
    assert TestClient(create_app(settings), base_url="http://localhost").get("/api/tree").status_code == 200


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
        r = c.get("/api/tree")
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
