# viz/schemas.py
"""Document validation: JSON Schema plus renderer-specific spec rules."""
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator, FormatChecker

from . import ids

_CANDIDATE_DIRS = (
    Path(__file__).parent / "_schemas",
    Path(__file__).resolve().parents[1] / "schemas",
)

# Deeper documents are refused before JSON Schema runs: the validator and the spec
# walks below recurse once per level, and a few hundred levels of nested arrays
# raise RecursionError. Real Vega-Lite specs stay far below this.
MAX_NESTING_DEPTH = 64


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


def nesting_depth_exceeds(doc: Any, limit: int = MAX_NESTING_DEPTH) -> bool:
    """True when objects and arrays nest deeper than limit. Iterative, so it cannot
    itself overflow the stack. A scalar is depth 0; {"a": 1} and [1] are depth 1."""
    stack = [(doc, 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict):
            children = list(node.values())
        elif isinstance(node, list):
            children = node
        else:
            continue
        if depth + 1 > limit:
            return True
        for child in children:
            stack.append((child, depth + 1))
    return False


def _depth_errors(doc: Any) -> list[str]:
    if nesting_depth_exceeds(doc):
        return [f"$: nesting deeper than {MAX_NESTING_DEPTH} levels"]
    return []


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


# `columns` is accepted for a uniform signature with the other renderer
# checks and is intentionally unchecked here: Vega-Lite specs may legitimately
# reference fields produced by transforms (calculate, aggregate, window),
# which are not in the declared column set.
def _check_vegalite(spec: dict, columns: set[str]) -> list[str]:
    errors = []
    if spec.get("data") != {"name": "data"}:
        errors.append("spec/data: top-level data must be exactly {\"name\": \"data\"}")
    for path, key, value in _walk(spec):
        # Same rules as web/src/renderers/vegaLiteSanitize.ts (plan 5c, A5 and A6).
        if key == "data" and path != "spec/data":
            errors.append(f"{path}: data is only allowed at the top level")
        if key in ("sequence", "graticule", "sphere"):
            errors.append(f"{path}: data generator \"{key}\" is not allowed")
        if key == "bind" and isinstance(value, dict) and "element" in value:
            errors.append(f"{path}: bind.element is not allowed")
        if key == "values":
            errors.append(f"{path}: inline values are not allowed")
        if key == "datasets":
            errors.append(f"{path}: inline datasets are not allowed")
        if key == "mark" and (value == "image" or (isinstance(value, dict) and value.get("type") == "image")):
            errors.append(f"{path}: image marks are not allowed")
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
    "stat": _check_stat,
}


def validate_chart(doc: Any) -> dict:
    depth = _depth_errors(doc)
    if depth:
        raise SchemaError(depth)
    errors = _schema_errors("chart", doc)
    data = doc.get("data") if isinstance(doc, dict) else None
    file_name = data.get("file") if isinstance(data, dict) else None
    if (
        isinstance(file_name, str)
        and not ids.DATA_FILE_PATTERN.fullmatch(file_name)
        and not any(e.startswith("data/file:") for e in errors)
    ):
        errors.append("data/file: must be data.<16 hex>.<json|parquet>")
    renderer = doc.get("renderer") if isinstance(doc, dict) else None
    if (
        isinstance(doc, dict)
        and isinstance(doc.get("spec"), dict)
        and isinstance(renderer, str)
        and renderer in _RENDERER_CHECKS
    ):
        data = doc.get("data")
        data_columns = data.get("columns") if isinstance(data, dict) else None
        columns = {
            c.get("name") for c in data_columns if isinstance(c, dict)
        } if isinstance(data_columns, list) else set()
        errors += _RENDERER_CHECKS[renderer](doc["spec"], columns)
    if errors:
        raise SchemaError(errors)
    return doc


def validate_dashboard(doc: Any) -> dict:
    depth = _depth_errors(doc)
    if depth:
        raise SchemaError(depth)
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
    depth = _depth_errors(doc)
    if depth:
        raise SchemaError(depth)
    errors = _schema_errors("folder", doc)
    if errors:
        raise SchemaError(errors)
    return doc
