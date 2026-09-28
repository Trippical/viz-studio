"""docs/work-setup.md must stay true to the code: every setting, every command, every file it names."""
import argparse
import re
from pathlib import Path

from viz.config import Settings
from viz.publish.cli import build_parser

REPO = Path(__file__).resolve().parents[1]
GUIDE = REPO / "docs" / "work-setup.md"


def _text() -> str:
    return GUIDE.read_text(encoding="utf-8")


def test_every_setting_is_documented():
    text = _text()
    for field in Settings.model_fields:
        assert f"VIZ_{field.upper()}" in text, f"VIZ_{field.upper()} is not documented"


def test_databricks_variables_are_documented():
    text = _text()
    for name in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        assert name in text, name


def test_every_viz_command_named_exists():
    parser = build_parser()
    commands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices
    for name in re.findall(r"\bviz ([a-z][a-z-]*)", _text()):
        assert name in commands, f"docs/work-setup.md names `viz {name}`"


def test_every_repo_path_named_exists():
    # web/ is left out on purpose: web/dist only exists after a build.
    for path in re.findall(r"`((?:deploy|docs|skills|tests)/[A-Za-z0-9_./-]+)`", _text()):
        assert (REPO / path).exists(), path


def test_the_guide_covers_the_real_infrastructure_checks():
    text = _text()
    for phrase in ("VIZ_INTEGRATION=1", "VIZ_IT_S3_BUCKET", "tests/publish/test_query_integration.py",
                   "tests/storage/test_s3_integration.py", "viz install-skill", "helm install", "Genie Code"):
        assert phrase in text, phrase
