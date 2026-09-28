"""Opt-in: a round trip against a real S3 bucket. Never runs in CI or on pull requests.
Uses a unique throwaway prefix and deletes everything it wrote."""
import os
import uuid

import pytest

from viz.storage import NotFound
from viz.storage.s3 import S3Storage

pytestmark = pytest.mark.skipif(
    os.environ.get("VIZ_INTEGRATION") != "1" or not os.environ.get("VIZ_IT_S3_BUCKET"),
    reason="set VIZ_INTEGRATION=1 and VIZ_IT_S3_BUCKET (and AWS credentials) to run",
)


def test_round_trip_against_a_real_bucket():
    storage = S3Storage(os.environ["VIZ_IT_S3_BUCKET"])
    base = os.environ.get("VIZ_IT_S3_PREFIX", "viz/")
    if not base.endswith("/"):
        base += "/"
    prefix = f"{base}integration-{uuid.uuid4().hex[:12]}/"
    first, second = f"{prefix}a.json", f"{prefix}b.json"
    try:
        with pytest.raises(NotFound):
            storage.get(f"{prefix}missing.json")
        storage.put(first, b'{"ok": true}', "application/json")
        assert storage.get(first) == b'{"ok": true}'
        assert storage.head(first).size == 12
        assert b"".join(storage.open(first, 1, 4)) == b'"ok"'
        storage.copy(first, second)
        assert [info.key for info in storage.list(prefix)] == [first, second]
    finally:
        for key in (first, second):
            try:
                storage.delete(key)
            except NotFound:
                pass
    assert storage.list(prefix) == []
