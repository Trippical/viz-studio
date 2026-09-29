"""Fixtures for the publisher tests. Commands read Settings() from the
environment, so the `env` fixture is how tests point them at a temp bucket."""
import shutil
from pathlib import Path

import pytest

from viz.config import Settings
from viz.storage import get_storage

SAMPLE = Path(__file__).resolve().parents[2] / "sample-bucket"


@pytest.fixture
def bucket(tmp_path) -> Path:
    """A writable copy of the sample bucket. The real sample bucket is never touched."""
    dst = tmp_path / "bucket"
    shutil.copytree(SAMPLE / "viz", dst / "viz")
    return dst


@pytest.fixture
def staging_root(tmp_path) -> Path:
    root = tmp_path / "staging"
    root.mkdir()
    return root


@pytest.fixture
def env(monkeypatch, bucket, staging_root):
    monkeypatch.setenv("VIZ_STORAGE", "local")
    monkeypatch.setenv("VIZ_LOCAL_DIR", str(bucket))
    monkeypatch.setenv("VIZ_ROOT_PREFIX", "viz/")
    monkeypatch.setenv("VIZ_AUTHOR", "tester@example.com")
    monkeypatch.setenv("VIZ_STAGING_DIR", str(staging_root))
    # "testserver" is the Host header FastAPI's TestClient sends; allowed in tests only.
    monkeypatch.setenv("VIZ_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    for name in ("VIZ_QUERY_DENY", "VIZ_PII_PATTERN", "VIZ_FORCE", "VIZ_S3_BUCKET"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(env) -> Settings:
    return Settings()


@pytest.fixture
def storage(settings):
    return get_storage(settings)
