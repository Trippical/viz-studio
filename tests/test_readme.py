"""README states the trust assumptions in plain words (spec 12.1, hardening B1)."""
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def _trust_section() -> str:
    text = README.read_text(encoding="utf-8")
    section = text.split("## Trust assumptions, read these first", 1)[1].split("\n## ", 1)[0]
    return " ".join(section.split())


def test_readme_says_the_site_has_no_login_of_its_own():
    section = _trust_section()
    for phrase in ("no login of its own", "SSO proxy", "`requireIdentity: true`", "401", "publishing is sharing"):
        assert phrase in section, phrase
