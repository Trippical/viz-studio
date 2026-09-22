from pathlib import Path

import pytest

from viz.config import Settings
from viz.storage import get_storage
from viz.storage.local import LocalStorage
from viz.storage.s3 import S3Storage


def test_defaults(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("VIZ_"):
            monkeypatch.delenv(key)
    s = Settings()
    assert s.storage == "local"
    assert s.root_prefix == "viz/"
    assert s.local_dir == Path("./sample-bucket")
    assert s.tree_ttl_seconds == 60
    assert s.allowed_hosts_list == ["localhost", "127.0.0.1", "testserver"]
    assert s.auth_header == "X-Forwarded-Email"
    assert s.max_document_bytes == 1048576
    assert s.host == "127.0.0.1"


def test_env_overrides_and_root_normalization(monkeypatch):
    monkeypatch.setenv("VIZ_STORAGE", "s3")
    monkeypatch.setenv("VIZ_S3_BUCKET", "my-bucket")
    monkeypatch.setenv("VIZ_ROOT_PREFIX", "/dash")
    monkeypatch.setenv("VIZ_ALLOWED_HOSTS", "viz.internal, localhost")
    s = Settings()
    assert s.storage == "s3"
    assert s.s3_bucket == "my-bucket"
    assert s.root_prefix == "dash/"
    assert s.allowed_hosts_list == ["viz.internal", "localhost"]


def test_get_storage_local(tmp_path):
    s = Settings(storage="local", local_dir=tmp_path)
    assert isinstance(get_storage(s), LocalStorage)


def test_get_storage_s3_requires_bucket():
    with pytest.raises(ValueError):
        get_storage(Settings(storage="s3", s3_bucket=None))


def test_get_storage_s3(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    storage = get_storage(Settings(storage="s3", s3_bucket="b"))
    assert isinstance(storage, S3Storage)
    assert storage.bucket == "b"
