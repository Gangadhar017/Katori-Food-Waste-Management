"""Set up a real kitchen (no simulator) from the command line.

    python -m katori.manage create-kitchen --slug aravali --name "Aravali Mess" --city Jaipur \
        --strength 300 --manager-email warden@example.edu --manager-name "A. Warden"
    python -m katori.manage add-user --slug aravali --role kitchen --email cook@example.edu --name "Head Cook"

Passwords are asked for at the prompt (or read from KATORI_NEW_PASSWORD) and never echoed.
A new kitchen starts with the starter food chart and plain estimates; the models take over
once four weeks of sittings have been weighed in.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys

from sqlalchemy import select

from . import clock
from .db import SessionLocal, init_db
from .models import Tenant, User
from .security import hash_password
from .seed import load_starter_menu
from .sim.engine import catch_up

ROLES = ("manager", "kitchen", "student")


def _password() -> str:
    password = os.environ.get("KATORI_NEW_PASSWORD") or getpass.getpass("Password for the new account: ")
    if len(password) < 10:
        sys.exit("Use a password of at least 10 characters.")
    return password


def _add_user(db, tenant: Tenant, role: str, email: str, name: str, room: str = "") -> User:
    email = email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        sys.exit(f"{email} already has an account.")
    user = User(tenant_id=tenant.id, email=email, name=name, role=role, room=room, password_hash=hash_password(_password()))
    db.add(user)
    return user


def create_kitchen(args: argparse.Namespace) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,58}", args.slug):
        sys.exit("The slug may use lower-case letters, digits and hyphens.")
    with SessionLocal() as db:
        if db.scalar(select(Tenant.id).where(Tenant.slug == args.slug)):
            sys.exit(f"A kitchen called {args.slug} already exists.")
        tenant = Tenant(slug=args.slug, name=args.name, city=args.city, strength=args.strength, created_at=clock.utcnow())
        db.add(tenant)
        db.flush()
        _add_user(db, tenant, "manager", args.manager_email, args.manager_name)
        if not args.empty_menu:
            load_starter_menu(db, tenant)
        catch_up(db, tenant)
        db.commit()
        print(f"Created {tenant.name} ({tenant.slug}) for {tenant.strength} residents. The manager can sign in now.")


def add_user(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == args.slug))
        if tenant is None:
            sys.exit(f"No kitchen called {args.slug}.")
        user = _add_user(db, tenant, args.role, args.email, args.name, args.room)
        db.commit()
        print(f"Added {user.name} as {user.role} at {tenant.name}.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m katori.manage", description="Set up kitchens and accounts")
    commands = parser.add_subparsers(dest="command", required=True)

    kitchen = commands.add_parser("create-kitchen", help="create a kitchen and its manager")
    kitchen.add_argument("--slug", required=True, help="short name used in links, e.g. aravali")
    kitchen.add_argument("--name", required=True)
    kitchen.add_argument("--city", default="")
    kitchen.add_argument("--strength", type=int, required=True, help="residents on the mess roll")
    kitchen.add_argument("--manager-email", required=True)
    kitchen.add_argument("--manager-name", required=True)
    kitchen.add_argument("--empty-menu", action="store_true", help="start without the starter dishes and food chart")
    kitchen.set_defaults(run=create_kitchen)

    user = commands.add_parser("add-user", help="add a manager, cook or resident to a kitchen")
    user.add_argument("--slug", required=True)
    user.add_argument("--role", choices=ROLES, required=True)
    user.add_argument("--email", required=True)
    user.add_argument("--name", required=True)
    user.add_argument("--room", default="")
    user.set_defaults(run=add_user)

    args = parser.parse_args()
    init_db()
    args.run(args)


if __name__ == "__main__":
    main()
