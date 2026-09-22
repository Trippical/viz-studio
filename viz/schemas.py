# viz/schemas.py
"""Document validation: JSON Schema plus renderer-specific spec rules."""
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator, FormatChecker

FORBIDDEN_SPEC_KEYS = frozenset(
    ["url", "href", "usermeta", "link", "sublink", "graphic", "extraCssText", "appendTo",
     "className", "images", "mapbox", "map", "__proto__", "constructor", "prototype"]
)
PLOTLY_BOUND_KEYS = ("x", "y", "z", "text", "hovertext", "labels", "values", "customdata")
PLOTLY_FORBIDDEN_TRACE_TYPES = frozenset(
    ["scattergeo", "choropleth", "scattermapbox", "choroplethmapbox", "densitymapbox",
     "scattermap", "choroplethmap", "densitymap"]
)

_CANDIDATE_DIRS = (
    Path(__file__).parent / "_schemas",
    Path(__file__).resolve().parents[1] / "schemas",
)


class SchemaError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def schema_dir() -> Path:
    for candidate in _CANDIDATE_DIRS:
        if (candidate / "chart.schema.json").is_file():
            return candidate
    raise FileNotFoundError("schemas directory not found")


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((schema_dir() / f"{name}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _schema_errors(name: str, doc: Any) -> list[str]:
    errors = sorted(_validator(name).iter_errors(doc), key=lambda e: list(e.absolute_path))
    out = []
    for e in errors:
        path = "/".join(str(p) for p in e.absolute_path) or "$"
        out.append(f"{path}: {e.message}")
    return out


def _walk(node: Any, path: str = "spec") -> Iterator[tuple[str, str, Any]]:
    """Yield (path, key, value) for every key in every nested object."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}/{key}"
            yield here, key, value
            yield from _walk(value, here)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, f"{path}/{i}")


def _check_vegalite(spec: dict, columns: set[str]) -> list[str]:
    errors = []
    for path, key, value in _walk(spec):
        if key == "data" and value != {"name": "data"}:
            errors.append(f"{path}: vega-lite data must be exactly {{\"name\": \"data\"}}")
        if key == "values":
            errors.append(f"{path}: inline values are not allowed")
        if key == "mark" and (value == "image" or (isinstance(value, dict) and value.get("type") == "image")):
            errors.append(f"{path}: image marks are not allowed")
    return errors


def _check_echarts(spec: dict, columns: set[str]) -> list[str]:
    errors = []
    for path, key, value in _walk(spec):
        if key == "dataset":
            errors.append(f"{path}: dataset is injected by the viewer and must not be set")
        if key == "data":
            errors.append(f"{path}: inline data is not allowed")
        if key == "formatter" and isinstance(value, str) and "<" in value:
            errors.append(f"{path}: formatter must not contain HTML")
        if key == "renderMode" and value != "richText":
            errors.append(f"{path}: renderMode must be richText")
    return errors


def _check_plotly(spec: dict, columns: set[str]) -> list[str]:
    errors = []
    extra = set(spec) - {"traces", "layout"}
    for key in sorted(extra):
        errors.append(f"spec/{key}: plotly spec allows only traces and layout")
    traces = spec.get("traces")
    if not isinstance(traces, list) or not traces:
        errors.append("spec/traces: must be a non-empty array")
        return errors
    for i, trace in enumerate(traces):
        if not isinstance(trace, dict):
            errors.append(f"spec/traces/{i}: must be an object")
            continue
        if trace.get("type") in PLOTLY_FORBIDDEN_TRACE_TYPES:
            errors.append(f"spec/traces/{i}/type: geo and map traces are not allowed")
        for key in PLOTLY_BOUND_KEYS:
            if key not in trace:
                continue
            binding = trace[key]
            if not isinstance(binding, dict) or set(binding) != {"column"}:
                errors.append(f"spec/traces/{i}/{key}: must be a column binding {{\"column\": name}}")
            elif binding["column"] not in columns:
                errors.append(f"spec/traces/{i}/{key}: unknown column {binding['column']!r}")
    return errors


def _check_stat(spec: dict, columns: set[str]) -> list[str]:
    errors = []
    if isinstance(spec, dict):
        if spec.get("value") not in columns:
            errors.append(f"spec/value: unknown column {spec.get('value')!r}")
        compare = spec.get("compare")
        if isinstance(compare, dict) and compare.get("column") not in columns:
            errors.append(f"spec/compare/column: unknown column {compare.get('column')!r}")
    return errors


_RENDERER_CHECKS = {
    "vega-lite": _check_vegalite,
    "echarts": _check_echarts,
    "plotly": _check_plotly,
    "stat": _check_stat,
}


def validate_chart(doc: Any) -> dict:
    errors = _schema_errors("chart", doc)
    if isinstance(doc, dict) and isinstance(doc.get("spec"), dict) and doc.get("renderer") in _RENDERER_CHECKS:
        columns = {c.get("name") for c in doc.get("data", {}).get("columns", []) if isinstance(c, dict)}
        errors += _RENDERER_CHECKS[doc["renderer"]](doc["spec"], columns)
    if errors:
        raise SchemaError(errors)
    return doc


def validate_dashboard(doc: Any) -> dict:
    errors = _schema_errors("dashboard", doc)
    if isinstance(doc, dict) and isinstance(doc.get("controls"), list):
        seen: set[str] = set()
        for i, control in enumerate(doc["controls"]):
            cid = control.get("id") if isinstance(control, dict) else None
            if cid in seen:
                errors.append(f"controls/{i}/id: duplicate control id {cid!r}")
            if cid is not None:
                seen.add(cid)
    if errors:
        raise SchemaError(errors)
    return doc


def validate_folder(doc: Any) -> dict:
    errors = _schema_errors("folder", doc)
    if errors:
        raise SchemaError(errors)
    return doc
