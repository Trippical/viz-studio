import pyarrow as pa
import pytest

from viz.config import Settings
from viz.publish.pii import drop_columns, parse_drop_list, pii_columns, pii_warning

DEFAULT = Settings(storage="local").pii_pattern


def test_default_pattern_flags_common_pii_names():
    cols = ["month", "customer_email", "SSN", "phone_number", "full_name", "home_address", "dob", "salary", "ip", "zip"]
    assert pii_columns(cols, DEFAULT) == [
        "customer_email", "SSN", "phone_number", "full_name", "home_address", "dob", "salary", "ip",
    ]


def test_ip_needs_a_word_boundary():
    assert pii_columns(["ship_date", "zip", "ip_address", "ip"], DEFAULT) == ["ip_address", "ip"]


def test_custom_pattern_and_invalid_pattern():
    assert pii_columns(["secret_thing", "other"], "secret") == ["secret_thing"]
    with pytest.raises(ValueError, match="invalid VIZ_PII_PATTERN"):
        pii_columns(["a"], "(")


def test_warning_text():
    assert pii_warning(["month", "revenue"], DEFAULT) is None
    assert pii_warning(["email", "name", "x"], DEFAULT) == (
        "warning: possible PII columns: email, name (use --drop-columns email,name)"
    )


def test_drop_columns():
    table = pa.table({"a": [1], "b": [2], "c": [3]})
    out = drop_columns(table, ["b"])
    assert out.column_names == ["a", "c"]
    assert drop_columns(table, []).column_names == ["a", "b", "c"]
    with pytest.raises(ValueError, match="unknown column 'zz'"):
        drop_columns(table, ["zz"])


def test_parse_drop_list():
    assert parse_drop_list(None) == []
    assert parse_drop_list("") == []
    assert parse_drop_list("a, b ,,c") == ["a", "b", "c"]
