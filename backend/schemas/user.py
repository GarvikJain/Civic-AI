"""Pydantic schemas for users and authentication."""

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    """Data needed to register a new user."""

    full_name: str
    email: EmailStr
    password: str
    role: str = "citizen"


class UserLogin(BaseModel):
    """Data needed to log in."""

    email: EmailStr
    password: str


class UserRead(BaseModel):
    """User data returned by the API (never includes the password)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    role: str


class Token(BaseModel):
    """JWT returned after a successful login."""

    access_token: str
    token_type: str = "bearer"
