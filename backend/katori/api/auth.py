"""Sign-in. The public demo also offers one-click entry in each role."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Tenant, User
from ..security import current_user, issue_token, verify_password
from .deps import kitchen_of, user_out

router = APIRouter(prefix="/api", tags=["auth"])
_attempts: dict[str, deque[float]] = defaultdict(deque)
MAX_ATTEMPTS, WINDOW_SECONDS = 8, 60


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=200)


class DemoEntry(BaseModel):
    role: str


def _throttle(request: Request) -> None:
    key = request.client.host if request.client else "unknown"
    recent, now = _attempts[key], time.monotonic()
    while recent and now - recent[0] > WINDOW_SECONDS:
        recent.popleft()
    if len(recent) >= MAX_ATTEMPTS:
        raise HTTPException(429, "Too many sign-in attempts. Wait a minute and try again.")
    recent.append(now)


@router.post("/auth/login")
def login(body: Login, request: Request, db: Session = Depends(get_db)) -> dict:
    _throttle(request)
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is not right")
    return {"token": issue_token(user), "user": user_out(user, db.get(Tenant, user.tenant_id))}


@router.post("/auth/demo")
def demo(body: DemoEntry, db: Session = Depends(get_db)) -> dict:
    if not get_settings().demo_mode:
        raise HTTPException(404, "The demo is not enabled on this server")
    if body.role not in {"student", "kitchen", "manager"}:
        raise HTTPException(422, "Pick student, kitchen or manager")
    user = db.scalar(
        select(User)
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(Tenant.is_demo.is_(True), User.is_demo.is_(True), User.role == body.role)
    )
    if user is None:
        raise HTTPException(503, "The demo hostel is still being set up")
    return {"token": issue_token(user), "user": user_out(user, db.get(Tenant, user.tenant_id))}


@router.get("/me")
def me(user: User = Depends(current_user), tenant: Tenant = Depends(kitchen_of)) -> dict:
    return user_out(user, tenant)
