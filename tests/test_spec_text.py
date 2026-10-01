"""The design spec must describe what plan 5a built (hardening decisions B1, B2, B3, A18, A29, A37)."""
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1] / "docs" / "superpowers" / "specs" / "2026-09-22-viz-site-design.md"


def _text() -> str:
    return SPEC.read_text(encoding="utf-8")


def _section(heading: str) -> str:
    text = _text()
    start = text.index(heading)
    rest = text[start + len(heading):]
    ends = [i for i in (rest.find("\n### "), rest.find("\n## ")) if i != -1]
    return rest[: min(ends)] if ends else rest


def test_spec_describes_content_addressed_data_files():
    text = _text()
    assert "`data.file`" in text
    assert "data.<sha16>.json" in text
    assert "There is no `data.path` field" not in text
    assert "<chart-id>/data.json" not in text


def test_spec_describes_the_conditional_commit_point():
    layout = _section("### 4.1 Layout")
    assert "single commit point" in layout
    assert "If-None-Match" in layout and "If-Match" in layout


def test_spec_describes_the_identity_gate():
    text = _text()
    assert "VIZ_REQUIRE_IDENTITY" in _section("### 12.2 Server")
    assert "VIZ_REQUIRE_IDENTITY" in _section("### 5.1 Server")
    assert "auth middleware slot" not in text
    assert "middleware slot" not in text


def test_spec_exempts_health_from_the_host_check():
    assert "`GET /api/health` and `HEAD /api/health` are answered before the Host check" in _section("### 12.2 Server")


def test_spec_drops_the_dashboard_ancestor_rule():
    assert "Dashboard ids have no such rule" in _section("### 12.2 Server")


def test_spec_drops_the_retired_renderers_from_the_sanitizer_rules():
    front_end = _section("### 12.3 Front end")
    assert "ECharts:" not in front_end
    assert "Plotly:" not in front_end


def test_spec_records_the_refresher_sql_rule():
    refresher = _section("### 12.7 Constraints the v2 refresher spec must honour")
    assert "must never run bucket-supplied SQL under a shared service" in refresher
    assert "no broader than the original author's" in refresher


def test_spec_records_the_viewer_rules_of_plan_5c():
    front_end = " ".join(_section("### 12.3 Front end").split())
    for phrase in (
        "`data` is allowed only at the top level",
        "`sequence`, `graticule` and `sphere` are rejected at any depth",
        "`params[].bind.element`",
        "Tooltips are text only",
        "`allowed_directories=['/viz-data/']` and `enable_external_access=false`",
    ):
        assert phrase in front_end, phrase
    assert "disable the HTTP and S3 filesystems" not in front_end
