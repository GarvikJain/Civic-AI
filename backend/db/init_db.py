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

_OFFICER_NEW_COLUMNS = {
    "user_id": "INTEGER",
}

_DOCUMENT_NEW_COLUMNS = {
    "reviewed_by_user_id": "INTEGER",
    "reviewed_at": "DATETIME",
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


def _ensure_unique_index(
    target_engine, table: str, column: str, index_name: str
) -> None:
    """Add a unique index when an older SQLite file gained a column via ALTER."""
    inspector = inspect(target_engine)
    if table not in inspector.get_table_names():
        return
    for index in inspector.get_indexes(table):
        if index.get("name") == index_name:
            return
        if index.get("unique") and index.get("column_names") == [column]:
            return
    with target_engine.begin() as connection:
        connection.execute(
            text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} ({column})")
        )


def init_db() -> None:
    """Create every table that does not exist yet, then add new columns."""
    Base.metadata.create_all(bind=engine)
    _add_missing_appointment_columns(engine)
    _add_missing_columns(engine, "eligibility_checks", _ELIGIBILITY_NEW_COLUMNS)
    _add_missing_columns(engine, "officers", _OFFICER_NEW_COLUMNS)
    _add_missing_columns(engine, "government_documents", _DOCUMENT_NEW_COLUMNS)
    _ensure_unique_index(engine, "officers", "user_id", "ix_officers_user_id")


if __name__ == "__main__":
    init_db()
    print("Database tables created.")
