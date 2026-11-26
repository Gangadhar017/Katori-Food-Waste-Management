"""Passwords, access tokens and the role checks used by the API."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import clock
from .config import get_settings
from .db import get_db
from .models import Tenant, User

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
NO_LOGIN = "!"  # stored for simulated residents: matches no password
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest, bytes.fromhex(digest_hex))


def issue_token(user: User) -> str:
    settings = get_settings()
    now = clock.utcnow()
    payload = {
        "sub": str(user.id),
        "tid": user.tenant_id,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.token_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def user_from_token(token: str, db: Session) -> User | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    if user is None or user.tenant_id != payload.get("tid"):
        return None
    return user


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    user = user_from_token(credentials.credentials, db) if credentials else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue")
    return user


def current_tenant(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Tenant:
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None:  # pragma: no cover - a user always has a tenant
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue")
    return tenant


def require_role(*roles: str):
    def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot do this")
        return user

    return check
