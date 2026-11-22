from datetime import datetime, timedelta
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.db import Base, SessionLocal, engine
from app.main import app, local_today
from app.models import Food

from .support import account_headers, authenticated_client


def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(
            Food(
                id="T1",
                name="Món kiểm thử",
                kcal_100g=250,
                protein_100g=10,
                carb_100g=20,
                fat_100g=5,
                source_type="test_fixture",
                source_reference="Synthetic test fixture",
                reference_mass_g=100,
                data_version="test-v1",
                is_verified=False,
                avoid_tags=[],
            )
        )
        db.commit()


def test_confirm_and_dashboard():
    with authenticated_client() as client:
        assert (
            client.post(
                "/api/food-logs",
                json={"food_id": "T1", "grams": 200, "meal_type": "lunch", "confirmed": False},
            ).status_code
            == 422
        )
        response = client.post(
            "/api/food-logs",
            json={"food_id": "T1", "grams": 200, "meal_type": "lunch", "confirmed": True},
        )
        assert response.status_code == 201, response.text
        assert response.json()["nutrition"]["kcal"] == 500
        dashboard = client.get("/api/dashboard").json()
        assert dashboard["totals"]["kcal"] == 500
        assert dashboard["entries"][0]["source_reference"] == "Synthetic test fixture"


def test_scan_reports_classified_failure_without_saving_food(monkeypatch):
    from sqlalchemy import select

    from app.ai import AIServiceError
    from app.models import AiRun

    def unavailable(*args):
        raise AIServiceError("timeout")

    monkeypatch.setattr("app.ai.scan_image", unavailable)
    image = BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    with authenticated_client() as client:
        before = client.get("/api/dashboard").json()
        response = client.post(
            "/api/scan", files={"file": ("food.png", image.getvalue(), "image/png")}
        )
        assert response.status_code == 503
        assert "phản hồi quá lâu" in response.json()["detail"]
        assert client.get("/api/dashboard").json() == before
    with SessionLocal() as db:
        latest = db.scalar(select(AiRun).where(AiRun.purpose == "scan").order_by(AiRun.id.desc()))
        assert latest.status == "timeout"


def test_scan_hides_provider_details_and_preserves_meals(monkeypatch, caplog):
    from app import ai

    secret = "private-provider-key-marker"
    failures = [
        RuntimeError(f"request failed: key={secret}"),
        ai.errors.ClientError(400, {"error": {"message": f"Invalid request key={secret}"}}),
    ]
    image = BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    with authenticated_client() as client:
        before = client.get("/api/dashboard").json()
        for failure in failures:

            def unavailable(*args, error=failure):
                raise error

            monkeypatch.setattr(ai, "scan_image", unavailable)
            response = client.post(
                "/api/scan", files={"file": ("food.png", image.getvalue(), "image/png")}
            )
            assert response.status_code == 503
            assert secret not in response.text
            assert secret not in caplog.text
            assert client.get("/api/dashboard").json() == before


def test_malformed_ai_dishes_return_503_without_changing_meals(monkeypatch):
    from types import SimpleNamespace

    from app import ai

    fake = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(text='{"dishes":"not-a-list"}')
        )
    )
    monkeypatch.setattr(ai, "client", lambda *_: fake)
    image = BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    with authenticated_client() as client:
        before = client.get("/api/dashboard").json()
        response = client.post(
            "/api/scan", files={"file": ("food.png", image.getvalue(), "image/png")}
        )
        assert response.status_code == 503
        assert "sai cấu trúc" in response.json()["detail"]
        assert client.get("/api/dashboard").json() == before


def test_slow_scan_does_not_block_health_endpoint(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered = Event()
    release = Event()

    def slow_scan(*args):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("Test did not release scan")
        return {"dishes": [], "warning": ""}

    monkeypatch.setattr("app.ai.scan_image", slow_scan)
    image = BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    with authenticated_client() as client, ThreadPoolExecutor(max_workers=2) as executor:
        scan_request = executor.submit(
            client.post, "/api/scan", files={"file": ("food.png", image.getvalue(), "image/png")}
        )
        try:
            assert entered.wait(2)
            health_request = executor.submit(client.get, "/api/health")
            assert health_request.result(timeout=2).status_code == 200
        finally:
            release.set()
        assert scan_request.result(timeout=3).status_code == 200


def test_food_history_preserves_daily_targets_and_account_scope(monkeypatch):
    today = local_today()
    yesterday = today - timedelta(days=1)
    day = [yesterday]
    monkeypatch.setattr("app.main.local_today", lambda: day[0])
    headers = account_headers()
    other = account_headers()
    payload = {
        "age": 22,
        "height_cm": 170,
        "weight_kg": 60,
        "target_weight_kg": 65,
        "target_date": (today + timedelta(days=180)).isoformat(),
        "sex": "male",
        "activity_level": "moderate",
        "goal": "gain",
    }
    with authenticated_client() as client:
        saved = client.put("/api/profile", headers=headers, json=payload)
        assert saved.status_code == 200
        original_kcal = saved.json()["daily_targets"]["kcal"]
        logged = client.post(
            "/api/food-logs",
            headers=headers,
            json={
                "food_id": "T1",
                "grams": 100,
                "meal_type": "lunch",
                "confirmed": True,
                "eaten_at": f"{yesterday.isoformat()}T12:00:00+07:00",
            },
        )
        assert logged.status_code == 201
        day[0] = today
        updated = client.put(
            "/api/profile", headers=headers, json={**payload, "activity_level": "sedentary"}
        )
        assert updated.status_code == 200
        assert updated.json()["daily_targets"]["kcal"] != original_kcal
        history = client.get("/api/food-history", headers=headers).json()["days"]
        assert len(history) == 1
        assert history[0]["targets"]["kcal"] == original_kcal
        assert history[0]["assessment"]["status"] == "under"
        assert history[0]["is_today"] is False
        assert client.get("/api/food-history", headers=other).json()["days"] == []


def test_dated_daily_targets_are_scoped_and_reject_past_date():
    deadline = (local_today() + timedelta(days=90)).isoformat()
    first = account_headers()
    second = account_headers()
    with authenticated_client() as client:
        mismatch = client.put(
            "/api/profile",
            headers=first,
            json={"weight_kg": 70, "target_weight_kg": 67, "goal": "gain"},
        )
        assert mismatch.status_code == 422
        assert "Giảm cân" in mismatch.json()["detail"]
        saved = client.put(
            "/api/profile",
            headers=first,
            json={
                "age": 25,
                "height_cm": 170,
                "weight_kg": 70,
                "target_weight_kg": 67,
                "target_date": deadline,
                "sex": "female",
                "activity_level": "moderate",
                "goal": "lose",
            },
        )
        assert saved.status_code == 200
        targets = saved.json()["daily_targets"]
        assert targets["target_date"] == deadline
        assert targets["days_remaining"] == 90
        assert targets["kcal"] >= 1200
        assert targets["protein_g"] == 85
        assert targets["protein_factor"] == 1.2
        assert targets["carb_g"] > 0 and targets["fat_g"] > 0
        assert (
            abs(
                4 * targets["protein_g"]
                + 4 * targets["carb_g"]
                + 9 * targets["fat_g"]
                - targets["kcal"]
            )
            <= 5
        )
        assert client.get("/api/profile", headers=first).json()["daily_targets"] == targets
        assert client.get("/api/profile", headers=second).json()["daily_targets"] is None
        rushed = client.put(
            "/api/profile",
            headers=first,
            json={
                "age": 25,
                "height_cm": 170,
                "weight_kg": 70,
                "target_weight_kg": 60,
                "target_date": (local_today() + timedelta(days=7)).isoformat(),
                "sex": "female",
                "activity_level": "moderate",
                "goal": "lose",
            },
        )
        assert rushed.json()["daily_targets"]["timeline_warning"] is True
        assert rushed.json()["daily_targets"]["kcal"] >= 1200
        strength = client.put(
            "/api/profile",
            headers=first,
            json={
                "age": 25,
                "height_cm": 170,
                "weight_kg": 70,
                "target_weight_kg": 67,
                "target_date": deadline,
                "sex": "female",
                "activity_level": "moderate",
                "protein_mode": "strength",
                "goal": "lose",
            },
        )
        assert strength.json()["daily_targets"]["protein_g"] == 110
        assert strength.json()["daily_targets"]["protein_factor"] == 1.6
        rejected = client.put(
            "/api/profile", headers=first, json={"target_date": local_today().isoformat()}
        )
        assert rejected.status_code == 422


def test_scan_rejects_bad_upload():
    with authenticated_client() as client:
        response = client.post("/api/scan", files={"file": ("bad.txt", b"hello", "text/plain")})
        assert response.status_code == 415


def test_scan_groups_dishes_and_requires_selection(monkeypatch):
    monkeypatch.setattr(
        "app.ai.scan_image",
        lambda *_: {
            "dishes": [
                {
                    "candidate_labels": ["Món kiểm thử"],
                    "visible_ingredients": [],
                    "uncertainty_reason": "",
                },
                {
                    "candidate_labels": ["món không có"],
                    "visible_ingredients": [],
                    "uncertainty_reason": "Không rõ",
                },
            ],
            "warning": "",
        },
    )
    image = BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    first = account_headers()
    second = account_headers()
    with authenticated_client() as client:
        response = client.post(
            "/api/scan",
            headers=first,
            files={"file": ("meal.png", image.getvalue(), "image/png")},
            data={"meal_type": "dinner"},
        )
        assert response.status_code == 200
        dishes = response.json()["dishes"]
        assert len(dishes) == 2
        assert dishes[0]["candidates"][0]["id"] == "T1"
        assert dishes[1]["candidates"] == []
        assert client.get("/api/scan-history", headers=first).json()["items"] == []
        pending_image_url = f"/api/scan-history/{response.json()['request_id']}/image"
        assert client.get(pending_image_url, headers=first).status_code == 404
        assert client.get("/api/scan-history", headers=second).json()["items"] == []

        confirmation = {
            "confirmation_id": response.json()["request_id"],
            "items": [{"food_id": "T1", "grams": 100, "meal_type": "dinner", "confirmed": True}],
        }
        assert (
            client.post("/api/food-logs/batch", headers=first, json=confirmation).status_code == 201
        )
        confirmed = client.get("/api/scan-history", headers=first).json()["items"][0]
        assert confirmed["meal_type"] == "dinner"
        assert confirmed["confirmed_at"] is not None
        assert datetime.fromisoformat(confirmed["created_at"]).utcoffset() == timedelta(0)
        assert datetime.fromisoformat(confirmed["confirmed_at"]).utcoffset() == timedelta(0)
        assert client.get("/api/dashboard", headers=first).json()["totals"]["kcal"] == 250
        image_response = client.get(confirmed["image_url"], headers=first)
        assert image_response.status_code == 200
        assert image_response.headers["content-type"] == "image/webp"
        assert client.get(confirmed["image_url"], headers=second).status_code == 404


def test_scan_returns_editable_nutrition_estimate(monkeypatch):
    monkeypatch.setattr(
        "app.ai.scan_image",
        lambda *_: {
            "dishes": [
                {
                    "candidate_labels": ["Sườn sốt cà chua"],
                    "visible_ingredients": ["Sườn"],
                    "uncertainty_reason": "",
                    "estimated_nutrition_100g": {"kcal": 185, "protein": 15, "carb": 5, "fat": 12},
                }
            ],
            "warning": "",
        },
    )
    image = BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    with authenticated_client() as client:
        dish = client.post(
            "/api/scan", files={"file": ("meal.png", image.getvalue(), "image/png")}
        ).json()["dishes"][0]
        assert dish["estimated_nutrition_100g"] == {
            "kcal": 185,
            "protein": 15,
            "carb": 5,
            "fat": 12,
        }


def test_unknown_dish_per_gram_estimate_scales_when_confirmed(monkeypatch):
    monkeypatch.setattr(
        "app.ai.scan_image",
        lambda *_: {
            "dishes": [
                {
                    "candidate_labels": ["Món đặc biệt chưa có trong danh mục"],
                    "confidence": 0.8,
                    "visible_ingredients": [],
                    "uncertainty_reason": "Chưa rõ lượng dầu",
                    "estimated_nutrition_1g": {
                        "kcal": 1.85,
                        "protein": 0.15,
                        "carb": 0.05,
                        "fat": 0.12,
                    },
                }
            ],
            "warning": "",
        },
    )
    image = BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    headers = account_headers()
    with authenticated_client() as client:
        response = client.post(
            "/api/scan",
            headers=headers,
            files={"file": ("food.png", image.getvalue(), "image/png")},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "needs_confirmation"
        dish = result["dishes"][0]
        assert dish["candidates"] == []
        assert dish["estimated_nutrition_1g"]["protein"] == 0.15
        assert dish["estimated_nutrition_100g"]["kcal"] == 185
        assert client.get("/api/dashboard", headers=headers).json()["totals"]["kcal"] == 0
        confirmed = client.post(
            "/api/food-logs/batch",
            headers=headers,
            json={
                "confirmation_id": result["request_id"],
                "items": [
                    {
                        "custom_food": {
                            "name": dish["suggested_labels"][0],
                            **{
                                f"{key}_100g": value
                                for key, value in dish["estimated_nutrition_100g"].items()
                            },
                        },
                        "grams": 200,
                        "meal_type": "lunch",
                        "confirmed": True,
                    }
                ],
            },
        )
        assert confirmed.status_code == 201
        assert confirmed.json()["entries"][0]["nutrition"] == {
            "kcal": 370,
            "protein": 30,
            "carb": 10,
            "fat": 24,
        }
        assert client.get("/api/dashboard", headers=headers).json()["totals"]["kcal"] == 370


def test_csv_catalog_is_used_for_scan_and_serving_nutrition(monkeypatch):
    captured = {}

    def fake_scan(_raw, _content_type, catalog, _avoid_tags):
        captured["catalog"] = catalog
        return {
            "dishes": [
                {
                    "candidate_labels": ["Phở gà"],
                    "visible_ingredients": ["Bánh phở", "Thịt gà"],
                    "uncertainty_reason": "",
                }
            ],
            "warning": "",
        }

    monkeypatch.setattr("app.ai.scan_image", fake_scan)
    image = BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    with authenticated_client() as client:
        result = client.post(
            "/api/scan", files={"file": ("pho.png", image.getvalue(), "image/png")}
        )
        assert result.status_code == 200
        candidate = result.json()["dishes"][0]["candidates"][0]
        assert candidate["id"] == "F_0332"
        assert candidate["basis_label"] == "1 tô (500g)"
        assert any(item["name"] == "Phở gà" for item in captured["catalog"])
        rejected = client.post(
            "/api/food-logs",
            json={"food_id": "F_0332", "grams": 1.5, "meal_type": "lunch", "confirmed": True},
        )
        assert rejected.status_code == 422
        assert "số nguyên" in rejected.json()["detail"]
        logged = client.post(
            "/api/food-logs",
            json={"food_id": "F_0332", "grams": 2, "meal_type": "lunch", "confirmed": True},
        )
        assert logged.status_code == 201
        assert logged.json()["unit"] == "tô"
        assert logged.json()["nutrition"]["kcal"] == 800


def test_scan_warns_and_requires_acknowledgement_for_avoided_ingredient(monkeypatch):
    monkeypatch.setattr(
        "app.ai.scan_image",
        lambda *_: {
            "dishes": [
                {
                    "candidate_labels": ["Phở gà"],
                    "visible_ingredients": ["Thịt gà", "Bánh phở"],
                    "uncertainty_reason": "",
                }
            ],
            "warning": "",
        },
    )
    image = BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    headers = account_headers()
    with authenticated_client() as client:
        saved = client.put("/api/profile", headers=headers, json={"avoid_tags": ["thịt"]})
        assert saved.status_code == 200
        scan = client.post(
            "/api/scan", headers=headers, files={"file": ("pho.png", image.getvalue(), "image/png")}
        ).json()
        assert scan["dishes"][0]["avoid_matches"] == ["thịt"]
        payload = {
            "confirmation_id": scan["request_id"],
            "items": [{"food_id": "F_0332", "grams": 1, "meal_type": "lunch", "confirmed": True}],
        }
        blocked = client.post("/api/food-logs/batch", headers=headers, json=payload)
        assert blocked.status_code == 422
        assert "thành phần cần tránh" in blocked.json()["detail"]
        payload["avoidance_acknowledged"] = True
        accepted = client.post("/api/food-logs/batch", headers=headers, json=payload)
        assert accepted.status_code == 201


def test_zero_nutrition_custom_food_can_be_corrected():
    headers = account_headers()
    first = {
        "items": [
            {
                "custom_food": {"name": "Món thiếu số liệu"},
                "grams": 100,
                "meal_type": "lunch",
                "confirmed": True,
            }
        ]
    }
    updated = {
        "items": [
            {
                "custom_food": {
                    "name": "Món thiếu số liệu",
                    "kcal_100g": 185,
                    "protein_100g": 15,
                    "carb_100g": 5,
                    "fat_100g": 12,
                },
                "grams": 200,
                "meal_type": "dinner",
                "confirmed": True,
            }
        ]
    }
    with authenticated_client() as client:
        assert client.post("/api/food-logs/batch", headers=headers, json=first).status_code == 201
        corrected = client.post("/api/food-logs/batch", headers=headers, json=updated)
        assert corrected.status_code == 201
        assert corrected.json()["entries"][0]["nutrition"]["kcal"] == 370
        assert corrected.json()["entries"][0]["nutrition"]["protein"] == 30


def test_batch_logs_are_all_or_nothing():
    valid = {"food_id": "T1", "grams": 100, "meal_type": "lunch", "confirmed": True}
    invalid = {**valid, "food_id": "UNKNOWN"}
    with authenticated_client() as client:
        before = len(client.get("/api/dashboard").json()["entries"])
        assert (
            client.post("/api/food-logs/batch", json={"items": [valid, invalid]}).status_code == 404
        )
        assert len(client.get("/api/dashboard").json()["entries"]) == before
        response = client.post("/api/food-logs/batch", json={"items": [valid, valid]})
        assert response.status_code == 201
        assert len(response.json()["entries"]) == 2


def test_log_can_be_edited_and_deleted():
    with authenticated_client() as client:
        created = client.post(
            "/api/food-logs",
            json={"food_id": "T1", "grams": 100, "meal_type": "lunch", "confirmed": True},
        ).json()
        changed = client.patch(
            f"/api/food-logs/{created['id']}", json={"grams": 200, "meal_type": "dinner"}
        )
        assert changed.status_code == 200
        assert changed.json()["nutrition"]["kcal"] == 500
        assert changed.json()["meal_type"] == "dinner"
        assert client.delete(f"/api/food-logs/{created['id']}").status_code == 204
        assert (
            client.patch(
                f"/api/food-logs/{created['id']}", json={"grams": 100, "meal_type": "lunch"}
            ).status_code
            == 404
        )


def test_repeated_confirmation_does_not_duplicate_meals():
    payload = {
        "confirmation_id": "demo-confirmation-001",
        "items": [{"food_id": "T1", "grams": 150, "meal_type": "lunch", "confirmed": True}],
    }
    with authenticated_client() as client:
        before = len(client.get("/api/dashboard").json()["entries"])
        first = client.post("/api/food-logs/batch", json=payload)
        second = client.post("/api/food-logs/batch", json=payload)
        assert first.status_code == second.status_code == 201
        assert first.json()["entries"][0]["id"] == second.json()["entries"][0]["id"]
        assert len(client.get("/api/dashboard").json()["entries"]) == before + 1
        changed = {**payload, "items": [{**payload["items"][0], "grams": 200}]}
        assert client.post("/api/food-logs/batch", json=changed).status_code == 409


def test_custom_food_can_be_confirmed_and_replayed():
    payload = {
        "confirmation_id": "custom-confirmation-001",
        "items": [
            {
                "custom_food": {
                    "name": "Món mới kiểm thử",
                    "kcal_100g": 120,
                    "protein_100g": 5,
                    "carb_100g": 15,
                    "fat_100g": 3,
                },
                "grams": 200,
                "meal_type": "dinner",
                "confirmed": True,
            }
        ],
    }
    with authenticated_client() as client:
        before = client.get("/api/dashboard").json()["totals"]["kcal"]
        first = client.post("/api/food-logs/batch", json=payload)
        assert first.status_code == 201
        assert first.json()["entries"][0]["nutrition"]["kcal"] == 240
        assert first.json()["entries"][0]["is_verified"] is False
        second = client.post("/api/food-logs/batch", json=payload)
        assert second.json()["entries"][0]["id"] == first.json()["entries"][0]["id"]
        assert client.get("/api/dashboard").json()["totals"]["kcal"] == before + 240
        assert (
            client.get("/api/foods", params={"q": "Món mới kiểm thử"}).json()[0]["source_type"]
            == "user_entered"
        )


def test_manual_food_matching_catalog_is_confirmed_as_catalog_food():
    payload = {
        "items": [
            {
                "custom_food": {"name": "món kiểm thử", "kcal_100g": 1},
                "grams": 100,
                "meal_type": "lunch",
                "confirmed": True,
            }
        ]
    }
    with authenticated_client() as client:
        response = client.post("/api/food-logs/batch", json=payload)
        assert response.status_code == 201
        assert response.json()["entries"][0]["food_id"] == "T1"
        assert response.json()["entries"][0]["nutrition"]["kcal"] == 250


def test_custom_100g_input_does_not_silently_become_a_serving_item():
    payload = {
        "items": [
            {
                "custom_food": {
                    "name": "Phở gà",
                    "kcal_100g": 100,
                    "protein_100g": 5,
                    "carb_100g": 15,
                    "fat_100g": 2,
                },
                "grams": 100,
                "meal_type": "lunch",
                "confirmed": True,
            }
        ]
    }
    headers = account_headers()
    with authenticated_client() as client:
        response = client.post("/api/food-logs/batch", headers=headers, json=payload)
        assert response.status_code == 201
        entry = response.json()["entries"][0]
        assert entry["food_id"] != "F_0332"
        assert entry["unit"] == "g"
        assert entry["nutrition"]["kcal"] == 100


def test_private_routes_require_authenticated_account():
    with TestClient(app) as client:
        assert client.get("/api/profile").status_code == 401
        assert client.get("/api/profile", headers={"X-Visitor-Id": "not-a-uuid"}).status_code == 401
        assert (
            client.get(
                "/api/profile", headers={"X-Visitor-Id": "33333333-3333-4333-8333-333333333333"}
            ).status_code
            == 401
        )
