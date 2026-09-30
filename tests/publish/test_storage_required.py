"""viz publish and viz move never fall back to the default local folder (finding A13)."""
from datetime import date, datetime, timezone

import pyarrow as pa

from viz.config import Settings
from viz.publish.cli import main
from viz.publish.publish import destination
from viz.publish.staging import write_staged_chart

NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


def _staged(staging_root, chart_id="sales/new-chart"):
    table = pa.table({"month": [date(2024, 1, 1), date(2024, 2, 1)], "revenue": [1.5, 2.5]})
    return write_staged_chart(table, chart_id, staging_root, author="tester@example.com", now=NOW)


def test_publish_without_viz_storage_is_refused_and_writes_nothing(env, bucket, staging_root, monkeypatch, capsys):
    staged = _staged(staging_root)
    monkeypatch.delenv("VIZ_STORAGE")
    assert main(["publish", str(staged.dir)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: VIZ_STORAGE is not set")
    assert "ask the user" in err
    assert not (bucket / "viz" / "charts" / "sales" / "new-chart").exists()


def test_blank_viz_storage_is_refused(env, staging_root, monkeypatch, capsys):
    staged = _staged(staging_root)
    monkeypatch.setenv("VIZ_STORAGE", "  ")
    assert main(["publish", str(staged.dir)]) == 2
    assert "VIZ_STORAGE is not set" in capsys.readouterr().err


def test_move_without_viz_storage_is_refused_and_moves_nothing(env, bucket, monkeypatch, capsys):
    monkeypatch.delenv("VIZ_STORAGE")
    assert main(["move", "sales/revenue-by-region", "sales/renamed", "--yes"]) == 2
    assert "VIZ_STORAGE is not set" in capsys.readouterr().err
    assert (bucket / "viz" / "charts" / "sales" / "revenue-by-region" / "chart.json").is_file()
    assert not (bucket / "viz" / "charts" / "sales" / "renamed").exists()


def test_publish_prints_the_local_destination(env, bucket, staging_root, capsys):
    staged = _staged(staging_root)
    assert main(["publish", str(staged.dir)]) == 0
    expected = str((bucket / "viz" / "charts" / "sales" / "new-chart" / "chart.json").resolve())
    assert f"published: sales/new-chart -> {expected}" in capsys.readouterr().out.splitlines()


def test_move_prints_the_local_destination(env, bucket, capsys):
    assert main(["move", "sales/revenue-by-region", "sales/renamed", "--yes"]) == 0
    expected = str((bucket / "viz").resolve())
    assert f"moved: sales/revenue-by-region -> sales/renamed in {expected}" in capsys.readouterr().out


def test_destination_for_s3():
    settings = Settings(storage="s3", s3_bucket="viz-bucket", root_prefix="viz/")
    assert destination(settings, "viz/charts/a/chart.json") == "s3://viz-bucket/viz/charts/a/chart.json"
