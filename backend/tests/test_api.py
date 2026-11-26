"""The API as each role uses it."""

from datetime import date, timedelta

from sqlalchemy import select

from katori import clock
from katori.meals import MEALS
from katori.models import DishService, MealService, Tenant, User
from katori.security import hash_password, verify_password
from katori.services import analytics


def _meals(client, student, **params):
    response = client.get("/api/meals", headers=student, params=params)
    assert response.status_code == 200
    return [meal for day in response.json()["days"] for meal in day["meals"]]


def test_health_and_public_summary(client):
    assert client.get("/api/health").json()["status"] == "ok"
    summary = client.get("/api/public/summary").json()
    assert summary["hostel"] == "Nilgiri Hostel" and summary["simulated"] is True
    assert summary["leftover_after_pct"] < summary["leftover_before_pct"]


def test_requests_without_a_valid_token_are_refused(client):
    assert client.get("/api/meals").status_code == 401
    assert client.get("/api/meals", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_roles_cannot_cross_into_each_others_pages(client, student, kitchen):
    assert client.get("/api/kitchen/sheet", headers=student).status_code == 403
    assert client.get("/api/manager/overview", headers=kitchen).status_code == 403
    assert client.post("/api/line/join", headers=kitchen).status_code == 403


def test_password_hashing_round_trip():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)
    assert not verify_password("anything", "!")


def test_skip_notice_reaches_the_kitchen_and_earns_points(client, student):
    meal = next(m for m in _meals(client, student) if m["state"] == "open")
    url = f"/api/meals/{meal['day']}/{meal['meal']}/rsvp"
    skipped = client.put(url, headers=student, json={"status": "skip"}).json()
    assert skipped["meal"]["rsvp"] == "skip"
    assert skipped["meal"]["notices"] == meal["notices"] + 1
    assert skipped["gained"] == 5
    assert client.put(url, headers=student, json={"status": "skip"}).json()["gained"] == 0  # no double credit
    back = client.put(url, headers=student, json={"status": "eat"}).json()
    assert back["meal"]["notices"] == meal["notices"] and back["gained"] == -5


def test_notice_is_refused_once_cooking_has_started(client, student):
    late = next(m for m in _meals(client, student, back=1) if m["state"] != "open")
    response = client.put(f"/api/meals/{late['day']}/{late['meal']}/rsvp", headers=student, json={"status": "skip"})
    assert response.status_code == 409


def test_marking_days_away_skips_every_sitting_in_range(client, student, db):
    start = clock.local_today("Asia/Kolkata") + timedelta(days=3)
    response = client.post("/api/meals/away", headers=student, json={"start": start.isoformat(), "end": (start + timedelta(days=1)).isoformat()})
    assert response.status_code == 200 and response.json()["marked"] == 8
    assert response.json()["gained"] == 20  # at most two rewarded skips per day
    away = [m for m in _meals(client, student, days=8) if m["day"] in {start.isoformat(), (start + timedelta(days=1)).isoformat()}]
    assert len(away) == 8 and all(m["rsvp"] == "skip" for m in away)
    assert client.post("/api/meals/away", headers=student, json={"start": "2020-01-01", "end": "2020-01-02"}).status_code == 422


def test_rating_a_served_meal_updates_the_dish_tally_once(client, student, db):
    served = next(m for m in _meals(client, student, back=1) if m["can_rate"])
    dish_id = served["dishes"][0]["id"]
    day = date.fromisoformat(served["day"])
    where = (DishService.day == day, DishService.meal == served["meal"], DishService.dish_id == dish_id)
    before = db.scalar(select(DishService).where(*where))
    votes, stars = before.rating_n, before.rating_sum
    url = f"/api/meals/{served['day']}/{served['meal']}/ratings"
    assert client.post(url, headers=student, json={"ratings": [{"dish_id": dish_id, "stars": 5}]}).json()["gained"] == 2
    changed = client.post(url, headers=student, json={"ratings": [{"dish_id": dish_id, "stars": 2}]}).json()
    assert changed["gained"] == 0
    db.expire_all()
    after = db.scalar(select(DishService).where(*where))
    assert after.rating_n == votes + 1 and after.rating_sum == stars + 2
    assert client.post(url, headers=student, json={"ratings": [{"dish_id": 999999, "stars": 3}]}).status_code == 422


def test_game_points_are_capped_per_play_and_per_day(client, student):
    first = client.post("/api/games/score", headers=student, json={"game": "just-enough", "score": 100000}).json()
    assert first["gained"] == 20
    for _ in range(2):
        client.post("/api/games/score", headers=student, json={"game": "just-enough", "score": 250})
    fourth = client.post("/api/games/score", headers=student, json={"game": "just-enough", "score": 400}).json()
    assert fourth["gained"] == 0 and fourth["scored_plays_left"] == 0
    assert client.post("/api/games/score", headers=student, json={"game": "chess", "score": 1}).status_code == 422


def test_leaderboard_always_includes_the_resident(client, student):
    board = client.get("/api/leaderboard", headers=student).json()
    mine = [row for row in board["rows"] if row["me"]]
    assert len(mine) == 1 and mine[0]["name"] == "Gangadhar Singh"
    assert all(row["name"].endswith(".") for row in board["rows"] if not row["me"])  # others are shown as "First L."
    points = [row["points"] for row in board["rows"][:20]]
    assert points == sorted(points, reverse=True)


def test_cook_sheet_turns_the_forecast_into_quantities(client, kitchen):
    sheet = client.get("/api/kitchen/sheet", headers=kitchen).json()
    head = sheet["headcount"]
    assert head["low"] <= head["expected"] <= head["high"] <= head["roll"] * 1.05
    assert sheet["dishes"] and all(d["advised_kg"] > 0 for d in sheet["dishes"])
    with_recipe = next(d for d in sheet["dishes"] if d["ingredients"])
    assert all(item["kg"] >= 0 for item in with_recipe["ingredients"])
    assert sheet["totals"]["advised_kg"] == round(sum(d["advised_kg"] for d in sheet["dishes"]), 1)
    later = sheet["sittings"][-1]
    assert client.get("/api/kitchen/sheet", headers=kitchen, params=later).json()["meal"] == later["meal"]


def test_kitchen_log_is_validated_and_saved(client, kitchen, db):
    log = client.get("/api/kitchen/log", headers=kitchen).json()
    url = f"/api/kitchen/log/{log['day']}/{log['meal']}"
    dishes = [{"dish_id": d["dish_id"], "prepared_kg": 12.0, "leftover_kg": 1.5} for d in log["dishes"]]
    body = {"served": 140, "prep_waste_kg": 2.5, "plate_waste_kg": 6.0, "dishes": dishes}
    impossible = {**body, "dishes": [{**dishes[0], "leftover_kg": 20.0}, *dishes[1:]]}
    assert client.put(url, headers=kitchen, json=impossible).status_code == 422
    dishes[0] = {**dishes[0], "leftover_kg": 0.0, "ran_out": True, "short_heads": 9}
    saved = client.put(url, headers=kitchen, json={**body, "dishes": dishes}).json()
    assert saved["logged_by"] == "kitchen" and saved["served"] == 140
    assert saved["dishes"][0]["ran_out"] is True and saved["dishes"][0]["short_heads"] == 9
    tomorrow = (clock.local_today("Asia/Kolkata") + timedelta(days=1)).isoformat()
    assert client.put(f"/api/kitchen/log/{tomorrow}/dinner", headers=kitchen, json=body).status_code in {409, 422}


def test_manager_overview_reports_the_change_since_adoption(client, manager):
    overview = client.get("/api/manager/overview", headers=manager).json()
    assert overview["empty"] is False
    change = overview["adoption"]
    assert change["after"]["leftover_pct"] < change["before"]["leftover_pct"]
    assert change["saved_kg"] > 0
    assert len(overview["trend"]) >= 7 and {"sheet", "habit"} == {week["phase"] for week in overview["trend"]}
    assert overview["insights"]
    waste = client.get("/api/manager/waste", headers=manager).json()
    assert len(waste["heatmap"]) == 28 and waste["by_dish"][0]["leftover_kg"] >= waste["by_dish"][-1]["leftover_kg"]


def test_forecast_page_scores_itself_against_what_happened(client, manager):
    view = client.get("/api/manager/forecast", headers=manager).json()
    assert len(view["upcoming"]) >= 28 and view["recent"]
    assert view["live"]["mape"] < 15
    models = client.get("/api/manager/models", headers=manager).json()
    assert {m["kind"] for m in models["models"] if m["trained"]} == {"headcount_cook", "headcount_outlook", "portion", "wait"}
    cook = next(m for m in models["models"] if m["kind"] == "headcount_cook")
    assert any(c["baseline"] for c in cook["candidates"]) and any(not c["baseline"] for c in cook["candidates"])


def test_changing_the_food_chart_changes_upcoming_days_and_their_forecast(client, manager, db, tenant):
    menu = client.get("/api/manager/menu", headers=manager).json()
    weekday = (clock.local_today(tenant.timezone) + timedelta(days=2)).weekday()
    day = clock.local_today(tenant.timezone) + timedelta(days=2)
    current = menu["chart"][weekday]["meals"]["dinner"]
    replacement = next(d["id"] for d in menu["dishes"] if d["category"] == "sabzi" and d["id"] not in current)
    new_ids = [*current[:-1], replacement]
    updated = client.put("/api/manager/menu", headers=manager, json={"weekday": weekday, "meal": "dinner", "dish_ids": new_ids})
    assert updated.status_code == 200 and updated.json()["chart"][weekday]["meals"]["dinner"] == new_ids
    rows = db.scalars(select(DishService).where(DishService.tenant_id == tenant.id, DishService.day == day, DishService.meal == "dinner")).all()
    assert {row.dish_id for row in rows} == set(new_ids)
    assert all(row.recommended_kg and row.recommended_kg > 0 for row in rows)
    duplicate = client.put("/api/manager/menu", headers=manager, json={"weekday": weekday, "meal": "dinner", "dish_ids": [current[0], current[0]]})
    assert duplicate.status_code == 422
    client.put("/api/manager/menu", headers=manager, json={"weekday": weekday, "meal": "dinner", "dish_ids": current})


def test_a_safer_service_level_cooks_more(client, manager, kitchen):
    def advised():
        sheet = client.get("/api/kitchen/sheet", headers=kitchen).json()
        target = next(s for s in sheet["sittings"][::-1])
        return client.get("/api/kitchen/sheet", headers=kitchen, params=target).json()

    lean = client.put("/api/manager/settings", headers=manager, json={"service_level": 0.9})
    assert lean.status_code == 200
    low = advised()
    client.put("/api/manager/settings", headers=manager, json={"service_level": 0.98})
    high = advised()
    client.put("/api/manager/settings", headers=manager, json={"service_level": 0.95})
    if not low["final"]:
        assert high["totals"]["advised_kg"] > low["totals"]["advised_kg"]
    assert client.put("/api/manager/settings", headers=manager, json={"service_level": 0.5}).status_code == 422


def test_kitchens_cannot_see_each_other_and_a_new_one_starts_cold(client, db):
    other = Tenant(slug="aravali", name="Aravali Mess", strength=90, created_at=clock.utcnow())
    db.add(other)
    db.flush()
    db.add(User(tenant_id=other.id, email="warden@aravali.test", name="Warden", role="manager", password_hash=hash_password("open-sesame")))
    db.commit()
    assert client.post("/api/auth/login", json={"email": "warden@aravali.test", "password": "nope"}).status_code == 401
    token = client.post("/api/auth/login", json={"email": "warden@aravali.test", "password": "open-sesame"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/manager/overview", headers=headers).json()["empty"] is True
    assert client.get("/api/manager/menu", headers=headers).json()["dishes"] == []
    # With no history the sheet falls back to a plain share of the roll instead of failing.
    sheet = client.get("/api/kitchen/sheet", headers=headers).json()
    assert sheet["headcount"]["model"] == "Starting estimate" and 0 < sheet["headcount"]["expected"] <= 90
    upcoming = db.scalars(select(MealService).where(MealService.tenant_id == other.id)).all()
    assert len(upcoming) >= 8 * len(MEALS) - 4
    analytics.forget_cache()
