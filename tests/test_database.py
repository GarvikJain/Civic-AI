"""Tests for the CivicAI database layer (Phase 2).

These tests use their own in-memory SQLite database, so the real
data/civicai.db file is never touched.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.session import enable_sqlite_foreign_keys
from backend.models import (
    Appointment,
    Citizen,
    CitizenQuery,
    EligibilityCheck,
    Feedback,
    GovernmentDocument,
    Officer,
    Regulation,
)

# The eight entities from the CivicAI ER diagram.
ERD_TABLES = [
    "citizens",
    "officers",
    "regulations",
    "appointments",
    "government_documents",
    "citizen_queries",
    "eligibility_checks",
    "feedback",
]

# table -> {column: referenced table}
EXPECTED_FOREIGN_KEYS = {
    "appointments": {"citizen_id": "citizens", "officer_id": "officers"},
    "government_documents": {"citizen_id": "citizens", "regulation_id": "regulations"},
    "citizen_queries": {"citizen_id": "citizens", "regulation_id": "regulations"},
    "eligibility_checks": {
        "citizen_id": "citizens",
        "appointment_id": "appointments",
        "regulation_id": "regulations",
    },
    "feedback": {"citizen_id": "citizens", "appointment_id": "appointments"},
}


@pytest.fixture(scope="module")
def engine():
    """One in-memory database shared by every test in this file."""
    # StaticPool keeps a single connection, otherwise each connection would
    # get its own empty in-memory database.
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    enable_sqlite_foreign_keys(test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session(engine):
    """A fresh session that rolls back after each test."""
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = factory()
    yield db
    db.rollback()
    db.close()


def make_citizen(session, email="citizen@example.com") -> Citizen:
    citizen = Citizen(
        name="Test Citizen",
        email=email,
        phone="9876543210",
        password="hashed-password",
        address="12 Main Road, Pune",
    )
    session.add(citizen)
    session.flush()
    return citizen


def make_officer(session, email="officer@example.com") -> Officer:
    officer = Officer(
        name="Test Officer",
        department="Revenue",
        role="Clerk",
        email=email,
    )
    session.add(officer)
    session.flush()
    return officer


def make_regulation(session) -> Regulation:
    regulation = Regulation(
        scheme_name="Income Certificate Scheme",
        department="Revenue",
        eligibility_criteria="Annual income below 2,50,000",
        required_documents="Aadhaar, Income Proof",
        circular_reference="CIRC/2026/11",
    )
    session.add(regulation)
    session.flush()
    return regulation


def make_appointment(session, citizen, officer=None) -> Appointment:
    appointment = Appointment(
        citizen_id=citizen.citizen_id,
        officer_id=officer.officer_id if officer else None,
        service_type="Income Certificate",
        appointment_date=datetime.now(timezone.utc) + timedelta(days=1),
        queue_number=1,
        status="scheduled",
    )
    session.add(appointment)
    session.flush()
    return appointment


# --- Schema tests -----------------------------------------------------------


def test_all_eight_tables_are_created(engine):
    tables = inspect(engine).get_table_names()
    for table in ERD_TABLES:
        assert table in tables, f"missing table: {table}"


def test_every_table_has_a_primary_key(engine):
    inspector = inspect(engine)
    for table in ERD_TABLES:
        primary_key = inspector.get_pk_constraint(table)["constrained_columns"]
        assert primary_key, f"{table} has no primary key"


def test_foreign_keys_match_the_erd(engine):
    inspector = inspect(engine)
    for table, expected in EXPECTED_FOREIGN_KEYS.items():
        actual = {
            fk["constrained_columns"][0]: fk["referred_table"]
            for fk in inspector.get_foreign_keys(table)
        }
        assert actual == expected, f"wrong foreign keys on {table}: {actual}"


def test_foreign_keys_are_enforced(session):
    """An appointment cannot point at a citizen that does not exist."""
    session.add(
        Appointment(
            citizen_id=9999,
            service_type="Income Certificate",
            appointment_date=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


# --- Relationship tests -----------------------------------------------------


def test_citizen_can_have_many_appointments(session):
    citizen = make_citizen(session, "many-appointments@example.com")
    make_appointment(session, citizen)
    make_appointment(session, citizen)
    session.refresh(citizen)

    assert len(citizen.appointments) == 2
    assert all(a.citizen_id == citizen.citizen_id for a in citizen.appointments)


def test_appointment_can_reference_an_officer(session):
    citizen = make_citizen(session, "with-officer@example.com")
    officer = make_officer(session, "assigned@example.com")
    appointment = make_appointment(session, citizen, officer)
    session.refresh(officer)

    assert appointment.officer.officer_id == officer.officer_id
    assert appointment.officer.department == "Revenue"
    assert appointment in officer.appointments


def test_regulation_is_referenced_by_documents_queries_and_checks(session):
    citizen = make_citizen(session, "regulation-links@example.com")
    regulation = make_regulation(session)

    session.add(
        GovernmentDocument(
            citizen_id=citizen.citizen_id,
            regulation_id=regulation.regulation_id,
            document_type="Aadhaar",
        )
    )
    session.add(
        CitizenQuery(
            citizen_id=citizen.citizen_id,
            regulation_id=regulation.regulation_id,
            query_text="Which documents do I need?",
        )
    )
    session.add(
        EligibilityCheck(
            citizen_id=citizen.citizen_id,
            regulation_id=regulation.regulation_id,
            result="eligible",
            warning_issued=False,
        )
    )
    session.flush()
    session.refresh(regulation)

    assert len(regulation.documents) == 1
    assert len(regulation.queries) == 1
    assert len(regulation.eligibility_checks) == 1
    assert regulation.documents[0].document_type == "Aadhaar"


def test_appointment_can_have_feedback_and_eligibility_checks(session):
    citizen = make_citizen(session, "appointment-children@example.com")
    regulation = make_regulation(session)
    appointment = make_appointment(session, citizen)

    session.add(
        EligibilityCheck(
            citizen_id=citizen.citizen_id,
            appointment_id=appointment.appointment_id,
            regulation_id=regulation.regulation_id,
            result="incomplete",
            missing_documents="Income Proof",
            warning_issued=True,
        )
    )
    session.add(
        Feedback(
            citizen_id=citizen.citizen_id,
            appointment_id=appointment.appointment_id,
            sentiment="negative",
            urgency="high",
            comments="Waited for two hours.",
        )
    )
    session.flush()
    session.refresh(appointment)

    assert len(appointment.eligibility_checks) == 1
    assert len(appointment.feedbacks) == 1
    assert appointment.eligibility_checks[0].warning_issued is True
    assert appointment.feedbacks[0].citizen.citizen_id == citizen.citizen_id


def test_citizen_has_documents_queries_checks_and_feedback(session):
    """Covers the remaining one-to-many links from Citizen in the ERD."""
    citizen = make_citizen(session, "all-children@example.com")
    regulation = make_regulation(session)
    appointment = make_appointment(session, citizen)

    session.add_all(
        [
            GovernmentDocument(
                citizen_id=citizen.citizen_id, document_type="Ration Card"
            ),
            CitizenQuery(citizen_id=citizen.citizen_id, query_text="Am I eligible?"),
            EligibilityCheck(
                citizen_id=citizen.citizen_id,
                regulation_id=regulation.regulation_id,
                result="eligible",
            ),
            Feedback(
                citizen_id=citizen.citizen_id,
                appointment_id=appointment.appointment_id,
                comments="Good service.",
            ),
        ]
    )
    session.flush()
    session.refresh(citizen)

    assert len(citizen.documents) == 1
    assert len(citizen.queries) == 1
    assert len(citizen.eligibility_checks) == 1
    assert len(citizen.feedbacks) == 1


def test_defaults_are_applied(session):
    """Status and OCR columns should get their default values."""
    citizen = make_citizen(session, "defaults@example.com")
    document = GovernmentDocument(
        citizen_id=citizen.citizen_id, document_type="Aadhaar"
    )
    session.add(document)
    session.flush()

    assert document.ocr_status == "pending"
    assert document.verification_status == "pending"
    assert document.upload_date is not None
    assert document.rejection_reason is None
