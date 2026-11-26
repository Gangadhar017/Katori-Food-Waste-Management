"""Housekeeping that runs alongside requests instead of in a scheduler.

Free hosting puts the service to sleep, so nothing here relies on a clock ticking in the
background: the first request after a quiet spell brings the kitchen up to date, and a
retrain is started (in a thread) once the serving model has fallen behind the log.
"""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..meals import MEALS
from ..ml import pipeline, registry
from ..models import MealService, Tenant
from ..sim.engine import catch_up
from . import analytics

log = logging.getLogger("katori.upkeep")
TICK_SECONDS = 60
_last_tick: dict[int, float] = {}
_tick_lock = threading.Lock()
_training: set[int] = set()
_last_result: dict[int, str] = {}


def models_stale(db: Session, tenant: Tenant) -> bool:
    # Only whole days count: a model trained through yesterday is current until tonight's dinner is logged.
    newest = db.scalar(
        select(func.max(MealService.day)).where(
            MealService.tenant_id == tenant.id, MealService.served.is_not(None), MealService.meal == MEALS[-1]
        )
    )
    if newest is None:
        return False
    run = registry.champion(db, tenant.id, "headcount_cook")
    if run is None or registry.load(run) is None:
        logged_days = db.scalar(
            select(func.count(func.distinct(MealService.day))).where(
                MealService.tenant_id == tenant.id, MealService.served.is_not(None)
            )
        )
        return (logged_days or 0) >= pipeline.MIN_HISTORY_DAYS
    return run.train_through is None or (newest - run.train_through).days >= get_settings().retrain_days


def is_training(tenant_id: int) -> bool:
    return tenant_id in _training


def last_result(tenant_id: int) -> str:
    return _last_result.get(tenant_id, "")


def _retrain(tenant_id: int, note: str) -> None:
    try:
        with SessionLocal() as db:
            tenant = db.get(Tenant, tenant_id)
            runs = pipeline.train_all(db, tenant, note=note)
            db.commit()
            pipeline.replan_outlook(db, tenant)
            db.commit()
            promoted = sum(1 for run in runs if run.status == "champion")
            _last_result[tenant_id] = f"{promoted} of {len(runs)} models promoted" if runs else "not enough history yet"
    except Exception:  # pragma: no cover - logged, the serving models stay in place
        log.exception("retrain failed for tenant %s", tenant_id)
        _last_result[tenant_id] = "failed, the previous models are still serving"
    finally:
        _training.discard(tenant_id)
        analytics.forget_cache()


def start_retrain(tenant_id: int, note: str = "nightly retrain", *, background: bool = True) -> bool:
    """Begin a retrain unless one is already running. Returns whether it started."""
    if tenant_id in _training:
        return False
    _training.add(tenant_id)
    if background:
        threading.Thread(target=_retrain, args=(tenant_id, note), name=f"retrain-{tenant_id}", daemon=True).start()
    else:
        _retrain(tenant_id, note)
    return True


def tick(db: Session, tenant: Tenant, *, force: bool = False) -> None:
    """Bring this kitchen up to date if it has not been looked at for a minute."""
    now = time.monotonic()
    if not force and now - _last_tick.get(tenant.id, -1e9) < TICK_SECONDS:
        return
    if not _tick_lock.acquire(blocking=False):
        return
    try:
        _last_tick[tenant.id] = now
        result = catch_up(db, tenant)
        db.commit()
        if result["completed"]:
            analytics.forget_cache()
        if models_stale(db, tenant):
            start_retrain(tenant.id)
    except Exception:  # pragma: no cover - never let housekeeping break a request
        db.rollback()
        log.exception("upkeep failed for tenant %s", tenant.id)
    finally:
        _tick_lock.release()


def reset() -> None:
    """Forget timers (tests)."""
    _last_tick.clear()
    _training.clear()
    _last_result.clear()
