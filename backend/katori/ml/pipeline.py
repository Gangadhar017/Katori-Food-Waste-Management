"""Training and planning entry points.

`train_all` retrains every model for a kitchen and decides, per model, whether the new
run may replace the serving one. `Planner` turns the serving models into the numbers the
kitchen sees: an expected head count with a range, and kilograms to cook per dish.

scikit-learn is imported inside the functions so the API can start, and answer every
read, without loading it.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..meals import cutoff_utc
from ..models import Dish, DishService, MealService, MenuEntry, ModelRun, Tenant
from . import registry
from .features import DEFAULT_RATE

MIN_HISTORY_DAYS = 28
STANDARD_RATE = {"breakfast": 0.70, "lunch": 0.86, "snacks": 0.62, "dinner": 0.90}
_train_lock = threading.Lock()


def standard_kg(portion_g: float, meal: str, strength: int) -> float:
    """The fixed rule a mess uses without data: a set share of the roll, a full portion each."""
    return round(strength * STANDARD_RATE[meal] * portion_g / 1000, 1)


def is_frozen(service: MealService) -> bool:
    """A cook-sheet forecast made at the cut-off is final: it is what the kitchen acted on."""
    return service.forecast_model.startswith("cook")


def _gate(db: Session, tenant: Tenant, kind: str, metrics: dict, backtest, meals) -> tuple[bool, str]:
    """May this run replace the serving model?"""
    if metrics["mae"] > metrics["baseline_mae"]:
        return False, f"rejected: no better than the naive baseline ({metrics['baseline']})"
    if kind == "headcount_cook" and backtest is not None:
        current = registry.champion(db, tenant.id, kind)
        if current is not None and current.train_through is not None:
            import pandas as pd

            live = meals[
                (meals["day"] > pd.Timestamp(current.train_through))
                & meals["served"].notna()
                & meals["forecast_p50"].notna()
            ]
            both = live.merge(backtest[["day", "meal", "pred"]], on=["day", "meal"], how="inner")
            if len(both) >= 12:
                serving = float((both["forecast_p50"] - both["served"]).abs().mean())
                challenger = float((both["pred"] - both["served"]).abs().mean())
                metrics["live_serving_mae"] = round(serving, 2)
                metrics["live_challenger_mae"] = round(challenger, 2)
                metrics["live_sittings"] = int(len(both))
                if challenger > serving * 1.10:
                    return False, "rejected: the serving model was more accurate on the newest sittings"
    return True, "promoted"


def train_all(
    db: Session, tenant: Tenant, *, quick: bool = False, note: str = "", at: datetime | None = None
) -> list[ModelRun]:
    """Retrain every model for this kitchen. Returns the runs it logged (possibly none)."""
    from . import headcount, portion, waittime
    from .features import headcount_frame, load_dishes, load_meals, portion_frame

    at = at or clock.utcnow()
    with _train_lock:
        meals, dishes = load_meals(db, tenant.id), load_dishes(db, tenant.id)
        done = meals[meals["served"].notna()]
        if done["day"].nunique() < MIN_HISTORY_DAYS:
            return []
        train_through = done["day"].max().date()
        n_folds = 4 if quick else 6
        # Fit everything first and write at the end, so the database is locked only for a moment.
        trained: list[tuple] = []

        def log(*run) -> None:
            trained.append(run)

        frame = headcount_frame(meals, dishes, tenant.strength)
        cook_backtest = None
        for kind in ("headcount_cook", "headcount_outlook"):
            try:
                artifact, metrics, detail, backtest = headcount.train(
                    frame, tenant.strength, kind, n_folds=n_folds, quick=quick
                )
            except headcount.NotEnoughData:
                continue
            if kind == "headcount_cook":
                cook_backtest = backtest
            log(kind, artifact.algorithm, artifact, metrics, detail, backtest, int(frame["ratio"].notna().sum()))

        portions = portion_frame(meals, dishes)
        try:
            artifact, metrics, detail, backtest = portion.train(portions, n_folds=n_folds, quick=quick)
            if cook_backtest is not None:
                quantiles, policy = portion.calibrate_demand(cook_backtest, backtest, tenant.service_level)
                artifact.demand_quantiles = quantiles
                detail["policy"] = policy
                detail["demand_quantiles"] = {str(level): round(value, 4) for level, value in quantiles.items()}
            log("portion", artifact.algorithm, artifact, metrics, detail, None, int(portions["valid"].sum()))
        except headcount.NotEnoughData:
            pass

        try:
            samples = waittime.load_samples(db, tenant.id)
            artifact, metrics, detail = waittime.train(samples, quick=quick)
            log("wait", artifact.algorithm, artifact, metrics, detail, None, int(len(samples)))
        except headcount.NotEnoughData:
            pass

        runs: list[ModelRun] = []
        for kind, algorithm, artifact, metrics, detail, backtest, n_rows in trained:
            promote, verdict = _gate(db, tenant, kind, metrics, backtest, meals)
            runs.append(
                registry.record(
                    db, tenant, kind, algorithm, artifact, metrics, detail,
                    train_through=train_through, n_rows=n_rows, promote=promote,
                    note=f"{note}: {verdict}" if note else verdict, trained_at=at,
                )
            )  # fmt: skip
        db.flush()
        return runs


class Planner:
    """Writes forecasts and advised quantities for sittings, using the serving models."""

    def __init__(self, db: Session, tenant: Tenant):
        self.db = db
        self.tenant = tenant

    def _serving(self, kind: str):
        run = registry.champion(self.db, self.tenant.id, kind)
        return run, registry.load(run)

    def has_models(self) -> bool:
        return self._serving("headcount_cook")[1] is not None

    def plan(self, services: Sequence[MealService], *, now: datetime | None = None, allow_cold: bool = True) -> int:
        """Forecast these sittings. Past the cut-off the cook model is used and the result is final."""
        services = [s for s in services if not is_frozen(s)]
        if not services:
            return 0
        now = now or clock.utcnow()
        tenant, db = self.tenant, self.db
        cook_run, cook = self._serving("headcount_cook")
        outlook_run, outlook = self._serving("headcount_outlook")
        portion_run, portion = self._serving("portion")
        if cook is None and not allow_cold:
            return 0

        import numpy as np

        from .features import headcount_frame, load_dishes, load_meals, portion_frame

        meals, dishes = load_meals(db, tenant.id), load_dishes(db, tenant.id)
        frame = headcount_frame(meals, dishes, tenant.strength)
        position = {(day.date(), meal): i for i, (day, meal) in enumerate(zip(frame["day"], frame["meal"], strict=True))}

        expected: dict[tuple, float] = {}
        for service in services:
            key = (service.day, service.meal)
            if key not in position:
                continue
            past_cutoff = now >= cutoff_utc(service.day, service.meal, tenant.timezone)
            run, model = (cook_run, cook) if past_cutoff else (outlook_run, outlook)
            if model is None and cook is not None:
                run, model = cook_run, cook
            if model is not None:
                row = frame.iloc[[position[key]]]
                off_day = service.calendar_kind in {"holiday", "break"}
                p50 = float(model.predict_heads(row, tenant.strength)[0])
                low = p50 * (1 + model.quantile(0.1, off_day=off_day))
                high = p50 * (1 + model.quantile(0.9, off_day=off_day))
                label = f"{'cook' if past_cutoff else 'outlook'}:{model.algorithm}#{run.id}"
            else:
                p50 = tenant.strength * DEFAULT_RATE[service.meal]
                low, high = p50 * 0.82, p50 * 1.18
                label = "cook:cold-start" if past_cutoff else "outlook:cold-start"
            service.forecast_p50 = round(p50, 1)
            service.forecast_p10 = round(max(min(low, p50), 0.0), 1)
            service.forecast_p90 = round(min(max(high, p50), tenant.strength * 1.05), 1)
            service.forecast_model = label
            # A cook-sheet forecast only uses what was known at the cut-off, whenever it is computed.
            service.forecast_at = min(now, cutoff_utc(service.day, service.meal, tenant.timezone))
            expected[key] = p50

        portions = portion_frame(meals, dishes)
        wanted = np.array(
            [(day.date(), meal) in expected for day, meal in zip(portions["day"], portions["meal"], strict=True)],
            dtype=bool,
        )
        target = portions[wanted]
        if len(target):
            take = portion.predict_take(target) if portion is not None else target["take_prior"].to_numpy(dtype=float)
            margin = portion.margin(tenant.service_level) if portion is not None else 0.10
            days = sorted({key[0] for key in expected})
            existing = {
                (row.day, row.meal, row.dish_id): row
                for row in db.scalars(
                    select(DishService).where(DishService.tenant_id == tenant.id, DishService.day.in_(days))
                )
            }
            for (day, meal, dish_id, portion_g), share in zip(
                zip(target["day"], target["meal"], target["dish_id"], target["portion_g"], strict=True), take, strict=True
            ):
                key = (day.date(), meal, int(dish_id))
                row = existing.get(key)
                if row is None:
                    row = DishService(tenant_id=tenant.id, day=key[0], meal=meal, dish_id=key[2])
                    db.add(row)
                    existing[key] = row
                kilos = expected[(key[0], meal)] * float(share) * float(portion_g) / 1000 * (1 + margin)
                row.recommended_kg = max(round(kilos, 1), 0.2)
                if row.habit_kg is None:
                    row.habit_kg = standard_kg(float(portion_g), meal, tenant.strength)
        db.flush()
        return len(expected)


def upcoming_services(db: Session, tenant: Tenant) -> list[MealService]:
    return list(
        db.scalars(
            select(MealService)
            .where(MealService.tenant_id == tenant.id, MealService.served.is_(None))
            .order_by(MealService.day)
        )
    )


def replan_outlook(db: Session, tenant: Tenant, *, now: datetime | None = None) -> int:
    """Refresh every forecast that is not yet final, for example after a retrain or a menu change."""
    return Planner(db, tenant).plan(upcoming_services(db, tenant), now=now)


def menu_dishes(db: Session, tenant_id: int, day, meal: str) -> list[Dish]:
    return [
        entry.dish
        for entry in db.scalars(
            select(MenuEntry)
            .where(MenuEntry.tenant_id == tenant_id, MenuEntry.day == day, MenuEntry.meal == meal)
            .order_by(MenuEntry.position)
        )
    ]
