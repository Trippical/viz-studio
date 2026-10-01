"""Every refusal that needs a person's consent says so, so an agent stops and asks
instead of adding the flag itself (finding A14)."""
from datetime import date, datetime, timezone

import pyarrow as pa

from viz.publish import staging
from viz.publish.cli import main
from viz.publish.staging import write_staged_chart

NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


def _staged(staging_root, chart_id):
    table = pa.table({"month": [date(2024, 1, 1), date(2024, 2, 1)], "revenue": [1.5, 2.5]})
    return write_staged_chart(table, chart_id, staging_root, author="tester@example.com", now=NOW)


def test_publish_overwrite_says_ask_the_user(env, staging_root, capsys):
    staged = _staged(staging_root, "sales/ask-first")
    assert main(["publish", str(staged.dir)]) == 0
    capsys.readouterr()
    assert main(["publish", str(staged.dir)]) == 1
    assert "ask the user before passing --force" in capsys.readouterr().err


def test_row_level_says_ask_the_user(env, staging_root, capsys, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    staged = _staged(staging_root, "sales/ask-large")
    assert main(["validate", str(staged.dir)]) == 1
    assert "ask the user before passing --allow-row-level" in capsys.readouterr().err


def test_move_dry_run_says_ask_the_user(env, capsys):
    assert main(["move", "sales/revenue-by-region", "sales/renamed"]) == 1
    assert "ask the user before passing --yes" in capsys.readouterr().err


def test_replacing_a_staged_dashboard_says_ask_the_user(env, capsys):
    assert main(["new-dashboard", "sales/ask-board"]) == 0
    capsys.readouterr()
    assert main(["new-dashboard", "sales/ask-board"]) == 1
    assert "ask the user before passing --force" in capsys.readouterr().err


def test_replacing_an_installed_skill_says_ask_the_user(tmp_path, capsys):
    assert main(["install-skill", "--dest", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["install-skill", "--dest", str(tmp_path)]) == 1
    assert "ask the user before passing --force" in capsys.readouterr().err
