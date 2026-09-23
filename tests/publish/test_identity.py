import getpass

import pytest
from moto import mock_aws

from viz.config import Settings
from viz.publish.identity import check_author, resolve_author


def test_databricks_user_wins():
    s = Settings(storage="local", author="env@example.com")
    assert resolve_author(s, databricks_user="dbx@example.com") == "dbx@example.com"


def test_settings_author_next():
    s = Settings(storage="local", author="env@example.com")
    assert resolve_author(s) == "env@example.com"


def test_local_fallback_is_user_at_local(monkeypatch):
    monkeypatch.delenv("VIZ_AUTHOR", raising=False)
    s = Settings(storage="local", author=None)
    assert resolve_author(s) == f"{getpass.getuser()}@local"


def test_s3_uses_sts_caller_identity(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("VIZ_AUTHOR", raising=False)
    s = Settings(storage="s3", s3_bucket="b", author=None)
    with mock_aws():
        arn = resolve_author(s)
    assert arn.startswith("arn:aws:")


def test_check_author():
    s = Settings(storage="local", author="env@example.com")
    assert check_author({"author": "env@example.com"}, s) == []
    assert check_author({"author": "someone@else"}, s) == [
        "author 'someone@else' does not match the resolved identity 'env@example.com'"
    ]
    assert check_author({}, s) == ["author is missing; the CLI stamps it as 'env@example.com'"]
    assert check_author({"author": "dbx@example.com"}, s, databricks_user="dbx@example.com") == []
