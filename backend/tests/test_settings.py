"""Cấu hình không làm đổi database theo thư mục mở terminal."""

from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app import auth, settings


@pytest.fixture
def configuration(monkeypatch, tmp_path):
    root = tmp_path / "project"
    backend = root / "backend"
    backend.mkdir(parents=True)
    monkeypatch.setattr(settings, "BACKEND_DIR", backend)
    monkeypatch.setattr(settings, "REPO_DIR", root)
    for name in ("DATABASE_URL", "POSTGRES_URL", "APP_DATA_DIR", "SCAN_UPLOAD_DIR", "VERCEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    return root, backend


def test_database_same_from_root_and_backend(configuration, monkeypatch):
    root, backend = configuration
    monkeypatch.chdir(root)
    first = settings.database_url()
    monkeypatch.chdir(backend)
    assert settings.database_url() == first
    assert Path(make_url(first).database) == backend / ".runtime" / "hbtnfit.db"


def test_keep_existing_root_database_and_reject_ambiguous_choice(configuration):
    root, backend = configuration
    (root / "hbtnfit.db").touch()
    assert Path(make_url(settings.database_url()).database) == root / "hbtnfit.db"
    (backend / "hbtnfit.db").touch()
    with pytest.raises(RuntimeError, match="nhiều database"):
        settings.database_url()


def test_explicit_relative_database_uses_existing_legacy_location(configuration, monkeypatch):
    root, _ = configuration
    (root / "hbtnfit.db").touch()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./hbtnfit.db")
    assert Path(make_url(settings.database_url()).database) == root / "hbtnfit.db"


def test_data_directory_and_upload_override(configuration, monkeypatch):
    _, backend = configuration
    monkeypatch.setenv("APP_DATA_DIR", "saved")
    assert Path(make_url(settings.database_url()).database) == backend / "saved" / "hbtnfit.db"
    assert settings.scan_directory() == backend / "saved" / "scans"
    monkeypatch.setenv("SCAN_UPLOAD_DIR", "pictures")
    assert settings.scan_directory() == backend / "pictures"


def test_whitespace_database_configuration_is_empty(configuration, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "  ")
    assert settings.database_url().endswith("hbtnfit.db")


def test_production_requires_explicit_secret(configuration, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="Thiếu AUTH_SECRET"):
        auth._secret()
    monkeypatch.setenv("AUTH_SECRET", "short")
    with pytest.raises(RuntimeError, match="32"):
        auth._secret()
