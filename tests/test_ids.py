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
    assert ids.data_key("viz/", "sales/emea/rev", "json") == "viz/charts/sales/emea/rev/data.json"
    assert ids.data_key("viz/", "sales/emea/rev", "parquet") == "viz/charts/sales/emea/rev/data.parquet"
    assert ids.dashboard_key("viz/", "sales/overview") == "viz/dashboards/sales/overview.json"
    assert ids.folder_key("viz/", "charts", "sales") == "viz/charts/sales/_folder.json"
    assert ids.folder_key("viz/", "dashboards", "") == "viz/dashboards/_folder.json"


def test_data_key_rejects_unknown_format():
    with pytest.raises(ValueError):
        ids.data_key("viz/", "a", "csv")


def test_is_ancestor():
    assert ids.is_ancestor("a", "a/b")
    assert ids.is_ancestor("a/b", "a/b/c")
    assert not ids.is_ancestor("a", "ab")
    assert not ids.is_ancestor("a/b", "a")
