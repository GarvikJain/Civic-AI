"""Create the database tables.

Run directly with:  python -m backend.db.init_db

create_all() does not add columns to tables that already exist. After Phase 6C
the appointments table gained a few timestamps; those are added below when
missing so an existing SQLite file keeps working.
"""

from sqlalchemy import inspect, text

from backend.db.base import Base
from backend.db.session import engine

# Importing the models package registers every table on Base.metadata before
# create_all() runs.
import backend.models  # noqa: F401

_APPOINTMENT_NEW_COLUMNS = {
    "queue_joined_at": "DATETIME",
    "service_started_at": "DATETIME",
    "service_completed_at": "DATETIME",
}

_ELIGIBILITY_NEW_COLUMNS = {
    "explanation": "TEXT",
    "created_at": "DATETIME",
}


def _add_missing_columns(target_engine, table: str, columns: dict[str, str]) -> None:
    inspector = inspect(target_engine)
    if table not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns(table)}
    with target_engine.begin() as connection:
        for name, sql_type in columns.items():
            if name not in existing:
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                )


def _add_missing_appointment_columns(target_engine) -> None:
    _add_missing_columns(target_engine, "appointments", _APPOINTMENT_NEW_COLUMNS)


def init_db() -> None:
    """Create every table that does not exist yet, then add new columns."""
    Base.metadata.create_all(bind=engine)
    _add_missing_appointment_columns(engine)
    _add_missing_columns(engine, "eligibility_checks", _ELIGIBILITY_NEW_COLUMNS)


if __name__ == "__main__":
    init_db()
    print("Database tables created.")
