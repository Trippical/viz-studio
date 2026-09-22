from fastapi.testclient import TestClient

from viz.server.app import create_app


def test_no_dist_returns_404_json(client):
    r = client.get("/dashboards/sales/overview")
    assert r.status_code == 404
    assert r.json()["detail"] == "front end not built"


def test_unknown_api_path_is_404_not_spa(client):
    r = client.get("/api/nothing/here")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_spa_fallback_and_assets(settings, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>viz</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    settings.web_dist = dist
    client = TestClient(create_app(settings))

    r = client.get("/")
    assert r.status_code == 200 and "<title>viz</title>" in r.text
    r = client.get("/dashboards/sales/overview")
    assert r.status_code == 200 and "<title>viz</title>" in r.text
    r = client.get("/assets/app.js")
    assert r.status_code == 200 and r.text == "console.log(1)"
    r = client.get("/assets/../index.html")
    assert r.status_code in (200, 404)  # normalized by the client; must never escape dist
    assert r.headers["content-security-policy"]

    (tmp_path / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
    for path in ("/%2e%2e%2fsecret.txt", "/..%2fsecret.txt"):
        r = client.get(path)
        assert r.status_code == 200
        assert "<title>viz</title>" in r.text
        assert "TOP SECRET" not in r.text


def test_security_headers_on_static(settings, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    settings.web_dist = dist
    client = TestClient(create_app(settings))
    r = client.get("/anything")
    assert r.headers["x-frame-options"] == "DENY"
