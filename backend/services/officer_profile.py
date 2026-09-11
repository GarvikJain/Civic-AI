"""Officer profiles linked to login users.

User is the authentication identity. Officer is the operational identity used
on Appointment.officer_id.

    JWT -> User.id -> Officer.user_id -> Officer.officer_id -> Appointment.officer_id

Email is never used to decide which officer handled a visit.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.roles import Role
from backend.models.officer import Officer
from backend.models.user import User

STAFF_ROLES = (Role.OFFICER.value, Role.ADMINISTRATOR.value)


class OfficerProfileMissingError(Exception):
    """A staff account has no officer profile and one could not be created."""


def build_officer_profile(user: User) -> Officer:
    """Create the operational profile for a newly created staff account."""
    title = "Administrator" if user.role == Role.ADMINISTRATOR.value else "Officer"
    return Officer(
        user=user,
        name=user.full_name,
        department="Unassigned",
        role=title,
        email=user.email,
    )


def find_officer_for_user(db: Session, user_id: int) -> Officer | None:
    return db.scalar(select(Officer).where(Officer.user_id == user_id))


def get_or_create_officer_for_user(db: Session, user: User) -> Officer:
    """Return the Officer row for this login user, creating one if needed.

    Lookup is always User.id → Officer.user_id.
    """
    if user.role not in STAFF_ROLES:
        raise OfficerProfileMissingError(
            "Only officer and administrator accounts have an officer profile."
        )
    existing = find_officer_for_user(db, user.id)
    if existing is not None:
        return existing
    officer = build_officer_profile(user)
    db.add(officer)
    db.flush()
    return officer
