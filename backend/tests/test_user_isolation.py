"""Kiểm tra quyền bằng hai tài khoản thật, kể cả khi cố giả mạo ID từ frontend."""

import uuid
from datetime import timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app import auth
from app.db import SessionLocal
from app.main import app, local_today
from app.models import BatchSubmission, FoodLog, ScanHistory, User

from .support import authenticated_client, register_account


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/api/profile", None),
        ("get", "/api/foods", None),
        ("get", "/api/dashboard", None),
        ("get", "/api/food-history", None),
        ("get", "/api/scan-history", None),
        ("get", "/api/scan-history/unknown/image", None),
        ("get", "/api/workouts/plans", None),
        ("get", "/api/workouts/today", None),
        ("get", "/api/workouts/attendance?month=2026-11", None),
        ("post", "/api/workouts/select", {"plan_id": "gain_ppl"}),
        ("post", "/api/workouts/attendance", {"status": "attended"}),
        ("patch", "/api/food-logs/1", {"grams": 100, "meal_type": "lunch"}),
        ("delete", "/api/food-logs/1", None),
    ],
)
def test_anonymous_or_visitor_header_cannot_access_private_routes(method, path, payload):
    with TestClient(app) as client:
        options = {"headers": {"X-Visitor-Id": str(uuid.uuid4())}}
        if payload is not None:
            options["json"] = payload
        assert getattr(client, method)(path, **options).status_code == 401


def test_login_normalization_password_hash_and_invalid_tokens(monkeypatch):
    with TestClient(app) as client:
        data = register_account(client)
        username = data["user"]["username"]
        with SessionLocal() as db:
            user = db.get(User, data["user"]["id"])
            assert user.password_hash.startswith("pbkdf2_sha256$")
            assert "test-password-123" not in user.password_hash
        assert (
            client.post(
                "/api/auth/login", json={"username": username.upper(), "password": "wrong"}
            ).status_code
            == 401
        )
        logged = client.post(
            "/api/auth/login", json={"username": username.upper(), "password": "test-password-123"}
        )
        assert logged.status_code == 200
        assert logged.json()["user"]["id"] == data["user"]["id"]
        assert (
            client.post(
                "/api/auth/register", json={"username": username, "password": "test-password-123"}
            ).status_code
            == 409
        )
        for token in ["invalid", data["access_token"] + "x", auth.create_token(str(uuid.uuid4()))]:
            assert (
                client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
                == 401
            )
        monkeypatch.setattr(auth.time, "time", lambda: 0)
        expired = auth.create_token(data["user"]["id"])
        monkeypatch.undo()
        assert (
            client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code
            == 401
        )


def test_user_id_in_payload_is_rejected_and_headers_do_not_switch_account():
    with TestClient(app) as client:
        first, second = register_account(client), register_account(client)
        a = {"Authorization": f"Bearer {first['access_token']}"}
        b = {
            "Authorization": f"Bearer {second['access_token']}",
            "X-Visitor-Id": first["user"]["id"],
        }
        profile = {
            "age": 22,
            "height_cm": 170,
            "weight_kg": 65,
            "target_weight_kg": 68,
            "goal": "gain",
            "target_date": (local_today() + timedelta(days=180)).isoformat(),
        }
        assert client.put("/api/profile", headers=a, json=profile).status_code == 200
        assert client.get("/api/profile", headers=b).json()["daily_targets"] is None
        assert (
            client.put(
                "/api/profile", headers=b, json={**profile, "user_id": first["user"]["id"]}
            ).status_code
            == 422
        )
        assert client.get("/api/auth/me", headers=b).json()["id"] == second["user"]["id"]
        assert client.put("/api/profile", headers=b, json={"weight_kg": 80}).status_code == 200
        assert client.get("/api/profile", headers=a).json()["weight_kg"] == 65


def test_private_food_logs_history_and_images_are_account_scoped(monkeypatch):
    monkeypatch.setattr(
        "app.ai.scan_image",
        lambda *_: {
            "dishes": [
                {
                    "candidate_labels": ["Phở gà"],
                    "visible_ingredients": ["thịt gà"],
                    "confidence": 0.9,
                    "uncertainty_reason": "",
                }
            ],
            "warning": "",
        },
    )
    image = BytesIO()
    Image.new("RGB", (24, 24), "white").save(image, "PNG")
    with TestClient(app) as client:
        first, second = register_account(client), register_account(client)
        a = {"Authorization": f"Bearer {first['access_token']}"}
        b = {"Authorization": f"Bearer {second['access_token']}"}
        scanned = client.post(
            "/api/scan", headers=a, files={"file": ("meal.png", image.getvalue(), "image/png")}
        ).json()
        history_id = scanned["request_id"]
        payload = {
            "confirmation_id": history_id,
            "items": [
                {
                    "custom_food": {
                        "name": "Món riêng của tài khoản",
                        "kcal_100g": 150,
                        "protein_100g": 10,
                        "carb_100g": 15,
                        "fat_100g": 5,
                    },
                    "grams": 200,
                    "meal_type": "lunch",
                    "confirmed": True,
                }
            ],
        }
        assert client.post("/api/food-logs/batch", headers=b, json=payload).status_code == 404
        response = client.post("/api/food-logs/batch", headers=a, json=payload)
        assert response.status_code == 201, response.text
        entry = response.json()["entries"][0]
        assert client.get(f"/api/foods/{entry['food_id']}", headers=b).status_code == 404
        assert not client.get("/api/foods?q=Món riêng", headers=b).json()
        assert client.get("/api/dashboard", headers=b).json()["entries"] == []
        assert client.get("/api/food-history", headers=b).json()["days"] == []
        assert client.get("/api/scan-history", headers=b).json()["items"] == []
        assert (
            client.patch(
                f"/api/food-logs/{entry['id']}",
                headers=b,
                json={"grams": 100, "meal_type": "dinner"},
            ).status_code
            == 404
        )
        assert client.delete(f"/api/food-logs/{entry['id']}", headers=b).status_code == 404
        assert (
            client.post(
                "/api/food-logs",
                headers=b,
                json={
                    "food_id": entry["food_id"],
                    "grams": 100,
                    "meal_type": "lunch",
                    "confirmed": True,
                },
            ).status_code
            == 404
        )
        url = f"/api/scan-history/{history_id}/image"
        assert client.get(url, headers=b).status_code == 404
        assert client.get(url, headers=a).status_code == 200
        with SessionLocal() as db:
            record = db.get(ScanHistory, history_id)
            assert record.user_id == first["user"]["id"]
            assert isinstance(record.image_key, str) and record.image_key.endswith(".webp")
            assert db.get(FoodLog, entry["id"]).user_id == first["user"]["id"]
        assert client.get("/api/dashboard", headers=a).json()["totals"]["kcal"] == 300


def test_deleted_account_token_cannot_be_reused():
    with TestClient(app) as client:
        data = register_account(client)
        with SessionLocal() as db:
            db.delete(db.get(User, data["user"]["id"]))
            db.commit()
        assert (
            client.get(
                "/api/dashboard", headers={"Authorization": f"Bearer {data['access_token']}"}
            ).status_code
            == 401
        )


def test_local_signing_secret_is_random_and_persistent(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(auth, "__file__", str(tmp_path / "app" / "auth.py"))
    one, two = auth._secret(), auth._secret()
    assert one == two and len(one) >= 32
    assert one != b"hbtnfit-local-development-secret"


def test_legacy_confirmation_keeps_idempotency_after_owner_migration():
    with authenticated_client() as client:
        food_id = next(f["id"] for f in client.get("/api/foods").json() if f["basis_unit"] == "g")
        payload = {
            "confirmation_id": "migration-check-" + uuid.uuid4().hex,
            "items": [
                {
                    "food_id": food_id,
                    "grams": 100,
                    "meal_type": "lunch",
                    "confirmed": True,
                }
            ],
        }
        first = client.post("/api/food-logs/batch", json=payload)
        assert first.status_code == 201
        uid = client.get("/api/auth/me").json()["id"]
        with SessionLocal() as db:
            submission = db.scalar(select(BatchSubmission).where(BatchSubmission.user_id == uid))
            submission.user_id = None
            db.commit()
        repeated = client.post("/api/food-logs/batch", json=payload)
        assert repeated.status_code == 201
        assert repeated.json() == first.json()
        assert len(client.get("/api/dashboard").json()["entries"]) == 1
