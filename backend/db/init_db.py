"""Create the database tables.

Run directly with:  python -m backend.db.init_db
"""

from backend.db.base import Base
from backend.db.session import engine

# Importing the models registers them on Base.metadata before create_all().
from backend.models import user  # noqa: F401


def init_db() -> None:
    """Create every table that does not exist yet."""
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database tables created.")
