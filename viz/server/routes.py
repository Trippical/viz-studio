"""Read-only API. Four routes plus health. No writes anywhere."""
from fastapi import APIRouter, HTTPException, Request

from ..ids import InvalidId, validate_id
from ..schemas import SchemaError
from ..storage import NotFound
from .documents import DocumentTooLarge, load_chart, load_dashboard, public_chart

router = APIRouter()


def _id(value: str) -> str:
    try:
        return validate_id(value)
    except InvalidId:
        raise HTTPException(status_code=400, detail="invalid id")


def _document(loader, request: Request, doc_id: str) -> dict:
    try:
        return loader(request.app.state.storage, request.app.state.settings, doc_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="not found")
    except DocumentTooLarge as err:
        raise HTTPException(status_code=413, detail=str(err))
    except SchemaError as err:
        raise HTTPException(status_code=422, detail={"errors": err.errors})


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
