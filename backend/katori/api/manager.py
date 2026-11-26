"""The mess manager's view: waste, forecasts, the models behind them and the weekly food chart."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import clock
from ..db import get_db
from ..meals import MEALS
from ..ml import pipeline, registry
from ..models import Dish, MenuTemplate, ModelRun, Tenant, User
from ..security import require_role
from ..services import analytics, upkeep
from ..sim.engine import rebuild_future_menu
from .deps import kitchen_of, tenant_out

router = APIRouter(prefix="/api/manager", tags=["manager"])
manager = require_role("manager")
SWAPPABLE = {"breakfast", "dal", "sabzi", "special", "snack", "dessert"}
MODEL_TITLES = {
    "headcount_cook": ("Head count at cut-off", "residents", "Runs when skip notices close; this is what the kitchen cooks from."),
    "headcount_outlook": ("Head count, week ahead", "residents", "Plans the coming week before notices are in. Weaker around holidays."),
    "portion": ("Portion per head", "kg per dish", "How much of each dish one diner really eats, given what else is on the counter."),
    "wait": ("Queue wait", "seconds", "How long until someone joining the line now is served."),
}


class SlotBody(BaseModel):
    weekday: int = Field(ge=0, le=6)
    meal: str
    dish_ids: list[int] = Field(min_length=1, max_length=8)


class SettingsBody(BaseModel):
    service_level: float = Field(ge=0.8, le=0.99)


@router.get("/overview")
def overview(days: int = Query(28, ge=7, le=126), _: User = Depends(manager), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    return {"tenant": tenant_out(tenant), **analytics.overview(db, tenant, days)}


@router.get("/waste")
def waste(days: int = Query(28, ge=7, le=126), _: User = Depends(manager), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    return analytics.waste_breakdown(db, tenant, days)


@router.get("/forecast")
def forecast(_: User = Depends(manager), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    return analytics.forecast_view(db, tenant)


@router.get("/models")
def models(_: User = Depends(manager), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    cards = []
    for kind, (title, unit, blurb) in MODEL_TITLES.items():
        run = registry.champion(db, tenant.id, kind)
        if run is None:
            cards.append({"kind": kind, "title": title, "unit": unit, "blurb": blurb, "trained": False})
            continue
        cards.append(
            {
                "kind": kind,
                "title": title,
                "unit": unit,
                "blurb": blurb,
                "trained": True,
                "run_id": run.id,
                "algorithm": run.algorithm,
                "trained_at": clock.iso_utc(run.trained_at),
                "train_through": run.train_through.isoformat() if run.train_through else None,
                "rows": run.n_rows,
                "metrics": run.metrics,
                "candidates": run.detail.get("candidates", []),
                "importance": run.detail.get("importance", []),
                "by_meal": run.detail.get("by_meal", {}),
                "policy": run.detail.get("policy", {}),
            }
        )
    history = db.scalars(select(ModelRun).where(ModelRun.tenant_id == tenant.id).order_by(ModelRun.id.desc()).limit(40)).all()
    return {
        "models": cards,
        "runs": [
            {
                "id": run.id,
                "kind": run.kind,
                "title": MODEL_TITLES.get(run.kind, (run.kind,))[0],
                "algorithm": run.algorithm,
                "status": run.status,
                "trained_at": clock.iso_utc(run.trained_at),
                "mae": run.metrics.get("mae"),
                "baseline_mae": run.metrics.get("baseline_mae"),
                "note": run.note,
            }
            for run in history
        ],
        "training": upkeep.is_training(tenant.id),
        "last_result": upkeep.last_result(tenant.id),
        "stale": upkeep.models_stale(db, tenant),
        "service_level": tenant.service_level,
    }


@router.post("/models/retrain")
def retrain(_: User = Depends(manager), tenant: Tenant = Depends(kitchen_of)) -> dict:
    started = upkeep.start_retrain(tenant.id, note="manual retrain")
    return {"started": started, "training": True}


def _menu_payload(db: Session, tenant: Tenant) -> dict:
    sittings, rows, _ = analytics.tables(db, tenant)
    stats = analytics.dish_stats(sittings, rows, tenant.strength, days=84) if not rows.empty else None
    by_dish = {int(r.dish_id): r for r in stats.itertuples(index=False)} if stats is not None and not stats.empty else {}
    dishes = db.scalars(select(Dish).where(Dish.tenant_id == tenant.id, Dish.active.is_(True)).order_by(Dish.category, Dish.name)).all()
    by_id = {dish.id: dish for dish in dishes}

    def stat(dish: Dish) -> dict:
        row = by_dish.get(dish.id)
        return {
            "id": dish.id,
            "name": dish.name,
            "category": dish.category,
            "veg": dish.veg,
            "slow": dish.slow,
            "portion_g": dish.portion_g,
            "cost_per_kg": dish.cost_per_kg,
            "times": int(row.times) if row else 0,
            "rating": analytics._num(row.rating, 2) if row else None,
            "leftover_pct": analytics._num(row.leftover_pct) if row else None,
            "turnout_lift": analytics._num(row.turnout_lift) if row else None,
        }

    catalog = {dish.id: stat(dish) for dish in dishes}
    chart = [{"weekday": weekday, "meals": {meal: [] for meal in MEALS}} for weekday in range(7)]
    for entry in db.scalars(select(MenuTemplate).where(MenuTemplate.tenant_id == tenant.id).order_by(MenuTemplate.position)):
        if entry.dish_id in by_id:
            chart[entry.weekday]["meals"][entry.meal].append(entry.dish_id)

    suggestions = []
    for day in chart:
        on_today = {dish_id for ids in day["meals"].values() for dish_id in ids}
        for meal, ids in day["meals"].items():
            for dish_id in ids:
                current = catalog[dish_id]
                if current["category"] not in SWAPPABLE or current["times"] < 3 or current["rating"] is None:
                    continue
                reasons = []
                if current["rating"] < 3.0:
                    reasons.append(f"rated {current['rating']:.1f} stars")
                if (current["leftover_pct"] or 0) > 20:
                    reasons.append(f"{current['leftover_pct']:.0f}% of it is left in the pot")
                if (current["turnout_lift"] or 0) < -8:
                    reasons.append(f"turnout is {abs(current['turnout_lift']):.0f} lower when it is on")
                if not reasons:
                    continue
                options = [
                    c for c in catalog.values()
                    if c["category"] == current["category"] and c["veg"] == current["veg"] and c["id"] not in on_today
                    and c["times"] >= 2 and c["rating"] is not None and c["rating"] >= current["rating"] + 0.6
                ]  # fmt: skip
                if not options:
                    continue
                better = max(options, key=lambda c: (c["rating"], c["turnout_lift"] or 0))
                extra_cost = (better["cost_per_kg"] * better["portion_g"] - current["cost_per_kg"] * current["portion_g"]) / 1000
                suggestions.append(
                    {
                        "weekday": day["weekday"],
                        "meal": meal,
                        "remove": current,
                        "add": better,
                        "reasons": reasons,
                        "turnout_gain": analytics._num((better["turnout_lift"] or 0) - (current["turnout_lift"] or 0), 0),
                        "cost_per_plate": round(extra_cost, 1),
                    }
                )
    # Worst-rated first, and never the same replacement twice: one good dish cannot fix the whole week.
    suggestions.sort(key=lambda s: s["remove"]["rating"])
    distinct, offered = [], set()
    for swap in suggestions:
        if swap["add"]["id"] not in offered:
            offered.add(swap["add"]["id"])
            distinct.append(swap)
    return {"chart": chart, "dishes": list(catalog.values()), "suggestions": distinct[:5]}


@router.get("/menu")
def menu(_: User = Depends(manager), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    return _menu_payload(db, tenant)


@router.put("/menu")
def put_menu(body: SlotBody, _: User = Depends(manager), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    """Replace the dishes of one weekday and meal on the food chart; upcoming days follow at once."""
    if body.meal not in MEALS:
        raise HTTPException(404, "Unknown meal")
    if len(set(body.dish_ids)) != len(body.dish_ids):
        raise HTTPException(422, "A dish is listed twice")
    known = set(db.scalars(select(Dish.id).where(Dish.tenant_id == tenant.id, Dish.active.is_(True), Dish.id.in_(body.dish_ids))))
    if known != set(body.dish_ids):
        raise HTTPException(422, "One of those dishes does not belong to this kitchen")
    db.execute(delete(MenuTemplate).where(MenuTemplate.tenant_id == tenant.id, MenuTemplate.weekday == body.weekday, MenuTemplate.meal == body.meal))
    for position, dish_id in enumerate(body.dish_ids):
        db.add(MenuTemplate(tenant_id=tenant.id, weekday=body.weekday, meal=body.meal, dish_id=dish_id, position=position))
    db.flush()
    rebuild_future_menu(db, tenant)
    db.commit()
    analytics.forget_cache()
    return _menu_payload(db, tenant)


@router.put("/settings")
def settings(body: SettingsBody, _: User = Depends(manager), tenant: Tenant = Depends(kitchen_of), db: Session = Depends(get_db)) -> dict:
    """How sure the kitchen wants to be that a pot does not run dry. Changes the safety margin on every sheet not yet final."""
    tenant.service_level = round(body.service_level, 2)
    db.flush()
    pipeline.replan_outlook(db, tenant)
    db.commit()
    analytics.forget_cache()
    return tenant_out(tenant)
