import os
import sys
from datetime import datetime

import boto3
import pytest
from moto import mock_aws

from viz.storage.base import NotFound, ObjectInfo
from viz.storage.local import LocalStorage
from viz.storage.s3 import S3Storage


@pytest.fixture(params=["local", "s3"])
def storage(request, tmp_path, monkeypatch):
    if request.param == "local":
        yield LocalStorage(tmp_path / "bucket")
        return
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-bucket")
        yield S3Storage("test-bucket", client=client)


def test_put_get_head(storage):
    storage.put("viz/charts/a/chart.json", b'{"x": 1}', "application/json")
    assert storage.get("viz/charts/a/chart.json") == b'{"x": 1}'
    info = storage.head("viz/charts/a/chart.json")
    assert isinstance(info, ObjectInfo)
    assert info.key == "viz/charts/a/chart.json"
    assert info.size == 8
    assert info.etag
    assert info.last_modified is None or isinstance(info.last_modified, datetime)


def test_missing_key_raises(storage):
    with pytest.raises(NotFound):
        storage.get("nope")
    with pytest.raises(NotFound):
        storage.head("nope")
    with pytest.raises(NotFound):
        list(storage.open("nope"))


def test_list_is_recursive_and_sorted(storage):
    storage.put("viz/charts/b/chart.json", b"b", "application/json")
    storage.put("viz/charts/a/sub/chart.json", b"a", "application/json")
    storage.put("viz/dashboards/x.json", b"x", "application/json")
    keys = [o.key for o in storage.list("viz/charts/")]
    assert keys == ["viz/charts/a/sub/chart.json", "viz/charts/b/chart.json"]
    assert storage.list("viz/nothing/") == []


def test_open_streams_whole_object_and_ranges(storage):
    storage.put("k", b"0123456789", "application/octet-stream")
    assert b"".join(storage.open("k")) == b"0123456789"
    assert b"".join(storage.open("k", start=2, end=4)) == b"234"
    assert b"".join(storage.open("k", start=7)) == b"789"


def test_etag_changes_when_content_changes(storage):
    storage.put("k", b"one", "text/plain")
    first = storage.head("k").etag
    storage.put("k", b"two!", "text/plain")
    assert storage.head("k").etag != first


def test_delete_and_copy(storage):
    storage.put("src", b"data", "text/plain")
    storage.copy("src", "dst")
    assert storage.get("dst") == b"data"
    storage.delete("src")
    with pytest.raises(NotFound):
        storage.get("src")
    with pytest.raises(NotFound):
        storage.copy("src", "other")


def test_delete_missing_is_noop(storage):
    storage.delete("never-existed")


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privileges on Windows")
def test_local_refuses_symlink_escape(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    os.symlink(outside, bucket / "leak.txt")
    storage = LocalStorage(bucket)
    with pytest.raises(NotFound):
        storage.get("leak.txt")
    assert [o.key for o in storage.list("")] == []


def test_local_refuses_dotdot(tmp_path):
    storage = LocalStorage(tmp_path / "bucket")
    with pytest.raises(NotFound):
        storage.get("../outside.txt")
