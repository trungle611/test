"""Nâng cấp bảng cũ sang quyền sở hữu theo tài khoản, không xóa dữ liệu demo."""

from sqlalchemy import inspect, text

OWNED_TABLES = (
    "profiles",
    "profile_guidance",
    "food_logs",
    "meal_plans",
    "workout_selection",
    "scan_history",
    "daily_nutrition_goals",
    "workout_progress",
    "workout_visits",
    "batch_submissions",
    "ai_runs",
)


def migrate_user_ownership(engine):
    """Giữ ID cũ; chỉ tài khoản đã xác minh với cùng ID mới đọc được dữ liệu.

    Các ID demo không thuộc User vẫn giữ trong DB nhưng không có phiên đăng nhập
    hợp lệ để truy cập. Không nhận dữ liệu bằng X-Visitor-Id từ frontend.
    """
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "users" not in tables:
            return
        for table in OWNED_TABLES:
            if table not in tables:
                continue
            columns = {c["name"] for c in inspect(connection).get_columns(table)}
            if "user_id" not in columns:
                if "visitor_id" in columns:
                    connection.execute(
                        text(f'ALTER TABLE "{table}" RENAME COLUMN visitor_id TO user_id')
                    )
                else:
                    connection.execute(
                        text(
                            f'ALTER TABLE "{table}" ADD COLUMN user_id VARCHAR(40) REFERENCES users(id)'
                        )
                    )
            connection.execute(
                text(f'CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON "{table}" (user_id)')
            )
            if table in {"profiles", "profile_guidance", "workout_selection"}:
                connection.execute(
                    text(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{table}_user_id "
                        f'ON "{table}" (user_id) WHERE user_id IS NOT NULL'
                    )
                )
