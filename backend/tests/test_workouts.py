from datetime import date

from fastapi.testclient import TestClient

from app.main import app

from .support import authenticated_client, register_account


def finish_session(client, items):
    for item in items:
        if item["status"] != "completed":
            assert client.post(f"/api/workouts/{item['id']}/start").status_code == 200
            assert client.post(f"/api/workouts/{item['id']}/complete").status_code == 200


def test_plans_have_specific_exercises_and_instructions():
    with authenticated_client() as client:
        plans = client.get("/api/workouts/plans").json()
        assert {(p["goal"], p["method"]) for p in plans} == {
            ("gain", "PPL"),
            ("gain", "UL"),
            ("lose", "PPL"),
            ("lose", "UL"),
        }
        selected = client.post("/api/workouts/select", json={"plan_id": "gain_ppl"}).json()
        assert selected["session_name"] == "Push"
        assert all(item["steps"] and item["focus"] for item in selected["items"])
        pull = plans[0]["session_exercises"][1]
        assert any("Lat Pulldown" in i["name"] for i in pull)
        assert any("Seated Cable Row" in i["name"] for i in pull)
        assert (
            client.post("/api/workouts/select", json={"plan_id": "not-a-plan"}).status_code == 404
        )


def test_skip_partial_progress_next_session_and_independent_nutrition(monkeypatch):
    day = [date(2026, 11, 22)]
    monkeypatch.setattr("app.workout_routes.local_today", lambda: day[0])
    with authenticated_client() as client:
        before = client.get("/api/dashboard").json()
        assert (
            client.post("/api/workouts/attendance", json={"status": "attended"}).status_code == 409
        )
        today = client.post("/api/workouts/select", json={"plan_id": "gain_ppl"}).json()
        first = today["items"][0]["id"]
        assert client.post(f"/api/workouts/{first}/start").status_code == 409
        client.post("/api/workouts/attendance", json={"status": "missed"})
        day[0] = date(2026, 11, 23)
        assert client.get("/api/workouts/today").json()["session_name"] == "Push"
        client.post("/api/workouts/attendance", json={"status": "attended"})
        assert client.post(f"/api/workouts/{first}/complete").status_code == 409
        client.post(f"/api/workouts/{first}/start")
        client.post(f"/api/workouts/{first}/complete")
        day[0] = date(2026, 11, 24)
        partial = client.get("/api/workouts/today").json()
        assert partial["items"][0]["status"] == "completed"
        client.post("/api/workouts/attendance", json={"status": "attended"})
        finish_session(client, partial["items"])
        done = client.get("/api/workouts/today").json()
        assert done["attendance"] == "completed"
        assert client.post(f"/api/workouts/{first}/complete").status_code == 200
        assert client.post("/api/workouts/attendance", json={"status": "missed"}).status_code == 409
        assert client.get("/api/workouts/today").json()["completed_sessions"] == 1
        day[0] = date(2026, 11, 25)
        assert client.get("/api/workouts/today").json()["session_name"] == "Pull"
        calendar = client.get("/api/workouts/attendance?month=2026-11").json()
        assert calendar["days"][21]["status"] == "missed"
        assert calendar["days"][23]["status"] == "completed"
        assert calendar["days"][24]["status"] is None
        assert calendar["attended_count"] == 2 and calendar["missed_count"] == 1
        assert client.get("/api/dashboard").json() == before


def test_switching_plan_preserves_calendar_and_separate_progress():
    with authenticated_client() as client:
        first = client.post("/api/workouts/select", json={"plan_id": "gain_ppl"}).json()
        client.post("/api/workouts/attendance", json={"status": "attended"})
        exercise = first["items"][0]["id"]
        client.post(f"/api/workouts/{exercise}/start")
        client.post(f"/api/workouts/{exercise}/complete")
        second = client.post("/api/workouts/select", json={"plan_id": "lose_ul"}).json()
        assert all(i["status"] == "not_started" for i in second["items"])
        month = second["date"][:7]
        assert client.get(f"/api/workouts/attendance?month={month}").json()["attended_count"] == 1
        resumed = client.post("/api/workouts/select", json={"plan_id": "gain_ppl"}).json()
        assert resumed["items"][0]["status"] == "completed"


def test_workout_selection_attendance_and_progress_are_user_scoped():
    with TestClient(app) as client:
        a, b = register_account(client), register_account(client)
        ha = {"Authorization": f"Bearer {a['access_token']}"}
        hb = {"Authorization": f"Bearer {b['access_token']}", "X-Visitor-Id": a["user"]["id"]}
        data = client.post("/api/workouts/select", headers=ha, json={"plan_id": "gain_ul"}).json()
        client.post("/api/workouts/attendance", headers=ha, json={"status": "attended"})
        first = data["items"][0]["id"]
        client.post(f"/api/workouts/{first}/start", headers=ha)
        assert client.get("/api/workouts/today", headers=hb).json()["selected_plan"] is None
        assert client.post(f"/api/workouts/{first}/complete", headers=hb).status_code == 404
        selected = client.post(
            "/api/workouts/select", headers=hb, json={"plan_id": "gain_ul"}
        ).json()
        assert all(i["status"] == "not_started" for i in selected["items"])
        calendar = client.get(
            f"/api/workouts/attendance?month={data['date'][:7]}", headers=hb
        ).json()
        assert calendar["attended_count"] == 0
        assert (
            client.post(
                "/api/workouts/attendance", headers=hb, json={"status": "missed"}
            ).status_code
            == 200
        )
        assert client.get("/api/workouts/today", headers=ha).json()["attendance"] == "attended"
        assert (
            client.get("/api/workouts/today", headers=ha).json()["items"][0]["status"] == "started"
        )


def test_cycle_wrap_does_not_reuse_completed_exercises(monkeypatch):
    day = [date(2026, 11, 1)]
    monkeypatch.setattr("app.workout_routes.local_today", lambda: day[0])
    with authenticated_client() as client:
        client.post("/api/workouts/select", json={"plan_id": "gain_ul"})
        for n in range(1, 5):
            day[0] = date(2026, 11, n)
            data = client.post("/api/workouts/attendance", json={"status": "attended"}).json()
            finish_session(client, data["items"])
        day[0] = date(2026, 11, 5)
        data = client.get("/api/workouts/today").json()
        assert data["session_number"] == 1 and data["completed_sessions"] == 4
        assert all(i["status"] == "not_started" for i in data["items"])


def test_calendar_validates_month_and_handles_leap_year():
    with authenticated_client() as client:
        assert client.get("/api/workouts/attendance?month=0000-01").status_code == 422
        assert client.get("/api/workouts/attendance?month=2026-13").status_code == 422
        assert len(client.get("/api/workouts/attendance?month=2028-02").json()["days"]) == 29
        assert len(client.get("/api/workouts/attendance?month=9999-12").json()["days"]) == 31
