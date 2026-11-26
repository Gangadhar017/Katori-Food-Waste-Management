"""Test setup: a throwaway database with a small demo hostel, built once per run."""

from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="katori-test-")
os.environ["KATORI_VAR_DIR"] = _tmp
os.environ["KATORI_WEB_DIR"] = os.path.join(_tmp, "no-web")
os.environ["KATORI_DEMO"] = "1"
os.environ["KATORI_SECRET"] = "only-for-the-test-run-0123456789-abcdefghij"
os.environ.pop("DATABASE_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from katori import clock  # noqa: E402
from katori.db import SessionLocal, init_db  # noqa: E402
from katori.models import Tenant  # noqa: E402
from katori.seed import DEMO_SLUG, seed_demo  # noqa: E402

STRENGTH = 180


@pytest.fixture(scope="session")
def hostel() -> int:
    """Nine weeks of a 180-bed hostel: four measured, two in shadow, three cooked from the sheet."""
    init_db()
    with SessionLocal() as db:
        tenant = seed_demo(db, history_days=63, live_days=21, strength=STRENGTH, quick=True)
        db.commit()
        return tenant.id


@pytest.fixture(scope="session")
def client(hostel):
    from katori.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(hostel):
    with SessionLocal() as session:
        yield session


@pytest.fixture
def tenant(db) -> Tenant:
    return db.scalar(select(Tenant).where(Tenant.slug == DEMO_SLUG))


def _headers(client: TestClient, role: str) -> dict:
    response = client.post("/api/auth/demo", json={"role": role})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture(scope="session")
def student(client) -> dict:
    return _headers(client, "student")


@pytest.fixture(scope="session")
def kitchen(client) -> dict:
    return _headers(client, "kitchen")


@pytest.fixture(scope="session")
def manager(client) -> dict:
    return _headers(client, "manager")


@pytest.fixture
def frozen_clock():
    """Pin the clock; tests move it forward by calling the returned function."""
    start = clock.utcnow()
    clock.freeze(start)
    yield lambda delta: clock.freeze(clock.utcnow() + delta)
    clock.freeze(None)
