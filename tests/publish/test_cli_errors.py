"""Regression tests: no plausible bad input may escape main() as a traceback.
Every case below must exit with a CliError-shaped 'error: ...' line on stderr,
never a Python traceback."""
import pyarrow as pa
import pytest

from viz.publish import query
from viz.publish.cli import main


def _assert_clean_error(err: str, code: int, expected_code: int) -> None:
    assert code == expected_code
    assert err.startswith("error: ")
    assert "Traceback" not in err


def test_ragged_csv_is_a_clean_error(env, tmp_path, capsys):
    path = tmp_path / "ragged.csv"
    path.write_text("a,b,c\n1,2,3\n4,5\n", encoding="utf-8")
    code = main(["stage", "--from", str(path), "--id", "sales/ragged"])
    _assert_clean_error(capsys.readouterr().err, code, 2)


def test_invalid_json_file_is_a_clean_error(env, tmp_path, capsys):
    path = tmp_path / "in.json"
    path.write_text("not json", encoding="utf-8")
    code = main(["stage", "--from", str(path), "--id", "sales/badjson"])
    _assert_clean_error(capsys.readouterr().err, code, 2)


def test_garbage_parquet_file_is_a_clean_error(env, tmp_path, capsys):
    path = tmp_path / "in.parquet"
    path.write_bytes(b"garbage")
    code = main(["stage", "--from", str(path), "--id", "sales/badparquet"])
    _assert_clean_error(capsys.readouterr().err, code, 2)


def test_s3_author_resolution_without_credentials_is_a_clean_error(env, tmp_path, capsys, monkeypatch):
    path = tmp_path / "in.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    monkeypatch.setenv("VIZ_STORAGE", "s3")
    monkeypatch.setenv("VIZ_S3_BUCKET", "x")
    monkeypatch.delenv("VIZ_AUTHOR", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    code = main(["stage", "--from", str(path), "--id", "sales/nocreds"])
    _assert_clean_error(capsys.readouterr().err, code, 2)


def test_truncated_parquet_in_validate_is_a_clean_error(env, staging_root, tmp_path, capsys, monkeypatch):
    from viz.publish import staging as staging_mod
    from viz.publish.staging import write_staged_chart

    monkeypatch.setattr(staging_mod, "SMALL_MAX_ROWS", 0)
    table = pa.table({"a": list(range(5)), "b": list(range(5))})
    from datetime import datetime, timezone
    staged = write_staged_chart(table, "sales/large", staging_root, author="tester@example.com",
                                 now=datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc))
    assert staged.data_path.name == "data.parquet"
    staged.data_path.write_bytes(b"0123456789")
    code = main(["validate", str(staged.dir)])
    _assert_clean_error(capsys.readouterr().err, code, 1)


def test_query_connector_failure_is_a_clean_error(env, capsys, monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://dbc-123.cloud.databricks.com/")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")

    def connect(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(query, "_connect", connect)
    code = main(["query", "--sql", "SELECT 1", "--id", "sales/boom"])
    _assert_clean_error(capsys.readouterr().err, code, 2)
