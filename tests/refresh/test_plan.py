import json
import shutil
from pathlib import Path

from viz.config import Settings
from viz.refresh import plan
from viz.refresh.__main__ import main
from viz.storage import get_storage

SAMPLE = Path(__file__).resolve().parents[2] / "sample-bucket"


def _settings(root: Path) -> Settings:
    return Settings(storage="local", local_dir=root, root_prefix="viz/")


def test_plan_lists_only_charts_with_a_source(tmp_path):
    shutil.copytree(SAMPLE / "viz", tmp_path / "viz")
    settings = _settings(tmp_path)
    assert plan(settings, get_storage(settings)) == [
        {"id": "sales/revenue-by-region", "schedule": "0 6 * * *", "warehouse_id": "sample"},
    ]


def test_plan_skips_an_invalid_chart(tmp_path, caplog):
    shutil.copytree(SAMPLE / "viz", tmp_path / "viz")
    bad = tmp_path / "viz" / "charts" / "broken" / "chart.json"
    bad.parent.mkdir(parents=True)
    bad.write_text(json.dumps({"schema_version": 1, "id": "broken"}), encoding="utf-8")
    settings = _settings(tmp_path)
    ids = [item["id"] for item in plan(settings, get_storage(settings))]
    assert ids == ["sales/revenue-by-region"]
    assert "broken" in caplog.text


def test_main_logs_the_plan_and_exits_zero(tmp_path, monkeypatch, capsys):
    shutil.copytree(SAMPLE / "viz", tmp_path / "viz")
    monkeypatch.setenv("VIZ_STORAGE", "local")
    monkeypatch.setenv("VIZ_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("VIZ_ROOT_PREFIX", "viz/")
    assert main() == 0
    out = capsys.readouterr().out
    assert "sales/revenue-by-region" in out
    assert "0 6 * * *" in out
    assert "1 refreshable chart" in out
