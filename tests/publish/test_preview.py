from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
from fastapi.testclient import TestClient

import viz.publish.cli as cli
from viz.publish.cli import main
from viz.publish.preview import build_preview_app, preview_settings
from viz.publish.staging import write_staged_chart

NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


def _stage_one(staging_root):
    table = pa.table({"month": [date(2024, 1, 1)], "revenue": [1.5]})
    return write_staged_chart(table, "sales/preview-me", staging_root, author="tester@example.com", now=NOW)


def test_preview_settings_ignore_storage_env(monkeypatch, staging_root):
    monkeypatch.setenv("VIZ_STORAGE", "s3")
    monkeypatch.setenv("VIZ_S3_BUCKET", "real-bucket")
    monkeypatch.setenv("VIZ_ROOT_PREFIX", "viz/")
    s = preview_settings(staging_root)
    assert s.storage == "local"
    assert s.local_dir == staging_root
    assert s.root_prefix == ""
    assert s.allowed_hosts_list == ["localhost", "127.0.0.1"]
    assert preview_settings(staging_root, host="0.0.0.0").allowed_hosts_list == ["*"]


def test_preview_app_serves_the_staging_directory(env, staging_root):
    _stage_one(staging_root)
    client = TestClient(build_preview_app(staging_root), base_url="http://127.0.0.1")
    assert client.get("/api/charts/sales/preview-me").status_code == 200
    r = client.get("/api/data/sales/preview-me")
    assert r.status_code == 200 and r.json()[0]["revenue"] == 1.5
    tree = client.get("/api/tree").json()
    assert tree["charts"]["folders"][0]["name"] == "sales"


def test_preview_app_rejects_foreign_host(env, staging_root):
    app = build_preview_app(staging_root)
    client = TestClient(app, base_url="http://evil.example")
    assert client.get("/api/tree").status_code == 400


def test_preview_command_defaults_to_loopback(env, staging_root, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_preview", lambda root, host, port: calls.append((Path(root), host, port)))
    assert main(["preview"]) == 0
    assert calls == [(staging_root, "127.0.0.1", 8000)]

    calls.clear()
    assert main(["preview", "--host", "0.0.0.0", "--port", "9000", "--staging", str(staging_root / "other")]) == 0
    assert calls == [(staging_root / "other", "0.0.0.0", 9000)]
