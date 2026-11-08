"""FastAPI app factory. Run: `uvicorn app.main:app`.

Routers are auto-discovered: every module in `app.api` and `app.sms` (including
the package itself) that defines a module-level `router` is mounted. Nobody
edits this file to add a route.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import Response
from fastapi.routing import APIRoute

from app import asr, intent, storage

ROUTER_PACKAGES = ("app.api", "app.sms")


def discover_routers() -> list[APIRouter]:
    routers = []
    for pkg_name in ROUTER_PACKAGES:
        pkg = importlib.import_module(pkg_name)
        modules = [pkg] + [
            importlib.import_module(f"{pkg_name}.{m.name}")
            for m in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name)
        ]
        routers += [m.router for m in modules if isinstance(getattr(m, "router", None), APIRouter)]
    return routers


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init()
    asr.preload()
    intent.preload()
    yield


def create_app() -> FastAPI:
    # /docs, /redoc and /openapi.json map every route; only serve them when asked (API_DOCS=on, local dev).
    docs = os.environ.get("API_DOCS", "").strip().lower() == "on"
    app = FastAPI(title="CallSafe", lifespan=lifespan, docs_url="/docs" if docs else None,
                  redoc_url="/redoc" if docs else None, openapi_url="/openapi.json" if docs else None)
    routers = discover_routers()
    for router in routers:
        app.include_router(router)
    # Routes tagged "tunnel" (Twilio's webhooks, /health) are the only ones reachable through the
    # cloudflared tunnel (scripts/demo_up); the console and API stay localhost-only.
    tunnel_paths = {r.path for router in routers for r in router.routes if isinstance(r, APIRoute) and "tunnel" in r.tags}

    @app.middleware("http")
    async def tunnel_only_twilio(request: Request, call_next):
        # Cloudflare sets Cf-Connecting-Ip on every request it forwards and a client can't strip it, so
        # its presence means "came in through the tunnel".
        if "cf-connecting-ip" in request.headers and request.url.path not in tunnel_paths:
            return Response(status_code=404)
        return await call_next(request)

    return app


app = create_app()
