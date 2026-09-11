"""Linking an authenticated user to their citizen profile.

Phase 3 made User the single login identity, while the ERD keeps Citizen as the
citizen's profile record. Until those are unified, a citizen's profile row is
looked up (or created) from the authenticated user's email.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.citizen import Citizen
from backend.models.user import User

# Citizen.password exists in the ERD but is never used for logging in, because
# authentication lives on User. This marker is not a valid bcrypt hash, so it
# can never be used to authenticate, and no real hash is duplicated here.
UNUSABLE_PASSWORD = "!"


def get_or_create_citizen(db: Session, user: User) -> Citizen:
    """Return the citizen profile for this user, creating it if needed."""
    citizen = db.scalar(select(Citizen).where(Citizen.email == user.email))
    if citizen is not None:
        return citizen

    citizen = Citizen(
        name=user.full_name,
        email=user.email,
        password=UNUSABLE_PASSWORD,
    )
    db.add(citizen)
    db.commit()
    db.refresh(citizen)
    return citizen
