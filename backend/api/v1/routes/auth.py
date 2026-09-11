"""Registration, login and account management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, require_role
from backend.core.roles import Role
from backend.core.security import create_access_token
from backend.db.session import get_db
from backend.models.user import User
from backend.schemas.user import Token, UserCreate, UserLogin, UserRead, UserRegister
from backend.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _reject_duplicate_email(db: Session, email: str) -> None:
    if auth_service.get_user_by_email(db, email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email is already registered",
        )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserRegister, db: Session = Depends(get_db)) -> User:
    """Register a new citizen account.

    Self-registration always creates a citizen. Officer and administrator
    accounts are created by an administrator through POST /auth/users.
    """
    _reject_duplicate_email(db, data.email)
    return auth_service.create_user(db, data, role=Role.CITIZEN)


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(Role.ADMINISTRATOR))],
)
def create_user(data: UserCreate, db: Session = Depends(get_db)) -> User:
    """Create an account with any role. Administrators only."""
    _reject_duplicate_email(db, data.email)
    return auth_service.create_user(db, data, role=data.role)


@router.post("/login", response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)) -> Token:
    """Exchange an email and password for a JWT."""
    user = auth_service.authenticate_user(db, data.email, data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        )
    return Token(access_token=create_access_token(subject=user.email, role=user.role))


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the logged-in user's identity and role."""
    return current_user
