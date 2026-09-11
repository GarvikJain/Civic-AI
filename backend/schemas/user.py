"""Pydantic schemas for users and authentication.

None of the response schemas contain the password or its hash.
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.core.roles import Role


class UserRegister(BaseModel):
    """Public self-registration. The role is always citizen.

    Officer and administrator accounts are created by an administrator through
    the admin endpoint, never by self-registration.
    """

    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserCreate(UserRegister):
    """Administrator-only user creation, where the role can be chosen."""

    role: Role = Role.CITIZEN


class UserLogin(BaseModel):
    """Data needed to log in."""

    email: EmailStr
    password: str


class UserRead(BaseModel):
    """User data returned by the API (never includes the password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    role: Role
    is_active: bool


class Token(BaseModel):
    """JWT returned after a successful login."""

    access_token: str
    token_type: str = "bearer"
