"""Catalogs and schemas that viz query must never read. Comes from VIZ_QUERY_DENY only."""
import re

_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_THREE = re.compile(rf"\b({_NAME})\.({_NAME})\.({_NAME})\b")
_TWO = re.compile(rf"\b({_NAME})\.({_NAME})\b")


def parse_deny(text: str) -> list[str]:
    return [part.strip().lower() for part in (text or "").split(",") if part.strip()]


def denied_references(sql: str, deny: str) -> list[str]:
    entries = parse_deny(deny)
    if not entries:
        return []
    catalogs = {e for e in entries if "." not in e}
    schemas = {e for e in entries if "." in e}
    schema_names = {e.split(".", 1)[1] for e in schemas}
    hits: set[str] = set()

    def three(m: re.Match) -> str:
        cat, sch, tbl = (g.lower() for g in m.groups())
        if cat in catalogs or f"{cat}.{sch}" in schemas:
            hits.add(f"{cat}.{sch}.{tbl}")
        return " "

    rest = _THREE.sub(three, sql)
    for m in _TWO.finditer(rest):
        first, second = (g.lower() for g in m.groups())
        if first in catalogs or first in schema_names:
            hits.add(f"{first}.{second}")
    return sorted(hits)
