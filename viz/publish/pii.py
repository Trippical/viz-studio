"""Warn about column names that look like personal data, and drop columns on request."""
import re

import pyarrow as pa


def _compile(pattern: str) -> re.Pattern:
    try:
        return re.compile(pattern)
    except re.error as err:
        raise ValueError(f"invalid VIZ_PII_PATTERN: {err}") from err


def pii_columns(columns: list[str], pattern: str) -> list[str]:
    rx = _compile(pattern)
    return [name for name in columns if rx.search(name)]


def pii_warning(columns: list[str], pattern: str) -> str | None:
    hits = pii_columns(columns, pattern)
    if not hits:
        return None
    return f"warning: possible PII columns: {', '.join(hits)} (use --drop-columns {','.join(hits)})"


def parse_drop_list(text: str | None) -> list[str]:
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def drop_columns(table: pa.Table, names: list[str]) -> pa.Table:
    for name in names:
        if name not in table.column_names:
            raise ValueError(f"unknown column {name!r}")
    keep = [c for c in table.column_names if c not in names]
    return table.select(keep)
