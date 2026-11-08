"""Operator login (§19.3): one password from env, then a signed session cookie.

Sessions are also stored server-side (hashed id + expiry), so they expire after
SESSION_TTL_S and POST /logout revokes them. Failed logins are throttled per client.
Other routers protect themselves with `dependencies=[Depends(require_operator)]`.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app import storage

COOKIE = "safesignal_session"
SESSION_TTL_S = 12 * 3600
MAX_FAILURES = 5  # failed logins per client within FAILURE_WINDOW_S before 429
FAILURE_WINDOW_S = 300

router = APIRouter()
_failures: dict[str, list[float]] = {}  # client host -> recent failed-login times


def _sign(nonce: str) -> str:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise HTTPException(500, "SESSION_SECRET is not set")
    return hmac.new(secret.encode(), nonce.encode(), hashlib.sha256).hexdigest()


def _id_hash(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


def _https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


class Login(BaseModel):
    password: str


@router.post("/login")
def login(body: Login, request: Request, response: Response) -> dict:
    client = request.client.host if request.client else "?"
    now = time.monotonic()
    recent = [t for t in _failures.get(client, []) if now - t < FAILURE_WINDOW_S]
    if len(recent) >= MAX_FAILURES:
        retry = int(FAILURE_WINDOW_S - (now - recent[0])) + 1
        raise HTTPException(429, "too many failed logins", headers={"Retry-After": str(retry)})
    expected = os.environ.get("OPERATOR_PASSWORD")
    if not expected or not hmac.compare_digest(body.password.encode(), expected.encode()):
        _failures[client] = recent + [now]
        raise HTTPException(401, "wrong password")
    _failures.pop(client, None)
    nonce = secrets.token_hex(16)
    storage.add_session(_id_hash(nonce), time.time() + SESSION_TTL_S)
    response.set_cookie(COOKIE, f"{nonce}.{_sign(nonce)}", max_age=SESSION_TTL_S, httponly=True,
                        samesite="strict", secure=_https(request))
    return {"status": "ok"}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    nonce, _, _ = request.cookies.get(COOKIE, "").partition(".")
    if nonce:
        storage.delete_session(_id_hash(nonce))
    response.delete_cookie(COOKIE, httponly=True, samesite="strict", secure=_https(request))
    return {"status": "ok"}


def require_operator(request: Request) -> None:
    nonce, _, sig = request.cookies.get(COOKIE, "").partition(".")
    if not nonce or not hmac.compare_digest(sig, _sign(nonce)) or not storage.session_valid(_id_hash(nonce)):
        raise HTTPException(401, "login required")
