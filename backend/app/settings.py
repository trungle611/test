"""Đường dẫn dữ liệu và cấu hình công khai, không phụ thuộc thư mục chạy lệnh."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")


def data_directory(backend_dir=None):
    base = backend_dir or BACKEND_DIR
    value = os.getenv("APP_DATA_DIR", "").strip()
    path = Path(value).expanduser() if value else base / ".runtime"
    return (path if path.is_absolute() else base / path).resolve()


def production():
    return os.getenv("APP_ENV", "local") == "production" or os.getenv("VERCEL") == "1"


def database_url():
    raw = os.getenv("DATABASE_URL", "").strip() or os.getenv("POSTGRES_URL", "").strip()
    if raw:
        raw = raw.strip()
        if raw.startswith("postgres://"):
            raw = "postgresql+psycopg://" + raw[len("postgres://") :]
        elif raw.startswith("postgresql://"):
            raw = "postgresql+psycopg://" + raw[len("postgresql://") :]
        url = make_url(raw)
        if url.get_backend_name() != "sqlite" or url.database in {None, "", ":memory:"}:
            return raw
        path = Path(url.database).expanduser()
        if not path.is_absolute():
            candidates = {p.resolve() for p in (BACKEND_DIR / path, REPO_DIR / path) if p.exists()}
            if len(candidates) > 1:
                raise RuntimeError(
                    "Có nhiều database cùng tên; hãy đặt DATABASE_URL bằng đường dẫn tuyệt đối"
                )
            path = next(iter(candidates)) if candidates else BACKEND_DIR / path
        return url.set(database=str(path.resolve())).render_as_string(hide_password=False)
    if not os.getenv("APP_DATA_DIR", "").strip():
        candidates = [
            p for p in (BACKEND_DIR / "hbtnfit.db", REPO_DIR / "hbtnfit.db") if p.exists()
        ]
        if len(candidates) > 1:
            raise RuntimeError("Có nhiều database cũ; hãy chọn rõ DATABASE_URL trước khi chạy")
        if candidates:
            return "sqlite:///" + str(candidates[0].resolve())
    return "sqlite:///" + str(data_directory() / "hbtnfit.db")


def scan_directory():
    value = os.getenv("SCAN_UPLOAD_DIR", "").strip()
    if value:
        path = Path(value).expanduser()
        return (path if path.is_absolute() else BACKEND_DIR / path).resolve()
    legacy = BACKEND_DIR / "uploads" / "scans"
    if not os.getenv("APP_DATA_DIR", "").strip() and legacy.exists():
        return legacy
    return data_directory() / "scans"
