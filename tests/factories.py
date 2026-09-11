"""Helpers for building test users and signing them in."""

from backend.core.roles import Role
from backend.core.security import hash_password
from backend.models.user import User

PASSWORD = "civicai-password"


def register_citizen(client, email="citizen@example.com"):
    """Register a citizen through the public endpoint."""
    return client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Citizen", "email": email, "password": PASSWORD},
    )


def add_user(session_factory, email, role, is_active=True) -> None:
    """Insert a user directly, for roles that cannot self-register."""
    db = session_factory()
    try:
        db.add(
            User(
                full_name=f"Test {role.value}",
                email=email,
                hashed_password=hash_password(PASSWORD),
                role=role.value,
                is_active=is_active,
            )
        )
        db.commit()
    finally:
        db.close()


def auth_header(client, email) -> dict:
    """Sign in and return the Authorization header."""
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def citizen_header(client, email="citizen@example.com") -> dict:
    """Register a citizen and return their Authorization header."""
    register_citizen(client, email)
    return auth_header(client, email)


def role_header(client, session_factory, role: Role) -> dict:
    """Create a user with this role and return their Authorization header."""
    email = f"{role.value}@example.com"
    add_user(session_factory, email, role)
    return auth_header(client, email)
