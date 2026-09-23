import pytest

from viz import __version__
from viz.config import Settings
from viz.publish.cli import main
from viz.publish.errors import CliError


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"viz {__version__}"


def test_no_command_prints_help_and_returns_2(capsys):
    assert main([]) == 2
    assert "usage: viz" in capsys.readouterr().out


def test_cli_error_is_printed_one_per_line(capsys, monkeypatch):
    import viz.publish.cli as cli

    def boom(args):
        raise CliError(["first thing", "second thing"], code=1)

    monkeypatch.setattr(cli, "_DEBUG_HANDLER", boom)
    assert main(["debug-raise"]) == 1
    err = capsys.readouterr().err
    assert err == "error: first thing\nerror: second thing\n"


def test_cli_error_accepts_a_single_string():
    err = CliError("just one", code=2)
    assert err.messages == ["just one"]
    assert err.code == 2


def test_publisher_settings_defaults(env, monkeypatch):
    monkeypatch.delenv("VIZ_AUTHOR", raising=False)
    monkeypatch.delenv("VIZ_STAGING_DIR", raising=False)
    s = Settings()
    assert s.author is None
    assert s.query_deny == ""
    assert "email" in s.pii_pattern
    assert s.staging_dir.name == ".viz-staging"


def test_publisher_settings_from_env(settings, staging_root):
    assert settings.author == "tester@example.com"
    assert settings.staging_dir == staging_root


def test_new_dependencies_import():
    import duckdb  # noqa: F401
    import pyarrow  # noqa: F401
