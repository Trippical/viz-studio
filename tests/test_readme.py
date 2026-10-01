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


def _paved_path_section() -> str:
    text = README.read_text(encoding="utf-8")
    section = text.split("## Publishing (the paved path)", 1)[1].split("\n## ", 1)[0]
    return " ".join(section.split())


def test_readme_names_the_local_publish_and_server_settings():
    """Adopter fix A7: VIZ_LOCAL_DIR, VIZ_HOST/VIZ_PORT and the <user>@local author fallback."""
    section = _paved_path_section()
    for phrase in ("`VIZ_LOCAL_DIR`", "`VIZ_STORAGE=local`", "`VIZ_HOST`", "`VIZ_PORT`", "`viz-server --help`",
                   "`<user>@local`", "`VIZ_STORAGE=s3`"):
        assert phrase in section, phrase
