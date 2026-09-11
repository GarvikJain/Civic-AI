"""Shared FastAPI dependencies, including role-based access control."""

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.roles import Role
from backend.core.security import decode_access_token
from backend.db.session import get_db
from backend.models.user import User
from backend.services.auth_service import get_user_by_email

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Read the JWT from the Authorization header and return its user.

    Rejects a missing, invalid or expired token, a token whose user no longer
    exists, and a user whose account has been deactivated.
    """
    if credentials is None:
        raise _unauthorized("Not authenticated")

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token has expired")
    except jwt.PyJWTError:
        raise _unauthorized("Invalid token")

    email = payload.get("sub")
    if not email:
        raise _unauthorized("Invalid token")

    user = get_user_by_email(db, email)
    if user is None:
        raise _unauthorized("User no longer exists")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        )
    return user


def require_role(*allowed_roles: Role) -> Callable[..., User]:
    """Build a dependency that only lets the given roles through.

    Used as:  current_user: User = Depends(require_role(Role.OFFICER))
    """
    allowed = {Role(role).value for role in allowed_roles}

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your role is not allowed to use this endpoint",
            )
        return current_user

    return dependency
