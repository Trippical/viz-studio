import hashlib
import json

import pytest

from viz.ids import data_file_name
from viz.storage import get_storage


@pytest.fixture
def storage(settings):
    return get_storage(settings)


def test_json_data_full(client, storage):
    r = client.get("/api/data/sales/revenue-by-region")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-disposition"] == 'attachment; filename="data.json"'
    assert r.headers["cache-control"] == "private, max-age=0, must-revalidate"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["etag"].startswith('"')
    assert int(r.headers["content-length"]) == len(r.content)
    assert len(json.loads(r.content)) == 144


def test_etag_304(client):
    first = client.get("/api/data/sales/revenue-by-region")
    r = client.get("/api/data/sales/revenue-by-region", headers={"If-None-Match": first.headers["etag"]})
    assert r.status_code == 304
    assert r.content == b""


def test_range_request(client):
    full = client.get("/api/data/sales/revenue-by-region").content
    r = client.get("/api/data/sales/revenue-by-region", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.content == full[10:20]
    assert r.headers["content-range"] == f"bytes 10-19/{len(full)}"
    assert r.headers["content-length"] == "10"
    r = client.get("/api/data/sales/revenue-by-region", headers={"Range": "bytes=-5"})
    assert r.status_code == 206
    assert r.content == full[-5:]
    r = client.get("/api/data/sales/revenue-by-region", headers={"Range": f"bytes={len(full) - 3}-"})
    assert r.content == full[-3:]


def test_unsatisfiable_range_416(client):
    full = client.get("/api/data/sales/revenue-by-region").content
    r = client.get("/api/data/sales/revenue-by-region", headers={"Range": f"bytes={len(full) + 5}-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(full)}"


def test_malformed_range_is_ignored(client):
    r = client.get("/api/data/sales/revenue-by-region", headers={"Range": "items=1-2"})
    assert r.status_code == 200


def test_parquet_media_type_and_missing_file(client, storage):
    name = data_file_name(hashlib.sha256(b"PAR1").hexdigest(), "parquet")
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc.update({"id": "sales/big", "renderer": "vega-lite", "spec": {"data": {"name": "data"}, "mark": "bar"},
                "data": {**doc["data"], "format": "parquet", "file": name, "lane": "large", "bytes": 4},
                "aggregate": "SELECT 1"})
    storage.put("viz/charts/sales/big/chart.json", json.dumps(doc).encode(), "application/json")
    assert client.get("/api/data/sales/big").status_code == 404   # chart exists, data file does not
    storage.put(f"viz/charts/sales/big/{name}", b"PAR1", "application/octet-stream")
    r = client.get("/api/data/sales/big")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"] == 'attachment; filename="data.parquet"'
    assert r.content == b"PAR1"


def test_data_for_invalid_chart_is_422(client, storage):
    storage.put("viz/charts/sales/bad/chart.json", b"{}", "application/json")
    assert client.get("/api/data/sales/bad").status_code == 422


def test_data_file_with_trailing_newline_is_422_not_500(client, storage):
    # jsonschema's `pattern` check lets a trailing "\n" through (Python's `$`
    # matches just before it); data_key()'s fullmatch does not, so without the
    # validate_chart fix this reaches an unhandled ValueError and a 500.
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc.update({"id": "sales/bad-newline", "data": {**doc["data"], "file": doc["data"]["file"] + "\n"}})
    storage.put("viz/charts/sales/bad-newline/chart.json", json.dumps(doc).encode(), "application/json")
    r = client.get("/api/data/sales/bad-newline")
    assert r.status_code == 422


def test_data_invalid_id_400_and_missing_404(client):
    assert client.get("/api/data/Bad").status_code == 400
    assert client.get("/api/data/sales/nope").status_code == 404


def test_head_matches_get_headers_without_body(client):
    get = client.get("/api/data/sales/revenue-by-region")
    head = client.head("/api/data/sales/revenue-by-region")
    assert head.status_code == 200
    assert head.content == b""
    for name in ("etag", "accept-ranges", "content-disposition", "cache-control", "content-length", "content-type"):
        assert head.headers[name] == get.headers[name]
    ranged = client.head("/api/data/sales/revenue-by-region", headers={"Range": "bytes=0-9"})
    assert ranged.status_code == 206
    assert ranged.content == b""
    assert ranged.headers["content-range"] == f"bytes 0-9/{get.headers['content-length']}"


def test_absurd_range_digits_are_ignored(client):
    r = client.get("/api/data/sales/revenue-by-region", headers={"Range": "bytes=" + "9" * 5000 + "-"})
    assert r.status_code == 200


def test_suffix_range_on_empty_file_is_416(client, storage):
    name = data_file_name(hashlib.sha256(b"").hexdigest(), "json")
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc.update({"id": "sales/empty", "data": {**doc["data"], "file": name, "rows": 0, "bytes": 0}})
    storage.put("viz/charts/sales/empty/chart.json", json.dumps(doc).encode(), "application/json")
    storage.put(f"viz/charts/sales/empty/{name}", b"", "application/json")
    r = client.get("/api/data/sales/empty", headers={"Range": "bytes=-5"})
    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */0"
    r = client.get("/api/data/sales/empty")
    assert r.status_code == 200
    assert r.content == b""
    assert r.headers["content-length"] == "0"


def test_data_route_serves_the_file_that_chart_json_names(client, storage):
    doc = json.loads(storage.get("viz/charts/sales/revenue-by-region/chart.json"))
    named = storage.get(f"viz/charts/sales/revenue-by-region/{doc['data']['file']}")
    # A stray legacy file and an older generation sit next to it; neither is served.
    storage.put("viz/charts/sales/revenue-by-region/data.json", b"[]", "application/json")
    storage.put("viz/charts/sales/revenue-by-region/data.0000000000000000.json", b"[1]", "application/json")
    r = client.get("/api/data/sales/revenue-by-region")
    assert r.status_code == 200
    assert r.content == named


def test_data_route_404_when_the_named_file_is_missing(client, storage):
    doc = json.loads(storage.get("viz/charts/sales/revenue-by-region/chart.json"))
    storage.delete(f"viz/charts/sales/revenue-by-region/{doc['data']['file']}")
    storage.put("viz/charts/sales/revenue-by-region/data.json", b"[]", "application/json")
    r = client.get("/api/data/sales/revenue-by-region")
    assert r.status_code == 404
    assert r.json() == {"detail": "data file not found"}
