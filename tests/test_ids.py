import hashlib

import pytest
from viz import ids


@pytest.mark.parametrize("value", ["a", "sales", "sales/emea", "revenue-by-region", "a1/b-2/c3"])
def test_valid_ids(value):
    assert ids.validate_id(value) == value


@pytest.mark.parametrize(
    "value",
    ["", "Sales", "sales/", "/sales", "sales//emea", "sales/../x", "a b", "a_b", "-a", "a-", "a/.b", "x" * 513],
)
def test_invalid_ids(value):
    with pytest.raises(ids.InvalidId):
        ids.validate_id(value)


def test_normalize_root():
    assert ids.normalize_root("viz") == "viz/"
    assert ids.normalize_root("viz/") == "viz/"
    assert ids.normalize_root("/viz/") == "viz/"
    assert ids.normalize_root("") == ""


def test_keys():
    assert ids.chart_key("viz/", "sales/emea/rev") == "viz/charts/sales/emea/rev/chart.json"
    assert ids.data_key("viz/", "sales/emea/rev", "data.0123456789abcdef.json") == "viz/charts/sales/emea/rev/data.0123456789abcdef.json"
    assert ids.data_key("viz/", "sales/emea/rev", "data.0123456789abcdef.parquet") == "viz/charts/sales/emea/rev/data.0123456789abcdef.parquet"
    assert ids.dashboard_key("viz/", "sales/overview") == "viz/dashboards/sales/overview.json"
    assert ids.folder_key("viz/", "charts", "sales") == "viz/charts/sales/_folder.json"
    assert ids.folder_key("viz/", "dashboards", "") == "viz/dashboards/_folder.json"


@pytest.mark.parametrize("name", [
    "json", "data.json", "data.parquet", "data.0123456789ABCDEF.json", "data.0123456789abcdef.csv",
    "data.0123456789abcde.json", "../data.0123456789abcdef.json", "chart.json", "data.0123456789abcdef.json\n",
])
def test_data_key_rejects_names_that_are_not_content_addressed(name):
    with pytest.raises(ValueError):
        ids.data_key("viz/", "a", name)


def test_data_file_name_is_the_first_16_hex_of_the_sha256():
    digest = hashlib.sha256(b"[]").hexdigest()
    assert ids.data_file_name(digest, "json") == f"data.{digest[:16]}.json"
    assert ids.data_file_name(digest, "parquet") == f"data.{digest[:16]}.parquet"
    with pytest.raises(ValueError):
        ids.data_file_name(digest, "csv")
    with pytest.raises(ValueError):
        ids.data_file_name("abc", "json")


def test_is_ancestor():
    assert ids.is_ancestor("a", "a/b")
    assert ids.is_ancestor("a/b", "a/b/c")
    assert not ids.is_ancestor("a", "ab")
    assert not ids.is_ancestor("a/b", "a")
