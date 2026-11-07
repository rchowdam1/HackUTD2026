"""FastAPI app factory. Run: `uvicorn app.main:app`.

Routers are auto-discovered: every module in `app.api` and `app.sms` (including
the package itself) that defines a module-level `router` is mounted. Nobody
edits this file to add a route.
"""
from __future__ import annotations

import importlib
import pkgutil
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app import asr, storage

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
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Safe Signal", lifespan=lifespan)
    for router in discover_routers():
        app.include_router(router)
    return app


app = create_app()
