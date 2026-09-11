"""Authentication business logic.

The routes only handle HTTP; the actual work lives here.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.security import hash_password, verify_password
from backend.models.user import User
from backend.schemas.user import UserCreate


def get_user_by_email(db: Session, email: str) -> User | None:
    """Return the user with this email, or None."""
    return db.scalar(select(User).where(User.email == email))


def create_user(db: Session, data: UserCreate) -> User:
    """Store a new user with a hashed password."""
    user = User(
        full_name=data.full_name,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return the user if the email and password match, otherwise None."""
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user
