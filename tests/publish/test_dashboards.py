import json

from viz import schemas
from viz.publish.cli import main


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_new_dashboard_with_charts(env, staging_root, capsys):
    args = ["new-dashboard", "sales/weekly", "--chart", "sales/revenue-by-region", "--chart", "sales/total-revenue"]
    assert main(args) == 0
    path = staging_root / "dashboards" / "sales" / "weekly.json"
    doc = schemas.validate_dashboard(_read(path))
    assert doc["author"] == "tester@example.com"
    assert doc["title"] == "Weekly"
    assert doc["created_at"] == doc["updated_at"]
    assert doc["controls"] == []
    assert doc["layout"] == [
        {"chart": "sales/revenue-by-region", "w": 6, "h": 4},
        {"chart": "sales/total-revenue", "w": 6, "h": 4},
    ]
    assert f"staged: {path}" in capsys.readouterr().out


def test_new_dashboard_passes_validate_against_the_bucket(env, staging_root):
    assert main(["new-dashboard", "sales/weekly", "--chart", "sales/revenue-by-region"]) == 0
    assert main(["validate", str(staging_root / "dashboards" / "sales" / "weekly.json")]) == 0


def test_new_dashboard_without_charts_gets_a_markdown_placeholder(env, staging_root):
    assert main(["new-dashboard", "ops/empty", "--title", "Ops"]) == 0
    doc = _read(staging_root / "dashboards" / "ops" / "empty.json")
    assert doc["title"] == "Ops"
    assert doc["layout"] == [{"markdown": "Describe what this dashboard answers.", "w": 12, "h": 1}]


def test_new_dashboard_rejects_a_bad_chart_id_and_writes_nothing(env, staging_root, capsys):
    assert main(["new-dashboard", "sales/weekly", "--chart", "Sales/Bad"]) == 1
    assert not (staging_root / "dashboards").exists()
    assert "error: " in capsys.readouterr().err


def test_new_dashboard_refuses_to_replace_a_staged_file(env, staging_root, capsys):
    assert main(["new-dashboard", "sales/weekly"]) == 0
    path = staging_root / "dashboards" / "sales" / "weekly.json"
    path.write_text('{"edited": true}\n', encoding="utf-8")
    capsys.readouterr()
    assert main(["new-dashboard", "sales/weekly"]) == 1
    assert path.read_text(encoding="utf-8") == '{"edited": true}\n'
    assert "--force" in capsys.readouterr().err
    assert main(["new-dashboard", "sales/weekly", "--force"]) == 0
    assert _read(path)["id"] == "sales/weekly"


def test_pull_dashboard_stages_a_restamped_copy(env, staging_root, bucket):
    published = _read(bucket / "viz" / "dashboards" / "sales" / "overview.json")
    assert main(["pull-dashboard", "sales/overview"]) == 0
    path = staging_root / "dashboards" / "sales" / "overview.json"
    doc = _read(path)
    assert doc["author"] == "tester@example.com"
    assert doc["created_at"] == published["created_at"]
    assert doc["updated_at"] != published["updated_at"]
    assert doc["layout"] == published["layout"]
    assert doc["controls"] == published["controls"]
    assert main(["validate", str(path)]) == 0


def test_pull_dashboard_that_is_not_published(env, capsys):
    assert main(["pull-dashboard", "sales/nope"]) == 1
    assert "not published" in capsys.readouterr().err


def test_pull_dashboard_refuses_to_replace_a_staged_file(env, staging_root, capsys):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    path = staging_root / "dashboards" / "sales" / "overview.json"
    path.write_text('{"edited": true}\n', encoding="utf-8")
    capsys.readouterr()
    assert main(["pull-dashboard", "sales/overview"]) == 1
    assert path.read_text(encoding="utf-8") == '{"edited": true}\n'
    assert "--force" in capsys.readouterr().err


def test_pulled_dashboard_with_a_deleted_chart_fails_validation(env, staging_root, bucket, capsys):
    (bucket / "viz" / "charts" / "sales" / "total-revenue" / "chart.json").unlink()
    assert main(["pull-dashboard", "sales/overview"]) == 0
    capsys.readouterr()
    assert main(["validate", str(staging_root / "dashboards" / "sales" / "overview.json")]) == 1
    assert "sales/total-revenue" in capsys.readouterr().err
