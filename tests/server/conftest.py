import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from viz.config import Settings
from viz.server.app import create_app

SAMPLE = Path(__file__).resolve().parents[2] / "sample-bucket"


@pytest.fixture
def bucket(tmp_path) -> Path:
    """A writable copy of the sample bucket."""
    dst = tmp_path / "bucket"
    shutil.copytree(SAMPLE / "viz", dst / "viz")
    return dst


@pytest.fixture
def settings(bucket) -> Settings:
    return Settings(storage="local", local_dir=bucket, root_prefix="viz/", tree_ttl_seconds=60,
                    web_dist=bucket / "no-web-dist")


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))
