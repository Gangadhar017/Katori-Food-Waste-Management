"""Model registry: one serving model ("champion") per kind per kitchen, with a full run history."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ModelRun, Tenant

_loaded: dict[int, object] = {}


def champion(db: Session, tenant_id: int, kind: str) -> ModelRun | None:
    return db.scalars(
        select(ModelRun)
        .where(ModelRun.tenant_id == tenant_id, ModelRun.kind == kind, ModelRun.status == "champion")
        .order_by(ModelRun.id.desc())
    ).first()


def _path(run: ModelRun) -> Path:
    return get_settings().model_dir / run.path


def load(run: ModelRun | None) -> object | None:
    """The fitted model behind a run, or None if its file is gone (the caller falls back and retrains)."""
    if run is None or not run.path:
        return None
    if run.id not in _loaded:
        path = _path(run)
        if not path.exists():
            return None
        import joblib

        _loaded[run.id] = joblib.load(path)
    return _loaded[run.id]


def record(
    db: Session,
    tenant: Tenant,
    kind: str,
    algorithm: str,
    artifact: object,
    metrics: dict,
    detail: dict,
    *,
    train_through: date | None,
    n_rows: int,
    promote: bool,
    note: str,
    trained_at: datetime,
) -> ModelRun:
    """Log a training run. A promoted run replaces the champion; a rejected one is kept for the record only."""
    run = ModelRun(
        tenant_id=tenant.id,
        kind=kind,
        algorithm=algorithm,
        status="champion" if promote else "rejected",
        trained_at=trained_at,
        train_through=train_through,
        n_rows=n_rows,
        metrics=metrics,
        detail=detail,
        note=note,
    )
    db.add(run)
    db.flush()
    if not promote:
        return run

    import joblib

    for old in db.scalars(
        select(ModelRun).where(
            ModelRun.tenant_id == tenant.id, ModelRun.kind == kind, ModelRun.status == "champion", ModelRun.id != run.id
        )
    ):
        old.status = "retired"
        _loaded.pop(old.id, None)
        if old.path:
            _path(old).unlink(missing_ok=True)
            old.path = ""
    run.path = f"{tenant.slug}/{kind}-{run.id}.joblib"
    target = _path(run)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, target, compress=3)
    _loaded[run.id] = artifact
    db.flush()
    return run


def forget_cache() -> None:
    _loaded.clear()
