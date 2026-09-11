"""Tests for authentication and role-based access control (Phase 3).

Every test runs against its own in-memory SQLite database, so the real
data/civicai.db file is never touched.
"""

from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.roles import Role
from backend.core.security import create_access_token, hash_password
from backend.db.base import Base
from backend.db.session import enable_sqlite_foreign_keys, get_db
from backend.main import app
from backend.models.regulation import Regulation
from backend.models.user import User

PASSWORD = "civicai-password"


@pytest.fixture
def session_factory():
    """A fresh in-memory database for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(bind=engine)
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


@pytest.fixture
def client(session_factory):
    """A TestClient whose requests use the in-memory database."""

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- helpers ----------------------------------------------------------------


def register_citizen(client, email="citizen@example.com") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Citizen", "email": email, "password": PASSWORD},
    )
    return response


def add_user(session_factory, email, role, is_active=True) -> None:
    """Insert a user directly, for roles that cannot self-register."""
    db = session_factory()
    try:
        user = User(
            full_name=f"Test {role.value}",
            email=email,
            hashed_password=hash_password(PASSWORD),
            role=role.value,
            is_active=is_active,
        )
        db.add(user)
        if role is Role.CITIZEN:
            from backend.services.citizen_service import build_citizen_profile

            db.add(build_citizen_profile(user))
        elif role in (Role.OFFICER, Role.ADMINISTRATOR):
            from backend.services.officer_profile import build_officer_profile

            db.add(build_officer_profile(user))
        db.commit()
    finally:
        db.close()


def login(client, email, password=PASSWORD):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


def auth_header(client, email) -> dict:
    token = login(client, email).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def header_for_role(client, session_factory, role) -> dict:
    email = f"{role.value}@example.com"
    add_user(session_factory, email, role)
    return auth_header(client, email)


# --- registration -----------------------------------------------------------


def test_citizen_registration_succeeds(client):
    response = register_citizen(client)
    assert response.status_code == 201

    body = response.json()
    assert body["email"] == "citizen@example.com"
    assert body["role"] == Role.CITIZEN.value
    assert body["is_active"] is True


def test_registration_response_hides_the_password(client):
    body = register_citizen(client).json()
    assert "password" not in body
    assert "hashed_password" not in body


def test_duplicate_registration_is_rejected(client):
    assert register_citizen(client).status_code == 201
    duplicate = register_citizen(client)
    assert duplicate.status_code == 400
    assert "already registered" in duplicate.json()["detail"]


def test_self_registration_cannot_choose_a_role(client):
    """A caller must not be able to make themselves an administrator."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Sneaky User",
            "email": "sneaky@example.com",
            "password": PASSWORD,
            "role": "administrator",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == Role.CITIZEN.value


def test_password_is_stored_as_a_bcrypt_hash(client, session_factory):
    register_citizen(client)

    db = session_factory()
    try:
        user = db.scalar(select(User).where(User.email == "citizen@example.com"))
        stored = user.hashed_password
    finally:
        db.close()

    assert stored != PASSWORD
    assert stored.startswith("$2b$")


# --- login ------------------------------------------------------------------


def test_login_succeeds_and_returns_a_jwt(client):
    register_citizen(client)
    response = login(client, "citizen@example.com")
    assert response.status_code == 200

    body = response.json()
    assert body["token_type"] == "bearer"

    payload = jwt.decode(
        body["access_token"], options={"verify_signature": False}
    )
    assert payload["sub"] == "citizen@example.com"
    assert payload["role"] == Role.CITIZEN.value
    assert "exp" in payload


def test_login_fails_with_the_wrong_password(client):
    register_citizen(client)
    response = login(client, "citizen@example.com", "wrong-password")
    assert response.status_code == 401


def test_login_fails_for_an_unknown_email(client):
    response = login(client, "nobody@example.com")
    assert response.status_code == 401


def test_login_is_refused_for_an_inactive_user(client, session_factory):
    add_user(session_factory, "disabled@example.com", Role.CITIZEN, is_active=False)
    response = login(client, "disabled@example.com")
    assert response.status_code == 403
    assert "inactive" in response.json()["detail"].lower()


# --- /auth/me and token validation ------------------------------------------


def test_me_returns_the_identity_and_role(client):
    register_citizen(client)
    response = client.get("/api/v1/auth/me", headers=auth_header(client, "citizen@example.com"))
    assert response.status_code == 200

    body = response.json()
    assert body["email"] == "citizen@example.com"
    assert body["role"] == Role.CITIZEN.value
    assert "hashed_password" not in body


def test_me_needs_a_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_invalid_token_is_rejected(client):
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


def test_expired_token_is_rejected(client):
    register_citizen(client)
    expired = create_access_token(
        subject="citizen@example.com",
        role=Role.CITIZEN.value,
        expires_delta=timedelta(minutes=-1),
    )
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired"


def test_token_for_a_deleted_user_is_rejected(client):
    """A signed token is useless once its user is gone."""
    token = create_access_token(subject="ghost@example.com", role=Role.CITIZEN.value)
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


# --- role-based access control ----------------------------------------------


def test_citizen_cannot_open_the_officer_dashboard(client):
    register_citizen(client)
    response = client.get(
        "/api/v1/officers/dashboard", headers=auth_header(client, "citizen@example.com")
    )
    assert response.status_code == 403


def test_officer_can_open_the_officer_dashboard(client, session_factory):
    headers = header_for_role(client, session_factory, Role.OFFICER)
    response = client.get("/api/v1/officers/dashboard", headers=headers)
    assert response.status_code == 200
    assert response.json()["module"] == "Officer Productivity Dashboard"


def test_administrator_can_open_the_officer_dashboard(client, session_factory):
    headers = header_for_role(client, session_factory, Role.ADMINISTRATOR)
    assert client.get("/api/v1/officers/dashboard", headers=headers).status_code == 200


def test_officer_dashboard_needs_a_token(client):
    assert client.get("/api/v1/officers/dashboard").status_code == 401


def test_citizen_can_open_the_citizen_dashboard(client):
    register_citizen(client)
    response = client.get(
        "/api/v1/citizens/dashboard", headers=auth_header(client, "citizen@example.com")
    )
    assert response.status_code == 200


def test_officer_cannot_open_the_citizen_dashboard(client, session_factory):
    headers = header_for_role(client, session_factory, Role.OFFICER)
    assert client.get("/api/v1/citizens/dashboard", headers=headers).status_code == 403


REGULATION = {
    "scheme_name": "Income Certificate Scheme",
    "department": "Revenue",
    "eligibility_criteria": "Annual income below 2,50,000",
    "required_documents": "Aadhaar, Income Proof",
    "circular_reference": "CIRC/2026/11",
}


def test_citizen_cannot_create_a_regulation(client):
    register_citizen(client)
    response = client.post(
        "/api/v1/regulations",
        json=REGULATION,
        headers=auth_header(client, "citizen@example.com"),
    )
    assert response.status_code == 403


def test_officer_cannot_create_a_regulation(client, session_factory):
    headers = header_for_role(client, session_factory, Role.OFFICER)
    response = client.post("/api/v1/regulations", json=REGULATION, headers=headers)
    assert response.status_code == 403


def test_administrator_can_create_a_regulation(client, session_factory):
    headers = header_for_role(client, session_factory, Role.ADMINISTRATOR)
    response = client.post("/api/v1/regulations", json=REGULATION, headers=headers)
    assert response.status_code == 201
    assert response.json()["scheme_name"] == REGULATION["scheme_name"]

    db = session_factory()
    try:
        stored = db.scalars(select(Regulation)).all()
    finally:
        db.close()
    assert len(stored) == 1


def test_regulation_creation_needs_a_token(client):
    assert client.post("/api/v1/regulations", json=REGULATION).status_code == 401


# --- administrator account management ---------------------------------------


def test_administrator_can_create_an_officer_account(client, session_factory):
    headers = header_for_role(client, session_factory, Role.ADMINISTRATOR)
    response = client.post(
        "/api/v1/auth/users",
        json={
            "full_name": "New Officer",
            "email": "new-officer@example.com",
            "password": PASSWORD,
            "role": "officer",
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["role"] == Role.OFFICER.value

    # The new officer can log in and reach officer functionality.
    officer_headers = auth_header(client, "new-officer@example.com")
    assert (
        client.get("/api/v1/officers/dashboard", headers=officer_headers).status_code
        == 200
    )


def test_officer_cannot_create_accounts(client, session_factory):
    headers = header_for_role(client, session_factory, Role.OFFICER)
    response = client.post(
        "/api/v1/auth/users",
        json={
            "full_name": "Shadow Admin",
            "email": "shadow-admin@example.com",
            "password": PASSWORD,
            "role": "administrator",
        },
        headers=headers,
    )
    assert response.status_code == 403


def test_inactive_user_token_cannot_call_protected_endpoints(client, session_factory):
    add_user(session_factory, "later-disabled@example.com", Role.OFFICER)
    headers = auth_header(client, "later-disabled@example.com")
    assert client.get("/api/v1/officers/dashboard", headers=headers).status_code == 200

    db = session_factory()
    try:
        user = db.scalar(select(User).where(User.email == "later-disabled@example.com"))
        user.is_active = False
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/officers/dashboard", headers=headers)
    assert response.status_code == 403
    assert "inactive" in response.json()["detail"].lower()


def test_citizen_cannot_create_accounts(client):
    register_citizen(client)
    response = client.post(
        "/api/v1/auth/users",
        json={
            "full_name": "Wannabe Officer",
            "email": "wannabe@example.com",
            "password": PASSWORD,
            "role": "officer",
        },
        headers=auth_header(client, "citizen@example.com"),
    )
    assert response.status_code == 403
