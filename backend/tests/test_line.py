"""The serving line: tokens are served in order, and the live stream is gated."""

from datetime import timedelta

from sqlalchemy import select

from katori.models import QueueTicket, WaitSample
from katori.services import line


def test_a_resident_moves_up_the_line_and_is_served(client, student, db, tenant, frozen_clock):
    joined = client.post("/api/line/join", headers=student).json()
    ticket = joined["ticket"]
    assert ticket["status"] == "waiting" and ticket["token"] > 0
    assert joined["line"]["simulated"] is True
    assert client.post("/api/line/join", headers=student).json()["ticket"]["token"] == ticket["token"]  # joining twice keeps the place

    seen_ahead, status = [ticket["ahead"]], "waiting"
    for _ in range(80):
        frozen_clock(timedelta(seconds=20))
        now = client.get("/api/line", headers=student).json()["ticket"]
        status = now["status"]
        if status != "waiting":
            break
        seen_ahead.append(now["ahead"])
    assert status in {"called", "served"}
    assert seen_ahead == sorted(seen_ahead, reverse=True), "nobody may jump ahead of a waiting token"

    for _ in range(6):
        frozen_clock(timedelta(seconds=10))
        status = client.get("/api/line", headers=student).json()["ticket"]["status"]
    assert status == "served"
    assert db.scalar(select(WaitSample).where(WaitSample.tenant_id == tenant.id).order_by(WaitSample.id.desc())).wait_s >= 0


def test_tokens_are_called_in_the_order_they_were_issued(client, kitchen, db, tenant, frozen_clock):
    for _ in range(12):
        frozen_clock(timedelta(seconds=15))
        line.snapshot(db, tenant)
    called = db.scalars(
        select(QueueTicket).where(QueueTicket.tenant_id == tenant.id, QueueTicket.called_at.is_not(None)).order_by(QueueTicket.called_at, QueueTicket.id)
    ).all()
    tokens = [t.token for t in called]
    assert len(tokens) >= 3 and tokens == sorted(tokens)


def test_opening_a_counter_is_reflected_at_once(client, kitchen, student):
    assert client.post("/api/line/counters", headers=student, json={"open": 3}).status_code == 403
    assert client.post("/api/line/counters", headers=kitchen, json={"open": 3}).json()["line"]["counters"] == 3
    assert client.post("/api/line/counters", headers=kitchen, json={"open": 9}).status_code == 422
    assert client.post("/api/line/counters", headers=kitchen, json={"open": 2}).json()["line"]["counters"] == 2


def test_leaving_gives_up_the_token(client, student, frozen_clock):
    frozen_clock(timedelta(seconds=5))
    client.post("/api/line/join", headers=student)
    assert client.post("/api/line/leave", headers=student).json()["ticket"] is None


def test_stream_needs_a_fresh_single_use_ticket(client, student):
    assert client.get("/api/line/stream", params={"ticket": "made-up"}).status_code == 401
    assert client.post("/api/line/stream-ticket").status_code == 401
    ticket = client.post("/api/line/stream-ticket", headers=student).json()["ticket"]
    assert len(ticket) > 20
    from katori.api import line as line_api

    assert ticket in line_api._tickets
    line_api._tickets.pop(ticket)
    assert client.get("/api/line/stream", params={"ticket": ticket}).status_code == 401


def test_dining_hall_board_is_public(client):
    board = client.get("/api/public/nilgiri/board").json()
    assert board["hostel"] == "Nilgiri Hostel" and len(board["sittings"]) == 4
    assert board["line"]["ticket"] is None
    assert client.get("/api/public/nowhere/board").status_code == 404
