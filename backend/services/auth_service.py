"""Authentication business logic.

The routes only handle HTTP; the actual work lives here.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.roles import Role
from backend.core.security import hash_password, verify_password
from backend.models.user import User
from backend.schemas.user import UserRegister
from backend.services.citizen_service import build_citizen_profile


def get_user_by_email(db: Session, email: str) -> User | None:
    """Return the user with this email, or None."""
    return db.scalar(select(User).where(User.email == email))


def create_user(
    db: Session, data: UserRegister, role: Role = Role.CITIZEN
) -> User:
    """Store a new user with a bcrypt-hashed password.

    The role is passed in by the caller rather than taken from the request
    body, so a user can never choose their own role.

    A user with the citizen role also gets their citizen profile, created in
    the same transaction so an account can never exist without one.
    """
    user = User(
        full_name=data.full_name,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=Role(role).value,
        is_active=True,
    )
    db.add(user)

    if user.role == Role.CITIZEN.value:
        db.add(build_citizen_profile(user))
    elif user.role in (Role.OFFICER.value, Role.ADMINISTRATOR.value):
        from backend.services.officer_profile import build_officer_profile

        db.add(build_officer_profile(user))

    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return the user if the email and password match, otherwise None."""
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user
