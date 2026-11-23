"""Đăng xuất thu hồi đúng phiên, không xóa dữ liệu hay phiên thiết bị khác."""

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import AuthSession

from .support import register_account


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_logout_revokes_only_current_session_and_preserves_account():
    with TestClient(app) as client:
        account = register_account(client)
        first = account["access_token"]
        credentials = {"username": account["user"]["username"], "password": "test-password-123"}
        second = client.post("/api/auth/login", json=credentials).json()["access_token"]
        assert first != second
        with SessionLocal() as db:
            stored = db.get(AuthSession, hashlib.sha256(first.encode()).hexdigest())
            assert stored and stored.user_id == account["user"]["id"]
            assert stored.token_hash != first
        assert client.post("/api/auth/logout", headers=bearer(first)).status_code == 204
        assert client.get("/api/auth/me", headers=bearer(first)).status_code == 401
        assert client.get("/api/profile", headers=bearer(first)).status_code == 401
        assert client.get("/api/auth/me", headers=bearer(second)).status_code == 200
        assert client.post("/api/auth/login", json=credentials).status_code == 200


def test_expired_server_session_rejects_otherwise_valid_token():
    with TestClient(app) as client:
        token = register_account(client)["access_token"]
        with SessionLocal() as db:
            session = db.get(AuthSession, hashlib.sha256(token.encode()).hexdigest())
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_logout_requires_real_session():
    with TestClient(app) as client:
        assert client.post("/api/auth/logout").status_code == 401
