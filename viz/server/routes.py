"""Read-only API. Four routes plus health. No writes anywhere."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
