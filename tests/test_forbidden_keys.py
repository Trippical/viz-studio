"""A37: the spec keys the server rejects and the keys the browser sanitizer rejects are
one list. Plotly and ECharts are gone, so their keys are not in it."""
import copy
import json
import re
from pathlib import Path

import pytest

from viz import schemas

REPO = Path(__file__).resolve().parents[1]
SANITIZER = REPO / "web" / "src" / "renderers" / "vegaLiteSanitize.ts"
FIXTURE = REPO / "tests" / "fixtures" / "valid" / "chart-vegalite.json"
PROTOTYPE_KEYS = {"__proto__", "constructor", "prototype"}


def _browser_forbidden_keys() -> set[str]:
    text = SANITIZER.read_text(encoding="utf-8")
    match = re.search(r"const FORBIDDEN_KEYS = new Set\(\[(.*?)\]\)", text, re.DOTALL)
    assert match, "vegaLiteSanitize.ts must declare FORBIDDEN_KEYS as new Set([...])"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _schema_forbidden_keys() -> set[str]:
    schema = json.loads((REPO / "schemas" / "chart.schema.json").read_text(encoding="utf-8"))
    return set(schema["$defs"]["noForbiddenKeys"]["then"]["propertyNames"]["not"]["enum"])


def test_schema_list_is_the_browser_list_plus_prototype_keys():
    browser = _browser_forbidden_keys()
    assert browser, "no keys parsed from vegaLiteSanitize.ts"
    assert _schema_forbidden_keys() == browser | PROTOTYPE_KEYS


def test_no_plotly_or_echarts_keys_remain():
    leftovers = {"link", "sublink", "graphic", "extraCssText", "appendTo", "className", "images", "mapbox", "map"}
    assert not (_schema_forbidden_keys() & leftovers)


@pytest.mark.parametrize("key", sorted(_browser_forbidden_keys() | PROTOTYPE_KEYS))
def test_server_rejects_every_forbidden_key_at_depth(key):
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc = copy.deepcopy(doc)
    doc["spec"]["encoding"]["x"][key] = {"field": "month"}
    with pytest.raises(schemas.SchemaError) as excinfo:
        schemas.validate_chart(doc)
    assert key in str(excinfo.value)


def test_fixture_uses_the_vega_lite_v6_schema():
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert doc["spec"]["$schema"] == "https://vega.github.io/schema/vega-lite/v6.json"
