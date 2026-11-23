import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from pathlib import Path

from .settings import data_directory, production

PASSWORD_ITERATIONS = 240_000
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret() -> bytes:
    value = os.getenv("AUTH_SECRET", "").strip()
    if value:
        if len(value) < 32:
            raise RuntimeError("AUTH_SECRET cần ít nhất 32 ký tự")
        return value.encode()
    if production():
        raise RuntimeError("Thiếu AUTH_SECRET cho môi trường production")
    # Khóa local ngẫu nhiên và bền qua lần khởi động; không dùng khóa mặc định công khai.
    path = data_directory(Path(__file__).resolve().parents[1]) / "auth-secret"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(secrets.token_urlsafe(48))
        path.chmod(0o600)
    except FileExistsError:
        pass
    value = path.read_text(encoding="utf-8").strip()
    if len(value) < 32:
        raise RuntimeError("Khóa phiên local không hợp lệ; hãy cấu hình AUTH_SECRET")
    return value.encode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_encode(salt)}${_encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt, expected = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), _decode(salt), int(rounds))
        return hmac.compare_digest(_encode(digest), expected)
    except (ValueError, TypeError):
        return False


def create_token(user_id: str) -> str:
    payload = _encode(
        json.dumps(
            {"sub": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS, "sid": uuid.uuid4().hex},
            separators=(",", ":"),
        ).encode()
    )
    signature = _encode(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def verify_token(token: str) -> str:
    try:
        payload, signature = token.split(".", 1)
        expected = _encode(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        data = json.loads(_decode(payload))
        if int(data["exp"]) <= int(time.time()):
            raise ValueError("expired token")
        return str(data["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid token") from exc
