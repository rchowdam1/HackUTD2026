"""Operator login (§19.3): one password from env, then a signed session cookie.

Other routers protect themselves with `dependencies=[Depends(require_operator)]`.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

COOKIE = "safesignal_session"

router = APIRouter()


def _sign(nonce: str) -> str:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise HTTPException(500, "SESSION_SECRET is not set")
    return hmac.new(secret.encode(), nonce.encode(), hashlib.sha256).hexdigest()


class Login(BaseModel):
    password: str


@router.post("/login")
def login(body: Login, response: Response) -> dict:
    expected = os.environ.get("OPERATOR_PASSWORD")
    if not expected or not hmac.compare_digest(body.password.encode(), expected.encode()):
        raise HTTPException(401, "wrong password")
    nonce = secrets.token_hex(16)
    response.set_cookie(COOKIE, f"{nonce}.{_sign(nonce)}", httponly=True, samesite="strict")
    return {"status": "ok"}


def require_operator(request: Request) -> None:
    nonce, _, sig = request.cookies.get(COOKIE, "").partition(".")
    if not nonce or not hmac.compare_digest(sig, _sign(nonce)):
        raise HTTPException(401, "login required")
