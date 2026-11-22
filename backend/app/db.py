import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException, Request
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "sqlite:///./hbtnfit.db"
if os.getenv("VERCEL") and DATABASE_URL.startswith("sqlite"):
    raise RuntimeError("Vercel cần DATABASE_URL hoặc POSTGRES_URL dùng PostgreSQL")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://") :]
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://") :]
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    **(
        {"poolclass": NullPool, "pool_pre_ping": True}
        if DATABASE_URL.startswith("postgresql")
        else {}
    ),
)
SessionLocal = sessionmaker(bind=engine)


if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")


def migrate_demo_columns():
    """Add columns to existing local SQLite demo databases without losing entries."""
    if DATABASE_URL.startswith("postgresql"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE foods ADD COLUMN IF NOT EXISTS basis_amount DOUBLE PRECISION DEFAULT 100"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE foods ADD COLUMN IF NOT EXISTS basis_unit VARCHAR(20) DEFAULT 'g'"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE foods ADD COLUMN IF NOT EXISTS basis_label VARCHAR(80) DEFAULT '100 g'"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE foods ADD COLUMN IF NOT EXISTS catalog_kind VARCHAR(20) DEFAULT 'food'"
                )
            )
            connection.execute(
                text("ALTER TABLE profile_guidance ADD COLUMN IF NOT EXISTS food_checklist JSONB")
            )
        return
    if not DATABASE_URL.startswith("sqlite"):
        return
    columns = {
        "foods": {
            "display_name": "VARCHAR(160)",
            "owner_id": "VARCHAR(40)",
            "basis_amount": "FLOAT DEFAULT 100",
            "basis_unit": "VARCHAR(20) DEFAULT 'g'",
            "basis_label": "VARCHAR(80) DEFAULT '100 g'",
            "catalog_kind": "VARCHAR(20) DEFAULT 'food'",
        },
        "profiles": {
            "sex": "VARCHAR(10)",
            "activity_level": "VARCHAR(20)",
            "protein_mode": "VARCHAR(20)",
        },
        "profile_guidance": {
            "target_date": "VARCHAR(10)",
            "food_checklist": "JSON",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, fields in columns.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, type_name in fields.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {type_name}"))


def get_db(request: Request):
    """Quyền sở hữu chỉ lấy từ token đã xác minh và tài khoản còn tồn tại."""
    from .auth import verify_token
    from .models import User

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(401, "Bạn cần đăng nhập để sử dụng tính năng này")
    try:
        user_id = str(uuid.UUID(verify_token(token.strip())))
    except ValueError as exc:
        raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn") from exc
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(401, "Tài khoản không tồn tại")
        session.info["user_id"] = user_id
        yield session


def public_db():
    """Chỉ dùng cho đăng ký và đăng nhập; không được dùng ở API dữ liệu cá nhân."""
    with SessionLocal() as session:
        yield session


def initialize_database():
    """Tạo DB mới hoặc nâng cấp schema hiện có, không xóa bảng hay nhận dữ liệu demo."""
    from .auth import _secret
    from .catalog import load_catalog
    from .migrations import migrate_user_ownership

    _secret()
    Base.metadata.create_all(engine)
    migrate_demo_columns()
    migrate_user_ownership(engine)
    load_catalog()
