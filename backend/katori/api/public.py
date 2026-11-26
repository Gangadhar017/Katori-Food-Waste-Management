"""Endpoints that need no sign-in: health, the landing page's numbers and the dining-hall display."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import __version__, clock
from ..config import get_settings
from ..db import get_db
from ..meals import MEALS, window_utc
from ..models import Dish, MealService, MenuEntry, Tenant
from ..services import analytics, line, upkeep
from .deps import dish_out, sitting_state
from .line import SSE_HEADERS, events, tenant_by_slug

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "demo": get_settings().demo_mode}


@router.get("/public/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    tenant = db.scalar(select(Tenant).where(Tenant.is_demo.is_(True)).order_by(Tenant.id))
    if tenant is None:
        raise HTTPException(404, "No demo kitchen on this server")
    upkeep.tick(db, tenant)
    return {"slug": tenant.slug, "demo": get_settings().demo_mode, **analytics.public_summary(db, tenant)}


@router.get("/public/{slug}/board")
def board(slug: str, db: Session = Depends(get_db)) -> dict:
    """What the screen in the dining hall shows: the line, today's menu, yesterday's waste."""
    tenant = tenant_by_slug(slug, db)
    upkeep.tick(db, tenant)
    now = clock.utcnow()
    today = clock.local_today(tenant.timezone)
    menus: dict[str, list[Dish]] = {meal: [] for meal in MEALS}
    for entry, dish in db.execute(
        select(MenuEntry, Dish)
        .join(Dish, Dish.id == MenuEntry.dish_id)
        .where(MenuEntry.tenant_id == tenant.id, MenuEntry.day == today)
        .order_by(MenuEntry.position)
    ):
        menus[entry.meal].append(dish)
    sittings = []
    for meal in MEALS:
        start, end = window_utc(today, meal, tenant.timezone)
        sittings.append(
            {
                "meal": meal,
                "starts_at": clock.iso_utc(start),
                "ends_at": clock.iso_utc(end),
                "state": sitting_state(now, today, meal, tenant.timezone),
                "dishes": [dish_out(d) for d in menus[meal]],
            }
        )
    yesterday = today - timedelta(days=1)
    logged = db.scalars(
        select(MealService).where(MealService.tenant_id == tenant.id, MealService.day == yesterday, MealService.served.is_not(None))
    ).all()
    served = sum(s.served or 0 for s in logged)
    plate = sum(s.plate_waste_kg or 0 for s in logged)
    return {
        "hostel": tenant.name,
        "city": tenant.city,
        "today": today.isoformat(),
        "sittings": sittings,
        "yesterday": {
            "served": served,
            "plate_waste_kg": round(plate, 1),
            "plate_waste_per_head_g": round(plate * 1000 / served) if served else None,
            "plates": round(plate / analytics.KG_PER_MEAL),
        },
        "line": line.snapshot(db, tenant),
    }


@router.get("/public/{slug}/board/stream")
async def board_stream(slug: str, request: Request, db: Session = Depends(get_db)) -> StreamingResponse:
    tenant = tenant_by_slug(slug, db)
    return StreamingResponse(events(request, tenant.id, None), media_type="text/event-stream", headers=SSE_HEADERS)
