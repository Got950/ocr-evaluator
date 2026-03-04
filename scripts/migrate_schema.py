"""
One-time migration: add missing columns to submissions and ensure evaluation_logs exists.
Run: py scripts/migrate_schema.py
"""
from __future__ import annotations

from app.config import get_settings
from app.models.database import Base, engine

_SETTINGS = get_settings()


def migrate():
    from sqlalchemy import text
    cols = [
        ("evaluation_details", "JSONB"),
        ("per_question_scores", "JSONB"),
        ("total_score", "FLOAT"),
        ("percentage", "FLOAT"),
        ("manual_override", "JSONB"),
        ("final_score", "FLOAT"),
    ]
    with engine.connect() as conn:
        for name, typ in cols:
            conn.execute(text(f"ALTER TABLE submissions ADD COLUMN IF NOT EXISTS {name} {typ}"))
        conn.commit()
    # Create evaluation_logs if missing
    Base.metadata.create_all(bind=engine)
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
