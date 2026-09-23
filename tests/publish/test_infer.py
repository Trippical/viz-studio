import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from viz.publish.infer import (
    UnsupportedColumn, contract_type, infer_columns, rows_from_table, table_from_file, table_from_rows,
)


def _typed_table() -> pa.Table:
    return pa.table({
        "s": pa.array(["a", None]),
        "i": pa.array([1, 2], pa.int64()),
        "f": pa.array([1.5, float("nan")]),
        "b": pa.array([True, False]),
        "d": pa.array([date(2024, 1, 31), None]),
        "t": pa.array([datetime(2024, 1, 31, 10, 30, 0), None], pa.timestamp("us")),
        "dec": pa.array([Decimal("1.25"), None], pa.decimal128(10, 2)),
    })


def test_contract_type_covers_the_six_types():
    assert contract_type(pa.string()) == "string"
    assert contract_type(pa.large_string()) == "string"
    assert contract_type(pa.int32()) == "integer"
    assert contract_type(pa.float64()) == "number"
    assert contract_type(pa.decimal128(10, 2)) == "number"
    assert contract_type(pa.bool_()) == "boolean"
    assert contract_type(pa.date32()) == "date"
    assert contract_type(pa.timestamp("ms", tz="UTC")) == "timestamp"


@pytest.mark.parametrize("arrow_type", [pa.list_(pa.int64()), pa.struct([("a", pa.int64())]), pa.binary()])
def test_unsupported_types_raise(arrow_type):
    with pytest.raises(UnsupportedColumn):
        contract_type(arrow_type)


def test_infer_columns_in_table_order():
    assert infer_columns(_typed_table()) == [
        {"name": "s", "type": "string"}, {"name": "i", "type": "integer"}, {"name": "f", "type": "number"},
        {"name": "b", "type": "boolean"}, {"name": "d", "type": "date"}, {"name": "t", "type": "timestamp"},
        {"name": "dec", "type": "number"},
    ]


def test_infer_columns_rejects_bad_names():
    table = pa.table({"region name": pa.array(["x"])})
    with pytest.raises(UnsupportedColumn, match="region name"):
        infer_columns(table)
    with pytest.raises(UnsupportedColumn):
        infer_columns(pa.table({"1st": pa.array([1])}))


def test_infer_columns_names_the_unsupported_column():
    with pytest.raises(UnsupportedColumn, match="'tags'"):
        infer_columns(pa.table({"tags": pa.array([[1, 2]])}))


def test_rows_from_table_is_json_safe():
    rows = rows_from_table(_typed_table())
    assert rows[0] == {"s": "a", "i": 1, "f": 1.5, "b": True, "d": "2024-01-31", "t": "2024-01-31T10:30:00Z", "dec": 1.25}
    assert rows[1] == {"s": None, "i": 2, "f": None, "b": False, "d": None, "t": None, "dec": None}
    json.dumps(rows)  # must not raise


def test_rows_from_table_converts_aware_timestamps_to_utc():
    t = pa.array([datetime(2024, 1, 31, 12, 0, 0, tzinfo=timezone.utc)], pa.timestamp("us", tz="+02:00"))
    assert rows_from_table(pa.table({"t": t}))[0]["t"] == "2024-01-31T12:00:00Z"


def test_rows_from_table_drops_infinities():
    rows = rows_from_table(pa.table({"f": pa.array([math.inf, -math.inf, 2.0])}))
    assert [r["f"] for r in rows] == [None, None, 2.0]


def test_table_from_rows_promotes_iso_strings():
    table = table_from_rows([
        {"d": "2024-01-01", "t": "2024-01-01T10:00:00Z", "s": "2024", "n": 1.5, "i": 3},
        {"d": None, "t": "2024-01-02 11:00:00", "s": "x", "n": 2.0, "i": 4},
    ])
    assert infer_columns(table) == [
        {"name": "d", "type": "date"}, {"name": "t", "type": "timestamp"}, {"name": "s", "type": "string"},
        {"name": "n", "type": "number"}, {"name": "i", "type": "integer"},
    ]
    assert rows_from_table(table)[1]["t"] == "2024-01-02T11:00:00Z"


def test_table_from_rows_round_trips():
    original = rows_from_table(_typed_table())
    again = rows_from_table(table_from_rows(original))
    assert again == original


def test_table_from_file_csv_json_parquet(tmp_path):
    csv = tmp_path / "in.csv"
    csv.write_text("month,region,revenue,orders\n2024-01-01,EMEA,10.5,3\n2024-02-01,NA,20,4\n", encoding="utf-8")
    t = table_from_file(csv)
    assert infer_columns(t) == [
        {"name": "month", "type": "date"}, {"name": "region", "type": "string"},
        {"name": "revenue", "type": "number"}, {"name": "orders", "type": "integer"},
    ]
    assert len(t) == 2

    js = tmp_path / "in.json"
    js.write_text(json.dumps(rows_from_table(t)), encoding="utf-8")
    assert rows_from_table(table_from_file(js)) == rows_from_table(t)

    pqf = tmp_path / "in.parquet"
    pq.write_table(t, pqf)
    assert rows_from_table(table_from_file(pqf)) == rows_from_table(t)


def test_table_from_file_rejects_other_suffixes(tmp_path):
    other = tmp_path / "in.xlsx"
    other.write_bytes(b"")
    with pytest.raises(UnsupportedColumn, match="xlsx"):
        table_from_file(other)


def test_table_from_file_json_must_be_an_array_of_objects(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(UnsupportedColumn, match="array of objects"):
        table_from_file(bad)


def test_table_from_rows_rejects_integers_beyond_int64():
    with pytest.raises(UnsupportedColumn, match="cannot infer column types"):
        table_from_rows([{"i": 99999999999999999999}])
