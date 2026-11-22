from sqlalchemy import create_engine, inspect, text

from app.migrations import migrate_user_ownership


def test_legacy_ownership_migration_is_repeatable_and_preserves_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE users (id VARCHAR(40) PRIMARY KEY)"))
        db.execute(
            text(
                "CREATE TABLE profiles (id INTEGER PRIMARY KEY, visitor_id VARCHAR(40), weight_kg FLOAT)"
            )
        )
        db.execute(text("INSERT INTO profiles VALUES (1, 'legacy-demo', 65)"))
        db.execute(
            text(
                "CREATE TABLE scan_history (id VARCHAR(40) PRIMARY KEY, visitor_id VARCHAR(40) NOT NULL, image_key TEXT)"
            )
        )
        db.execute(
            text("INSERT INTO scan_history VALUES ('scan1', 'legacy-demo', 'old/image.webp')")
        )
        db.execute(
            text(
                "CREATE TABLE workout_visits (id INTEGER PRIMARY KEY, plan_id VARCHAR(40), day TEXT, status TEXT, UNIQUE(plan_id, day))"
            )
        )
        db.execute(
            text(
                "INSERT INTO workout_visits VALUES (1, 'legacy-hashed-plan', '2026-11-20', 'completed')"
            )
        )
    migrate_user_ownership(engine)
    migrate_user_ownership(engine)
    with engine.begin() as db:
        columns = {c["name"] for c in inspect(db).get_columns("profiles")}
        assert "user_id" in columns and "visitor_id" not in columns
        assert db.execute(text("SELECT user_id, weight_kg FROM profiles")).one() == (
            "legacy-demo",
            65,
        )
        assert db.execute(text("SELECT user_id, image_key FROM scan_history")).one() == (
            "legacy-demo",
            "old/image.webp",
        )
        assert db.execute(text("SELECT user_id, status FROM workout_visits")).one() == (
            None,
            "completed",
        )
        assert db.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
    engine.dispose()
