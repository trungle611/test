"""Tính thử, lưu bốn chỉ số, chọn thực đơn và lỗi AI không làm mất mục tiêu."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import ai
from app.db import SessionLocal
from app.main import app, local_today
from app.models import Food

from .support import authenticated_client, register_account


def profile_input(**changes):
    return {
        "age": 22,
        "height_cm": 170,
        "weight_kg": 65,
        "target_weight_kg": 68,
        "target_date": (local_today() + timedelta(days=365)).isoformat(),
        "sex": "male",
        "activity_level": "moderate",
        "protein_mode": "balanced",
        "goal": "gain",
        "avoid_tags": [],
        "target_kcal": 1800,
        **changes,
    }


def test_preview_does_not_save_and_save_updates_dashboard_four_targets():
    with authenticated_client() as client:
        before = client.get("/api/profile").json()
        response = client.post("/api/profile/preview", json=profile_input())
        assert response.status_code == 200, response.text
        targets = response.json()["daily_targets"]
        assert all(targets[k] > 0 for k in ("kcal", "protein_g", "carb_g", "fat_g"))
        energy = targets["protein_g"] * 4 + targets["carb_g"] * 4 + targets["fat_g"] * 9
        assert abs(energy - targets["kcal"]) <= 5
        assert client.get("/api/profile").json() == before
        saved = client.put("/api/profile", json=profile_input())
        assert saved.status_code == 200, saved.text
        assert saved.json()["daily_targets"] == targets
        assert client.get("/api/profile").json()["daily_targets"] == targets
        assert client.get("/api/dashboard").json()["totals"]["kcal"] == 0


@pytest.mark.parametrize(
    "values",
    [
        {"goal": "lose"},
        {"target_weight_kg": 60},
        {"target_date": local_today().isoformat()},
        {"age": 17},
        {"sex": None},
    ],
)
def test_invalid_goal_preview_rejected_without_changing_saved_profile(values):
    with authenticated_client() as client:
        client.put("/api/profile", json=profile_input())
        before = client.get("/api/profile").json()
        assert client.post("/api/profile/preview", json=profile_input(**values)).status_code == 422
        assert client.get("/api/profile").json() == before


@pytest.mark.parametrize(
    "current,target,goal", [(65, 60, "lose"), (65, 65, "maintain"), (65, 68, "gain")]
)
def test_consistent_goals_are_accepted(current, target, goal):
    with authenticated_client() as client:
        assert (
            client.put(
                "/api/profile",
                json=profile_input(weight_kg=current, target_weight_kg=target, goal=goal),
            ).status_code
            == 200
        )


def valid_guidance(*args):
    with SessionLocal() as db:
        foods = db.scalars(
            select(Food)
            .where(
                Food.owner_id.is_(None),
                Food.catalog_kind == "dish",
                Food.kcal_100g.between(300, 600),
            )
            .limit(3)
        ).all()
        assert len(foods) == 3
        examples = [
            {"food_id": food.id, "meal_type": meal}
            for food, meal in zip(foods, ("breakfast", "lunch", "dinner"))
        ]
    return {
        "summary": "Gợi ý phù hợp mục tiêu đã lưu.",
        "ppl_note": "Tập theo buổi Push, Pull, Legs.",
        "ul_note": "Luân phiên thân trên và thân dưới.",
        "food_options": [
            {"title": f"Thực đơn {i}", "detail": "Có đủ ba bữa trong ngày.", "examples": examples}
            for i in (1, 2)
        ],
    }


def test_guidance_choice_three_meals_tick_and_owner_isolation(monkeypatch):
    monkeypatch.setattr(ai, "generate_profile_guidance", valid_guidance)
    with authenticated_client() as client:
        client.put("/api/profile", json=profile_input())
        response = client.post("/api/profile/analyze")
        assert response.status_code == 200, response.text
        analysis = response.json()["analysis"]
        assert len(analysis["food_options"]) == 2
        option = analysis["food_options"][0]
        assert (
            abs(option["estimated_totals"]["kcal"] - response.json()["daily_targets"]["kcal"]) < 100
        )
        chosen = client.post(
            "/api/profile/choice", json={"food_choice": option["id"], "workout_choice": "gain_ul"}
        )
        assert chosen.status_code == 200, chosen.text
        checklist = chosen.json()["food_checklist"]
        assert {i["meal_type"] for i in checklist} == {"breakfast", "lunch", "dinner"}
        item = checklist[0]
        tick = client.patch(
            f"/api/profile/food-checklist/{item['id']}",
            json={"completed": True, "amount": item["amount"]},
        )
        assert tick.status_code == 200, tick.text
        assert len(client.get("/api/dashboard").json()["entries"]) == 1
        # Chọn lại cùng thực đơn không được mất trạng thái tick hoặc tạo món trùng.
        again = client.post("/api/profile/choice", json={"food_choice": option["id"]})
        assert again.json()["food_checklist"][0]["completed"] is True
        other = register_account(client)
        headers = {"Authorization": f"Bearer {other['access_token']}"}
        assert client.get("/api/profile", headers=headers).json()["daily_targets"] is None
        assert (
            client.post(
                "/api/profile/choice", headers=headers, json={"food_choice": option["id"]}
            ).status_code
            == 409
        )


def test_ai_failure_and_unknown_food_preserve_saved_goals(monkeypatch):
    def failed(*args):
        raise ai.AIServiceError("AI đang bận. Hãy thử lại sau.")

    with authenticated_client() as client:
        client.put("/api/profile", json=profile_input())
        before = client.get("/api/profile").json()
        monkeypatch.setattr(ai, "generate_profile_guidance", failed)
        assert client.post("/api/profile/analyze").status_code == 503
        assert client.get("/api/profile").json() == before
        result = valid_guidance()
        result["food_options"][0]["examples"][0]["food_id"] = "unknown-csv-food"
        monkeypatch.setattr(ai, "generate_profile_guidance", lambda *args: result)
        assert client.post("/api/profile/analyze").status_code == 503
        assert client.get("/api/profile").json() == before


def test_profile_change_during_ai_does_not_store_stale_advice(monkeypatch):
    with authenticated_client() as client:
        client.put("/api/profile", json=profile_input())

        def changed(*args):
            assert (
                client.put("/api/profile", json=profile_input(target_weight_kg=69)).status_code
                == 200
            )
            return valid_guidance()

        monkeypatch.setattr(ai, "generate_profile_guidance", changed)
        assert client.post("/api/profile/analyze").status_code == 409
        assert client.get("/api/profile").json()["analysis"] is None


def test_new_profile_routes_require_authentication():
    with TestClient(app) as client:
        for path in ("preview", "analyze", "choice"):
            assert client.post(f"/api/profile/{path}", json={}).status_code == 401
