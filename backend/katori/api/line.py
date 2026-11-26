"""The serving line over HTTP: join, leave, and a live stream of positions.

Browsers cannot attach a bearer token to an EventSource, so a signed-in client first swaps
its token for a single-use stream ticket and opens the stream with that.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..models import Tenant, User
from ..security import current_user, require_role
from ..services import line
from .deps import kitchen_of

router = APIRouter(prefix="/api", tags=["line"])
_tickets: dict[str, tuple[int, int | None, float]] = {}  # ticket -> (tenant id, user id, expiry)
TICKET_SECONDS = 60
STREAM_SECONDS = 600  # the browser reconnects by itself; this stops abandoned streams piling up
PUSH_EVERY = 2.0
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class Counters(BaseModel):
    open: int = Field(ge=1, le=4)


class Next(BaseModel):
    counter: int = Field(ge=1, le=4)


def _snapshot_json(tenant_id: int, user_id: int | None) -> str:
    with SessionLocal() as db:
        tenant = db.get(Tenant, tenant_id)
        user = db.get(User, user_id) if user_id else None
        return json.dumps(line.snapshot(db, tenant, user), separators=(",", ":"))


async def events(request: Request, tenant_id: int, user_id: int | None) -> AsyncIterator[str]:
    """Server-sent events: the line's state whenever it changes, with a heartbeat in between."""
    started = sent_at = time.monotonic()
    last = ""
    while time.monotonic() - started < STREAM_SECONDS:
        if await request.is_disconnected():
            return
        payload = await run_in_threadpool(_snapshot_json, tenant_id, user_id)
        if payload != last:
            yield f"data: {payload}\n\n"
            last, sent_at = payload, time.monotonic()
        elif time.monotonic() - sent_at > 15:
            yield ": keep-alive\n\n"
            sent_at = time.monotonic()
        await asyncio.sleep(PUSH_EVERY)


@router.get("/line")
def get_line(user: User = Depends(current_user), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    return line.snapshot(db, tenant, user if user.role == "student" else None)


@router.post("/line/join")
def join(user: User = Depends(require_role("student")), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    try:
        return line.join(db, tenant, user)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/line/leave")
def leave(user: User = Depends(require_role("student")), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    return line.leave(db, tenant, user)


@router.post("/line/counters")
def counters(body: Counters, _: User = Depends(require_role("kitchen", "manager")), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    return line.set_counters(db, tenant, body.open)


@router.post("/line/next")
def call_next(body: Next, _: User = Depends(require_role("kitchen", "manager")), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    return line.call_next(db, tenant, body.counter)


@router.post("/line/stream-ticket")
def stream_ticket(user: User = Depends(current_user)) -> dict:
    now = time.monotonic()
    for stale in [key for key, (_, _, expiry) in _tickets.items() if expiry < now]:
        _tickets.pop(stale, None)
    ticket = secrets.token_urlsafe(24)
    _tickets[ticket] = (user.tenant_id, user.id if user.role == "student" else None, now + TICKET_SECONDS)
    return {"ticket": ticket}


@router.get("/line/stream")
async def stream(ticket: str, request: Request) -> StreamingResponse:
    entry = _tickets.pop(ticket, None)
    if entry is None or entry[2] < time.monotonic():
        raise HTTPException(401, "This stream link has expired")
    return StreamingResponse(events(request, entry[0], entry[1]), media_type="text/event-stream", headers=SSE_HEADERS)


def tenant_by_slug(slug: str, db: Session) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        raise HTTPException(404, "No such kitchen")
    return tenant
