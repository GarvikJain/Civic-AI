"""Tests for the explicit User -> Citizen relationship.

User is the login identity; Citizen is the profile. Ownership is resolved
through Citizen.user_id, never by matching email addresses.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.core.roles import Role
from backend.models.citizen import Citizen
from backend.models.user import User
from backend.services import citizen_service
from backend.services.citizen_service import CitizenProfileMissingError
from tests.factories import PASSWORD, add_user, register_citizen


def get_user(session_factory, email) -> User:
    db = session_factory()
    try:
        return db.scalar(select(User).where(User.email == email))
    finally:
        db.close()


def all_citizens(session_factory) -> list[Citizen]:
    db = session_factory()
    try:
        return list(db.scalars(select(Citizen)).all())
    finally:
        db.close()


# --- 1 to 3. registration builds both rows ---------------------------------


def test_registration_creates_a_user(client, session_factory):
    assert register_citizen(client, "linked@example.com").status_code == 201

    user = get_user(session_factory, "linked@example.com")
    assert user is not None
    assert user.role == Role.CITIZEN.value


def test_registration_creates_exactly_one_citizen_profile(client, session_factory):
    register_citizen(client, "linked@example.com")
    assert len(all_citizens(session_factory)) == 1


def test_the_profile_points_at_the_new_user(client, session_factory):
    register_citizen(client, "linked@example.com")

    user = get_user(session_factory, "linked@example.com")
    citizen = all_citizens(session_factory)[0]

    assert citizen.user_id == user.id
    assert citizen.name == user.full_name
    assert citizen.email == user.email


def test_the_profile_never_copies_the_password(client, session_factory):
    """Authentication credentials must live on User only."""
    register_citizen(client, "linked@example.com")

    user = get_user(session_factory, "linked@example.com")
    citizen = all_citizens(session_factory)[0]

    assert citizen.password is None
    assert citizen.password != user.hashed_password
    assert citizen.password != PASSWORD


def test_the_relationship_works_in_both_directions(client, session_factory):
    register_citizen(client, "linked@example.com")

    db = session_factory()
    try:
        user = db.scalar(select(User).where(User.email == "linked@example.com"))
        assert user.citizen is not None
        assert user.citizen.user_id == user.id
        assert user.citizen.user.id == user.id
    finally:
        db.close()


# --- 4. no duplicates -------------------------------------------------------


def test_registering_twice_is_rejected_and_adds_no_second_profile(
    client, session_factory
):
    assert register_citizen(client, "linked@example.com").status_code == 201
    assert register_citizen(client, "linked@example.com").status_code == 400

    assert len(all_citizens(session_factory)) == 1


def test_a_user_cannot_have_two_citizen_profiles(client, session_factory):
    """The unique constraint on user_id enforces the one-to-one link."""
    register_citizen(client, "linked@example.com")
    user = get_user(session_factory, "linked@example.com")

    db = session_factory()
    try:
        db.add(
            Citizen(user_id=user.id, name="Duplicate", email="duplicate@example.com")
        )
        with pytest.raises(IntegrityError):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_a_profile_cannot_point_at_a_missing_user(session_factory):
    db = session_factory()
    try:
        db.add(Citizen(user_id=9999, name="Ghost", email="ghost@example.com"))
        with pytest.raises(IntegrityError):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_officers_and_administrators_get_no_citizen_profile(client, session_factory):
    add_user(session_factory, "officer@example.com", Role.OFFICER)
    add_user(session_factory, "admin@example.com", Role.ADMINISTRATOR)

    assert all_citizens(session_factory) == []


# --- 5 and 8. lookup is by user id, not email ------------------------------


def test_lookup_uses_the_user_id(client, session_factory):
    register_citizen(client, "linked@example.com")
    user = get_user(session_factory, "linked@example.com")

    db = session_factory()
    try:
        citizen = citizen_service.get_citizen_for_user(db, user.id)
        assert citizen.user_id == user.id
    finally:
        db.close()


def test_changing_the_user_email_does_not_break_ownership(client, session_factory):
    """Ownership follows the foreign key, so a new email changes nothing."""
    register_citizen(client, "linked@example.com")
    user_id = get_user(session_factory, "linked@example.com").id

    db = session_factory()
    try:
        user = db.get(User, user_id)
        user.email = "new-address@example.com"
        db.commit()
    finally:
        db.close()

    db = session_factory()
    try:
        citizen = citizen_service.get_citizen_for_user(db, user_id)
        assert citizen.user_id == user_id
        # The profile still carries the old contact email, and the link holds.
        assert citizen.email == "linked@example.com"
    finally:
        db.close()


def test_two_citizens_get_separate_profiles(client, session_factory):
    register_citizen(client, "first@example.com")
    register_citizen(client, "second@example.com")

    first = get_user(session_factory, "first@example.com")
    second = get_user(session_factory, "second@example.com")

    db = session_factory()
    try:
        first_profile = citizen_service.get_citizen_for_user(db, first.id)
        second_profile = citizen_service.get_citizen_for_user(db, second.id)
    finally:
        db.close()

    assert first_profile.citizen_id != second_profile.citizen_id
    assert first_profile.user_id == first.id
    assert second_profile.user_id == second.id


# --- 10. a missing profile is reported -------------------------------------


def test_a_missing_profile_raises_a_clear_error(session_factory):
    add_user(session_factory, "orphan@example.com", Role.CITIZEN, with_profile=False)
    user = get_user(session_factory, "orphan@example.com")

    db = session_factory()
    try:
        with pytest.raises(CitizenProfileMissingError, match="citizen profile"):
            citizen_service.get_citizen_for_user(db, user.id)
        # The failed lookup must not have created anything.
        assert citizen_service.find_citizen_for_user(db, user.id) is None
    finally:
        db.close()


def test_the_email_bridge_is_gone():
    """The old email-based identity helper must no longer exist."""
    assert not hasattr(citizen_service, "get_or_create_citizen")
