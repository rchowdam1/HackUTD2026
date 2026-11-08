from fastapi import APIRouter

router = APIRouter(tags=["tunnel"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
