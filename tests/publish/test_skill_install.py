from pathlib import Path

from viz.publish import skill
from viz.publish.cli import main

REPO = Path(__file__).resolve().parents[2]


def test_skill_source_finds_the_checkout_copy():
    assert (skill.skill_source() / "SKILL.md").is_file()


def test_default_destination_is_the_claude_code_personal_skills_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert skill.default_destination() == tmp_path / ".claude" / "skills"


def test_install_skill_copies_the_whole_skill(tmp_path, capsys):
    assert main(["install-skill", "--dest", str(tmp_path)]) == 0
    target = tmp_path / "publish-viz"
    assert (target / "SKILL.md").is_file()
    assert (target / "references" / "vega-lite.md").is_file()
    assert (target / "examples" / "line-by-category.json").is_file()
    assert f"installed: {target}" in capsys.readouterr().out


def test_install_skill_refuses_to_overwrite_without_force(tmp_path, capsys):
    target = tmp_path / "publish-viz"
    target.mkdir()
    (target / "SKILL.md").write_text("my own edits\n", encoding="utf-8")
    assert main(["install-skill", "--dest", str(tmp_path)]) == 1
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "my own edits\n"
    assert "--force" in capsys.readouterr().err


def test_install_skill_force_replaces_the_old_copy(tmp_path):
    target = tmp_path / "publish-viz"
    target.mkdir()
    (target / "stale.md").write_text("old\n", encoding="utf-8")
    assert main(["install-skill", "--dest", str(tmp_path), "--force"]) == 0
    assert not (target / "stale.md").exists()
    assert (target / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: publish-viz")


def test_install_skill_reports_a_missing_skill(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(skill, "_CANDIDATE_DIRS", (tmp_path / "nowhere",))
    assert main(["install-skill", "--dest", str(tmp_path / "dest")]) == 2
    assert "not packaged" in capsys.readouterr().err


def test_the_wheel_packages_the_skill():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert '"skills/publish-viz" = "viz/_skills/publish-viz"' in text
