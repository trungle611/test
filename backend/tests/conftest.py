"""Mỗi lần chạy suite dùng DB/ảnh tạm, không đụng dữ liệu hoặc khóa thật."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
scratch = tempfile.TemporaryDirectory(prefix="hbtnfit-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(scratch.name) / 'tests.db'}"
os.environ["SCAN_UPLOAD_DIR"] = str(Path(scratch.name) / "scans")
os.environ["AUTH_SECRET"] = "test-only-secret-not-for-real-deployment-2026"
os.environ["GEMINI_API_KEY"] = "test-only-dummy-key"
os.environ["GEMINI_FALLBACK_API_KEY"] = ""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_database():
    yield
    from app.db import engine

    engine.dispose()
    scratch.cleanup()
