"""The Katori API. Run with:  uvicorn katori.main:app"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from . import __version__
from .api import auth, kitchen, line, manager, public, resident
from .config import get_settings
from .db import SessionLocal, init_db
from .models import Tenant
from .services import upkeep

log = logging.getLogger("katori")


def prepare() -> None:
    """Create tables, build the demo hostel if this is a fresh demo server, and bring every kitchen up to date."""
    settings = get_settings()
    init_db()
    with SessionLocal() as db:
        if settings.demo_mode and db.scalar(select(Tenant.id).limit(1)) is None:
            from .seed import seed_demo

            log.info("Empty database: building the demo hostel (this takes about a minute)")
            seed_demo(db)
            db.commit()
        for tenant in db.scalars(select(Tenant)).all():
            upkeep.tick(db, tenant, force=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    prepare()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Katori", version=__version__, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    for module in (public, auth, resident, line, kitchen, manager):
        app.include_router(module.router)
    if settings.web_dir.is_dir():
        # The built web app, served from the same origin as the API.
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app


app = create_app()
