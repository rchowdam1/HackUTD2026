"""Operator API (Track B owns after the skeleton merges).

Any module in app.api or app.sms that defines `router` is mounted by main.py.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
