"""Read-only API. Four routes plus health. No writes anywhere."""
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from ..ids import InvalidId, data_key, validate_id
from ..schemas import SchemaError
from ..storage import NotFound
from .documents import DocumentTooLarge, load_chart, load_dashboard, public_chart

router = APIRouter()

MEDIA_TYPES = {"json": "application/json; charset=utf-8", "parquet": "application/octet-stream"}
_RANGE = re.compile(r"^bytes=(\d{0,19})-(\d{0,19})$")


def _id(value: str) -> str:
    try:
        return validate_id(value)
    except InvalidId as err:
        raise HTTPException(status_code=400, detail="invalid id") from err


def _document(loader, request: Request, doc_id: str) -> dict:
    try:
        return loader(request.app.state.storage, request.app.state.settings, doc_id)
    except NotFound as err:
        raise HTTPException(status_code=404, detail="not found") from err
    except DocumentTooLarge as err:
        raise HTTPException(status_code=413, detail=str(err)) from err
    except SchemaError as err:
        raise HTTPException(status_code=422, detail={"errors": err.errors}) from err


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/tree")
async def tree(request: Request):
    return await request.app.state.tree.get()


@router.get("/dashboards/{dashboard_id:path}")
def dashboard(dashboard_id: str, request: Request):
    return _document(load_dashboard, request, _id(dashboard_id))


@router.get("/charts/{chart_id:path}")
def chart(chart_id: str, request: Request):
    return public_chart(_document(load_chart, request, _id(chart_id)))


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None | str:
    """None: no usable range. 'unsatisfiable': 416. Otherwise (start, end) inclusive."""
    if not header:
        return None
    m = _RANGE.match(header.strip())
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return None
    if size == 0:
        return "unsatisfiable"
    first, last = m.group(1), m.group(2)
    if first == "":
        suffix = int(last)
        if suffix == 0:
            return "unsatisfiable"
        return max(size - suffix, 0), size - 1
    start = int(first)
    end = size - 1 if last == "" else min(int(last), size - 1)
    if start >= size or start > end:
        return "unsatisfiable"
    return start, end


@router.api_route("/data/{chart_id:path}", methods=["GET", "HEAD"])
def data(chart_id: str, request: Request):
    chart_id = _id(chart_id)
    doc = _document(load_chart, request, chart_id)
    settings = request.app.state.settings
    storage = request.app.state.storage
    fmt = doc["data"]["format"]
    key = data_key(settings.root_prefix, chart_id, fmt)
    try:
        info = storage.head(key)
    except NotFound as err:
        raise HTTPException(status_code=404, detail="data file not found") from err

    etag = f'"{info.etag}"'
    headers = {
        "ETag": etag,
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'attachment; filename="data.{fmt}"',
        "Cache-Control": "private, max-age=0, must-revalidate",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    rng = _parse_range(request.headers.get("range"), info.size)
    if rng == "unsatisfiable":
        headers["Content-Range"] = f"bytes */{info.size}"
        raise HTTPException(status_code=416, detail="range not satisfiable", headers=headers)

    is_head = request.method == "HEAD"
    if rng is None:
        headers["Content-Length"] = str(info.size)
        if is_head:
            return Response(status_code=200, headers=headers, media_type=MEDIA_TYPES[fmt])
        return StreamingResponse(storage.open(key), status_code=200, headers=headers, media_type=MEDIA_TYPES[fmt])

    start, end = rng
    headers["Content-Range"] = f"bytes {start}-{end}/{info.size}"
    headers["Content-Length"] = str(end - start + 1)
    if is_head:
        return Response(status_code=206, headers=headers, media_type=MEDIA_TYPES[fmt])
    return StreamingResponse(storage.open(key, start=start, end=end), status_code=206, headers=headers,
                              media_type=MEDIA_TYPES[fmt])
