"""Tài khoản kiểm thử được tạo qua API thật, không giả mạo dependency xác thực."""

import uuid
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import app


def register_account(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "test_" + uuid.uuid4().hex[:16],
            "password": "test-password-123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def account_headers():
    with TestClient(app) as client:
        data = register_account(client)
    return {"Authorization": f"Bearer {data['access_token']}"}


@contextmanager
def authenticated_client():
    with TestClient(app) as client:
        data = register_account(client)
        client.headers["Authorization"] = f"Bearer {data['access_token']}"
        yield client
