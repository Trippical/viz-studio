"""Conditional puts: the commit point of an atomic publish (hardening decision B2)."""
import hashlib
import threading

import boto3
import botocore.session
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from viz.storage import PreconditionFailed
from viz.storage.base import NotFound
from viz.storage.local import LocalStorage
from viz.storage.s3 import S3Storage


@pytest.fixture(params=["local", "s3"])
def storage(request, tmp_path, monkeypatch):
    if request.param == "local":
        (tmp_path / "bucket").mkdir()
        yield LocalStorage(tmp_path / "bucket")
        return
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-bucket")
        yield S3Storage("test-bucket", client=client)


def test_etag_is_the_md5_of_the_bytes(storage):
    storage.put("k", b"hello", "text/plain")
    expected = hashlib.md5(b"hello").hexdigest()
    assert storage.head("k").etag == expected
    assert [info.etag for info in storage.list("k")] == [expected]


def test_if_none_match_writes_only_a_new_key(storage):
    storage.put("k", b"one", "text/plain", if_none_match=True)
    with pytest.raises(PreconditionFailed):
        storage.put("k", b"two", "text/plain", if_none_match=True)
    assert storage.get("k") == b"one"


def test_if_match_needs_the_current_etag(storage):
    storage.put("k", b"one", "text/plain")
    first = storage.head("k").etag
    storage.put("k", b"two", "text/plain", if_match=first)
    assert storage.get("k") == b"two"
    with pytest.raises(PreconditionFailed):
        storage.put("k", b"three", "text/plain", if_match=first)  # stale ETag
    assert storage.get("k") == b"two"


def test_if_match_on_a_missing_key_is_precondition_failed(storage):
    with pytest.raises(PreconditionFailed):
        storage.put("gone", b"x", "text/plain", if_match=hashlib.md5(b"x").hexdigest())
    with pytest.raises(NotFound):
        storage.get("gone")


def test_both_conditions_at_once_is_a_programming_error(storage):
    with pytest.raises(ValueError):
        storage.put("k", b"x", "text/plain", if_match="abc", if_none_match=True)


def test_local_conditional_put_is_atomic_across_threads(tmp_path):
    storage = LocalStorage(tmp_path)
    results = []

    def attempt(i: int) -> None:
        try:
            storage.put("k", str(i).encode(), "text/plain", if_none_match=True)
            results.append("written")
        except PreconditionFailed:
            results.append("refused")

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("written") == 1
    assert results.count("refused") == 7


class _RecordingClient:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        return {}


def test_s3_sends_the_conditions_to_put_object():
    client = _RecordingClient()
    storage = S3Storage("b", client=client)
    storage.put("k", b"x", "text/plain", if_none_match=True)
    storage.put("k", b"x", "text/plain", if_match="abc123")
    storage.put("k", b"x", "text/plain")
    assert client.calls[0]["IfNoneMatch"] == "*" and "IfMatch" not in client.calls[0]
    assert client.calls[1]["IfMatch"] == '"abc123"' and "IfNoneMatch" not in client.calls[1]
    assert "IfMatch" not in client.calls[2] and "IfNoneMatch" not in client.calls[2]


class _FailingClient:
    def __init__(self, code: str, status: int):
        self.code = code
        self.status = status

    def put_object(self, **kwargs):
        raise ClientError({"Error": {"Code": self.code, "Message": "x"},
                           "ResponseMetadata": {"HTTPStatusCode": self.status}}, "PutObject")


@pytest.mark.parametrize("code,status", [("PreconditionFailed", 412), ("ConditionalRequestConflict", 409)])
def test_s3_maps_conditional_failures(code, status):
    storage = S3Storage("b", client=_FailingClient(code, status))
    with pytest.raises(PreconditionFailed):
        storage.put("k", b"x", "text/plain", if_none_match=True)


def test_s3_other_errors_are_not_precondition_failures():
    storage = S3Storage("b", client=_FailingClient("AccessDenied", 403))
    with pytest.raises(ClientError):
        storage.put("k", b"x", "text/plain", if_none_match=True)


def test_installed_botocore_knows_the_conditional_put_parameters():
    # boto3>=1.35.69 (botocore 1.35.69) is the first release with IfMatch on PutObject.
    shape = botocore.session.get_session().get_service_model("s3").operation_model("PutObject").input_shape
    assert "IfMatch" in shape.members
    assert "IfNoneMatch" in shape.members
