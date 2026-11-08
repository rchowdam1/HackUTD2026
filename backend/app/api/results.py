"""GET /results/latest (Track C's file, served unchanged) and GET /aggregates."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Response

from app import storage
from app.api.auth import require_operator

RESULTS = Path(__file__).resolve().parents[3] / "results" / "latest.json"

router = APIRouter(dependencies=[Depends(require_operator)])


@router.get("/results/latest")
def latest() -> Response:
    if not RESULTS.exists():
        return Response('{"status":"pending"}', media_type="application/json")
    return Response(RESULTS.read_bytes(), media_type="application/json")


@router.get("/aggregates")
def aggregates() -> dict:
    return storage.aggregates()
