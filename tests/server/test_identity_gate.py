"""B1: with VIZ_REQUIRE_IDENTITY on, requests without the SSO proxy's identity header get 401."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from viz.config import Settings
from viz.publish.preview import preview_settings
from viz.server.app import create_app
from viz.server.middleware import CSP

EMAIL = {"X-Forwarded-Email": "someone@example.com"}
VIZ_PACKAGE = Path(__file__).resolve().parents[2] / "viz"


@pytest.fixture
def gated(settings) -> TestClient:
    settings.require_identity = True
    return TestClient(create_app(settings))


def test_setting_defaults_to_off_and_reads_the_environment(monkeypatch):
    monkeypatch.delenv("VIZ_REQUIRE_IDENTITY", raising=False)
    assert Settings().require_identity is False
    monkeypatch.setenv("VIZ_REQUIRE_IDENTITY", "true")
    assert Settings().require_identity is True


def test_off_by_default_requests_without_identity_are_served(client):
    assert client.get("/api/tree").status_code == 200


def test_missing_identity_is_401(gated):
    r = gated.get("/api/tree")
    assert r.status_code == 401
    assert r.json() == {"detail": "identity header required"}
    assert r.headers["content-security-policy"] == CSP


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_identity_is_401(gated, value):
    assert gated.get("/api/tree", headers={"X-Forwarded-Email": value}).status_code == 401


@pytest.mark.parametrize("path", [
    "/api/tree", "/api/charts/sales/revenue-by-region", "/api/dashboards/sales/overview",
    "/api/data/sales/revenue-by-region", "/", "/d/sales/overview", "/api/nothing",
])
def test_every_path_needs_identity(gated, path):
    assert gated.get(path).status_code == 401


def test_identity_present_is_served(gated):
    assert gated.get("/api/tree", headers=EMAIL).status_code == 200
    assert gated.get("/api/data/sales/revenue-by-region", headers=EMAIL).status_code == 200


def test_health_needs_no_identity(gated):
    r = gated.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert gated.head("/api/health").status_code == 200


def test_other_methods_on_health_need_identity(gated):
    assert gated.post("/api/health").status_code == 401


def test_health_from_a_load_balancer_needs_neither_host_nor_identity(settings):
    settings.require_identity = True
    with TestClient(create_app(settings), base_url="http://10.1.2.3:8000") as c:
        assert c.get("/api/health").status_code == 200
        assert c.head("/api/health").status_code == 200


def test_the_header_name_is_the_auth_header_setting(settings):
    settings.require_identity = True
    settings.auth_header = "X-Auth-Request-Email"
    c = TestClient(create_app(settings))
    assert c.get("/api/tree", headers=EMAIL).status_code == 401
    assert c.get("/api/tree", headers={"X-Auth-Request-Email": "a@example.com"}).status_code == 200


def test_rejected_request_is_logged(gated, caplog):
    with caplog.at_level("INFO", logger="viz.access"):
        gated.get("/api/tree")
    assert any("user=-" in rec.getMessage() and "status=401" in rec.getMessage() for rec in caplog.records)


def test_preview_never_requires_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("VIZ_REQUIRE_IDENTITY", "true")
    assert preview_settings(tmp_path).require_identity is False


def test_no_code_calls_the_identity_middleware_an_auth_slot():
    for path in sorted(VIZ_PACKAGE.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        assert "auth slot" not in text, path
        assert "identity slot" not in text, path
        assert "nothing here enforces" not in text, path
