"""Runtime settings, read once from the environment."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    var_dir: Path
    model_dir: Path
    secret_key: str
    demo_mode: bool
    cors_origins: tuple[str, ...]
    web_dir: Path
    token_hours: int
    sim_seed: int
    retrain_days: int  # retrain once the serving model is this many logged days behind


@lru_cache
def get_settings() -> Settings:
    var_dir = Path(os.environ.get("KATORI_VAR_DIR", BACKEND_DIR / "var")).resolve()
    database_url = os.environ.get("DATABASE_URL") or f"sqlite:///{(var_dir / 'katori.db').as_posix()}"
    # Hosted Postgres providers hand out the legacy scheme; SQLAlchemy wants the driver named.
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgres://") :]
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://") :]

    origins = tuple(
        origin.strip().rstrip("/")
        for origin in os.environ.get("KATORI_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if origin.strip()
    )
    return Settings(
        database_url=database_url,
        var_dir=var_dir,
        model_dir=Path(os.environ.get("KATORI_MODEL_DIR", var_dir / "models")).resolve(),
        # Without a configured secret every restart signs with a fresh key, which only logs people out.
        secret_key=os.environ.get("KATORI_SECRET") or secrets.token_urlsafe(48),
        demo_mode=_flag("KATORI_DEMO", True),
        cors_origins=origins,
        web_dir=Path(os.environ.get("KATORI_WEB_DIR", REPO_DIR / "web" / "dist")).resolve(),
        token_hours=int(os.environ.get("KATORI_TOKEN_HOURS", "12")),
        sim_seed=int(os.environ.get("KATORI_SIM_SEED", "2315")),
        retrain_days=int(os.environ.get("KATORI_RETRAIN_DAYS", "1")),
    )
