"""Citizen profiles.

User is the login identity; Citizen is the profile that owns a citizen's
appointments, documents, queries, eligibility checks and feedback.

Ownership is resolved through the explicit link:

    JWT -> User.id -> Citizen.user_id -> Citizen.citizen_id

Email is never used to decide who owns what.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.citizen import Citizen
from backend.models.user import User


class CitizenProfileMissingError(Exception):
    """A citizen account has no profile row.

    A profile is created during registration, so this means the data is
    inconsistent. It is reported rather than quietly repaired, because
    creating a profile mid-request would hide the real problem.
    """


def build_citizen_profile(user: User) -> Citizen:
    """Create the profile row for a newly registered citizen.

    The caller commits, so the user and the profile are saved together.
    """
    return Citizen(
        user=user,
        name=user.full_name,
        email=user.email,
        # Authentication uses User.hashed_password; no credential is copied.
        password=None,
    )


def find_citizen_for_user(db: Session, user_id: int) -> Citizen | None:
    """Return the citizen profile linked to this user, or None."""
    return db.scalar(select(Citizen).where(Citizen.user_id == user_id))


def get_citizen_for_user(db: Session, user_id: int) -> Citizen:
    """Return the citizen profile linked to this user.

    Raises CitizenProfileMissingError if there is none.
    """
    citizen = find_citizen_for_user(db, user_id)
    if citizen is None:
        raise CitizenProfileMissingError(
            "No citizen profile is linked to this account."
        )
    return citizen
