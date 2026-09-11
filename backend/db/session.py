"""Database engine and session handling.

Only this module knows which database is being used, so moving from SQLite to
PostgreSQL means changing DATABASE_URL in the .env file and nothing else.
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import BASE_DIR, settings


def _engine_kwargs() -> dict:
    """SQLite needs one extra flag; other databases do not."""
    if settings.database_url.startswith("sqlite"):
        # FastAPI may use a different thread than the one that created the
        # connection, so this check has to be disabled for SQLite.
        return {"connect_args": {"check_same_thread": False}}
    return {}


def _ensure_sqlite_directory() -> None:
    """Create the data/ folder so SQLite can create its file."""
    if settings.database_url.startswith("sqlite"):
        (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)


_ensure_sqlite_directory()

engine = create_engine(settings.database_url, echo=False, **_engine_kwargs())

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """FastAPI dependency that gives a route one database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
