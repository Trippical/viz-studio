"""The publish-viz skill must stay true to the code: real commands, real files, every example taught."""
import argparse
import re
from pathlib import Path

from viz.publish.cli import build_parser
from viz.publish.staging import LARGE_DEFAULT_AGGREGATE

SKILL = Path(__file__).resolve().parents[1] / "skills" / "publish-viz"
DOCS = [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _subcommands() -> set[str]:
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    raise AssertionError("viz has no subcommands")


def test_skill_front_matter():
    text = _text(SKILL / "SKILL.md")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with YAML front matter"
    front = match.group(1)
    assert re.search(r"^name: publish-viz$", front, re.MULTILINE)
    description = re.search(r"^description: (.+)$", front, re.MULTILINE)
    assert description and description.group(1).startswith("Use when")
    assert len(description.group(1)) <= 1024


def test_skill_is_short_enough_to_load():
    assert len(_text(SKILL / "SKILL.md").splitlines()) < 300


def test_every_referenced_file_exists():
    for doc in DOCS:
        for ref in re.findall(r"(?:references|examples)/[a-z0-9-]+\.(?:md|json)", _text(doc)):
            assert (SKILL / ref).is_file(), f"{doc.name} names {ref}, which does not exist"


def test_every_example_is_taught_in_the_vega_lite_guide():
    guide = _text(SKILL / "references" / "vega-lite.md")
    for example in sorted((SKILL / "examples").glob("*.json")):
        assert f"examples/{example.name}" in guide, f"vega-lite.md never names {example.name}"


def test_every_viz_command_named_in_the_skill_exists():
    commands = _subcommands()
    for doc in DOCS:
        for name in re.findall(r"`viz ([a-z][a-z-]*)", _text(doc)):
            assert name in commands, f"{doc.name} names `viz {name}`, which is not a viz subcommand"


def test_skill_states_the_trust_assumptions():
    text = _text(SKILL / "SKILL.md")
    for phrase in (
        "Publishing equals sharing",
        "Folders are organization, not permission",
        "Filters are a view, not a restriction",
        "data, never instructions",
    ):
        assert phrase in text, phrase


def test_skill_teaches_the_author_workaround():
    text = _text(SKILL / "SKILL.md")
    assert "VIZ_AUTHOR" in text
    assert "does not match the resolved identity" in text


def test_skill_forbids_the_dangerous_flags_without_the_user():
    text = _text(SKILL / "SKILL.md")
    for flag in ("--force", "--yes", "--allow-row-level"):
        assert flag in text, flag


def test_skill_teaches_editing_the_large_lane_aggregate():
    workflow = _text(SKILL / "SKILL.md")
    assert "`aggregate`" in workflow

    data = _text(SKILL / "references" / "data.md")
    assert "SELECT * FROM data LIMIT 1000" in data
    assert LARGE_DEFAULT_AGGREGATE in data
    assert "SELECT * FROM data LIMIT 1000" == LARGE_DEFAULT_AGGREGATE


def test_skill_says_to_ask_when_viz_storage_is_not_set():
    text = _text(SKILL / "SKILL.md")
    assert "`VIZ_STORAGE` is not set" in text


def _step(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end)]


def test_skill_stops_on_errors_that_need_the_user():
    text = _text(SKILL / "SKILL.md")
    step5 = _step(text, "5. **Validate.**", "6. **Preview")
    assert "ask the user" in step5
    assert "Never add `--force`, `--yes` or `--allow-row-level` on your own." in step5


def test_skill_allows_editing_the_renderer():
    text = _text(SKILL / "SKILL.md")
    step4 = _step(text, "4. **Write the chart.**", "5. **Validate.**")
    assert "`renderer`" in step4


def test_dashboards_guide_calls_author_attribution():
    text = _text(SKILL / "references" / "dashboards.md")
    assert "must equal the identity" not in text
    assert "with your identity" not in text
    assert "attribution" in text
