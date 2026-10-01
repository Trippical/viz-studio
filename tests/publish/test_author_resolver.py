"""One author rule for every command that stamps a document (finding A19): the
Databricks login when DATABRICKS_HOST, DATABRICKS_TOKEN and DATABRICKS_WAREHOUSE_ID
are all set, otherwise VIZ_AUTHOR, the AWS caller identity, or <user>@local.
viz validate applies the same rule."""
import json
import os

import pytest

import viz.publish.identity as identity
from viz.config import Settings
from viz.publish import query
from viz.publish.cli import main
from viz.publish.identity import publisher_author


class FakeCursor:
    def __init__(self, calls):
        self.calls = calls

    def execute(self, sql):
        self.calls.append(sql)

    def fetchone(self):
        return ("dbx@example.com",)

    def close(self):
        pass


class FakeConnection:
    def __init__(self, calls):
        self.calls = calls

    def cursor(self):
        return FakeCursor(self.calls)

    def close(self):
        pass


@pytest.fixture
def dbx(monkeypatch):
    calls = []
    monkeypatch.setattr(query, "_connect", lambda **kwargs: FakeConnection(calls))
    monkeypatch.setenv("DATABRICKS_HOST", "https://dbc-123.cloud.databricks.com/")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")
    return calls


def _csv(tmp_path):
    path = tmp_path / "rows.csv"
    path.write_text("region,revenue\nEMEA,1.5\n", encoding="utf-8")
    return path


def _never_connect(**kwargs):
    raise AssertionError("must not contact Databricks")


def test_publisher_author_order(monkeypatch):
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)
    s = Settings(storage="local", author="env@example.com")
    assert publisher_author(s) == "env@example.com"
    assert publisher_author(s, databricks_user="given@example.com") == "given@example.com"

    # Host and token without a warehouse: the login is not used, and nothing connects.
    monkeypatch.setenv("DATABRICKS_HOST", "https://dbc-123.cloud.databricks.com/")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.setattr(query, "_connect", _never_connect)
    assert query.databricks_login_available() is False
    assert publisher_author(s) == "env@example.com"

    # A warehouse passed by the caller (the one a viz query chart ran on) completes the three.
    monkeypatch.setattr(query, "_connect", lambda **kwargs: FakeConnection([]))
    assert query.databricks_login_available("wh-from-source") is True
    assert publisher_author(s, warehouse_id="wh-from-source") == "dbx@example.com"

    # All three variables set.
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")
    assert query.databricks_login_available() is True
    assert publisher_author(s) == "dbx@example.com"
    assert publisher_author(s, databricks_user="given@example.com") == "given@example.com"


def test_env_fixture_clears_databricks_variables(monkeypatch, request):
    monkeypatch.delenv("VIZ_INTEGRATION", raising=False)
    monkeypatch.setenv("DATABRICKS_HOST", "https://leak.example.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-leak")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "leak")
    request.getfixturevalue("env")
    for name in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        assert name not in os.environ, f"unit tests must never see a real {name}"


def test_stage_stamps_and_validates_the_databricks_login(env, staging_root, dbx, tmp_path):
    assert main(["stage", "--from", str(_csv(tmp_path)), "--id", "sales/from-file"]) == 0
    chart_dir = staging_root / "charts" / "sales" / "from-file"
    assert json.loads((chart_dir / "chart.json").read_text(encoding="utf-8"))["author"] == "dbx@example.com"
    assert main(["validate", str(chart_dir)]) == 0


def test_new_dashboard_stamps_and_validates_the_databricks_login(env, staging_root, dbx):
    assert main(["new-dashboard", "sales/dbx-board", "--chart", "sales/revenue-by-region"]) == 0
    path = staging_root / "dashboards" / "sales" / "dbx-board.json"
    assert json.loads(path.read_text(encoding="utf-8"))["author"] == "dbx@example.com"
    assert main(["validate", str(path)]) == 0


def test_pull_dashboard_stamps_and_validates_the_databricks_login(env, staging_root, dbx):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    path = staging_root / "dashboards" / "sales" / "overview.json"
    assert json.loads(path.read_text(encoding="utf-8"))["author"] == "dbx@example.com"
    assert main(["validate", str(path)]) == 0


def test_without_databricks_every_command_uses_viz_author(env, staging_root, tmp_path):
    assert main(["stage", "--from", str(_csv(tmp_path)), "--id", "sales/from-file"]) == 0
    chart = staging_root / "charts" / "sales" / "from-file" / "chart.json"
    assert json.loads(chart.read_text(encoding="utf-8"))["author"] == "tester@example.com"
    assert main(["new-dashboard", "sales/plain-board"]) == 0
    board = staging_root / "dashboards" / "sales" / "plain-board.json"
    assert json.loads(board.read_text(encoding="utf-8"))["author"] == "tester@example.com"


def test_without_a_warehouse_id_every_command_uses_viz_author(env, staging_root, dbx, monkeypatch, tmp_path):
    # DATABRICKS_HOST and DATABRICKS_TOKEN are set, DATABRICKS_WAREHOUSE_ID is not:
    # no command fails for want of a warehouse, and none contacts Databricks.
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID")
    assert main(["stage", "--from", str(_csv(tmp_path)), "--id", "sales/from-file"]) == 0
    chart_dir = staging_root / "charts" / "sales" / "from-file"
    assert json.loads((chart_dir / "chart.json").read_text(encoding="utf-8"))["author"] == "tester@example.com"
    assert main(["validate", str(chart_dir)]) == 0
    assert main(["new-dashboard", "sales/plain-board", "--chart", "sales/revenue-by-region"]) == 0
    board = staging_root / "dashboards" / "sales" / "plain-board.json"
    assert json.loads(board.read_text(encoding="utf-8"))["author"] == "tester@example.com"
    assert main(["validate", str(board)]) == 0
    assert main(["pull-dashboard", "sales/overview"]) == 0
    assert dbx == [], "no Databricks connection without DATABRICKS_WAREHOUSE_ID"


def test_unreachable_databricks_during_stage_is_a_clean_error(env, staging_root, dbx, monkeypatch, tmp_path, capsys):
    def refuse(**kwargs):
        raise ConnectionError("warehouse unreachable")

    monkeypatch.setattr(query, "_connect", refuse)
    assert main(["stage", "--from", str(_csv(tmp_path)), "--id", "sales/from-file"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: could not resolve the author identity:")
    assert "Traceback" not in err
    assert not (staging_root / "charts" / "sales" / "from-file").exists()


def test_identity_module_describes_author_as_attribution():
    assert "attribution" in identity.__doc__
    assert "not authentication" in identity.__doc__
