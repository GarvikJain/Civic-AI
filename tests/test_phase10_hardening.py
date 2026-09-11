"""Phase 10: officer audit, concurrency, attribution, and dashboard stats."""

import pytest
from sqlalchemy import select

from ai_modules.document_verification.states import VerificationStatus
from backend.core.roles import Role
from backend.models.appointment import Appointment
from backend.models.government_document import GovernmentDocument
from backend.models.officer import Officer
from backend.models.user import User
from backend.services import document_service
from tests.factories import add_user, auth_header, citizen_header, role_header
from tests.test_document_api import StubPipeline, review_outcome, upload
from tests.test_queue_api import create_appointment

SUMMARY_URL = "/api/v1/officers/dashboard/summary"
FORBIDDEN_KEYS = {
    "password",
    "hashed_password",
    "access_token",
    "jwt",
    "stored_filename",
    "extracted_data",
}


@pytest.fixture
def stub_pipeline(monkeypatch, tmp_path):
    from backend.core import config as config_module

    monkeypatch.setattr(config_module.settings, "documents_dir", str(tmp_path))
    pipeline = StubPipeline()
    monkeypatch.setattr(document_service, "get_verification_pipeline", lambda: pipeline)
    return pipeline


def officer_headers(client, session_factory, email: str) -> dict:
    add_user(session_factory, email, Role.OFFICER)
    return auth_header(client, email)


def user_id_for(session_factory, email: str) -> int:
    db = session_factory()
    try:
        return db.scalar(select(User.id).where(User.email == email))
    finally:
        db.close()


def officer_id_for_user(session_factory, email: str) -> int:
    db = session_factory()
    try:
        return db.scalar(
            select(Officer.officer_id).join(User).where(User.email == email)
        )
    finally:
        db.close()


def stored_document(session_factory, document_id: int) -> GovernmentDocument:
    db = session_factory()
    try:
        document = db.get(GovernmentDocument, document_id)
        db.expunge(document)
        return document
    finally:
        db.close()


def assert_no_secrets(payload) -> None:
    text = str(payload).lower()
    for key in FORBIDDEN_KEYS:
        assert key not in text


def test_staff_account_gets_an_officer_profile_linked_by_user_id(
    client, session_factory
):
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    created = client.post(
        "/api/v1/auth/users",
        json={
            "full_name": "Linked Officer",
            "email": "linked-officer@example.com",
            "password": "civicai-password",
            "role": "officer",
        },
        headers=admin,
    )
    assert created.status_code == 201
    user_id = user_id_for(session_factory, "linked-officer@example.com")
    db = session_factory()
    try:
        officer = db.scalar(select(Officer).where(Officer.user_id == user_id))
        assert officer is not None
        assert officer.user_id == user_id
        assert officer.name == "Linked Officer"
        assert officer.email == "linked-officer@example.com"
    finally:
        db.close()


def test_officer_approval_records_reviewer_identity_and_timestamp(
    client, session_factory, stub_pipeline
):
    stub_pipeline.outcome = review_outcome("Needs officer review.")
    citizen = citizen_header(client, "audit-owner@example.com")
    document_id = upload(client, citizen).json()["document_id"]
    officer = officer_headers(client, session_factory, "auditor@example.com")
    officer_user_id = user_id_for(session_factory, "auditor@example.com")

    approved = client.post(
        f"/api/v1/officers/documents/{document_id}/approve", json={}, headers=officer
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["verification_status"] == "verified"
    assert body["reviewed_by_user_id"] == officer_user_id
    assert body["reviewed_at"] is not None
    assert body["reviewer_name"] == "Test officer"
    assert body["rejection_reason"] is None
    assert "extracted_data" not in body

    stored = stored_document(session_factory, document_id)
    assert stored.reviewed_by_user_id == officer_user_id
    assert stored.reviewed_at is not None
    assert stored.verification_status == VerificationStatus.VERIFIED.value
    assert "reviewer" not in (stored.extracted_data or "").lower()

    seen = client.get(f"/api/v1/documents/{document_id}", headers=citizen)
    assert seen.json()["reviewed_by_user_id"] == officer_user_id
    assert seen.json()["reviewer_name"] == "Test officer"


def test_officer_rejection_records_reason_and_reviewer(
    client, session_factory, stub_pipeline
):
    stub_pipeline.outcome = review_outcome("Needs officer review.")
    citizen = citizen_header(client, "reject-owner@example.com")
    document_id = upload(client, citizen).json()["document_id"]
    officer = officer_headers(client, session_factory, "rejector@example.com")
    officer_user_id = user_id_for(session_factory, "rejector@example.com")

    rejected = client.post(
        f"/api/v1/officers/documents/{document_id}/reject",
        json={"reason": "The scan is unreadable."},
        headers=officer,
    )
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["verification_status"] == "rejected"
    assert body["rejection_reason"] == "The scan is unreadable."
    assert body["reviewed_by_user_id"] == officer_user_id
    assert body["reviewed_at"] is not None
    assert body["reviewer_name"] == "Test officer"


def test_conflicting_final_decisions_keep_the_first_officer(
    client, session_factory, stub_pipeline
):
    stub_pipeline.outcome = review_outcome("Needs officer review.")
    citizen = citizen_header(client, "race-owner@example.com")
    document_id = upload(client, citizen).json()["document_id"]
    first = officer_headers(client, session_factory, "alpha-officer@example.com")
    second = officer_headers(client, session_factory, "beta-officer@example.com")
    first_user_id = user_id_for(session_factory, "alpha-officer@example.com")

    approved = client.post(
        f"/api/v1/officers/documents/{document_id}/approve", json={}, headers=first
    )
    conflict = client.post(
        f"/api/v1/officers/documents/{document_id}/reject",
        json={"reason": "Should not overwrite the first decision."},
        headers=second,
    )
    assert approved.status_code == 200
    assert conflict.status_code == 409
    assert "already been finalized" in conflict.json()["detail"].lower()

    stored = stored_document(session_factory, document_id)
    assert stored.verification_status == "verified"
    assert stored.reviewed_by_user_id == first_user_id
    assert stored.rejection_reason is None


def test_second_officer_cannot_approve_after_rejection(
    client, session_factory, stub_pipeline
):
    stub_pipeline.outcome = review_outcome("Needs officer review.")
    citizen = citizen_header(client, "final-reject@example.com")
    document_id = upload(client, citizen).json()["document_id"]
    first = officer_headers(client, session_factory, "winner@example.com")
    second = officer_headers(client, session_factory, "late@example.com")
    winner_id = user_id_for(session_factory, "winner@example.com")

    rejected = client.post(
        f"/api/v1/officers/documents/{document_id}/reject",
        json={"reason": "Identity mismatch on the scan."},
        headers=first,
    )
    conflict = client.post(
        f"/api/v1/officers/documents/{document_id}/approve", json={}, headers=second
    )
    assert rejected.status_code == 200
    assert conflict.status_code == 409
    stored = stored_document(session_factory, document_id)
    assert stored.verification_status == "rejected"
    assert stored.reviewed_by_user_id == winner_id
    assert stored.rejection_reason == "Identity mismatch on the scan."


@pytest.mark.parametrize(
    "status",
    ["pending", "processing", "verified", "rejected"],
)
def test_invalid_document_review_transitions_are_conflict(
    client, session_factory, status
):
    citizen = citizen_header(client, f"state-{status}@example.com")
    officer = officer_headers(client, session_factory, f"state-off-{status}@example.com")
    db = session_factory()
    try:
        from backend.models.citizen import Citizen

        owner = db.scalar(
            select(Citizen).join(User).where(User.email == f"state-{status}@example.com")
        )
        document = GovernmentDocument(
            citizen_id=owner.citizen_id,
            document_type="Income Certificate",
            verification_status=status,
            ocr_status="completed",
        )
        db.add(document)
        db.commit()
        document_id = document.document_id
    finally:
        db.close()

    approve = client.post(
        f"/api/v1/officers/documents/{document_id}/approve", json={}, headers=officer
    )
    reject = client.post(
        f"/api/v1/officers/documents/{document_id}/reject",
        json={"reason": "Not allowed from this state."},
        headers=officer,
    )
    assert approve.status_code == 409
    assert reject.status_code == 409
    stored = stored_document(session_factory, document_id)
    assert stored.verification_status == status
    assert stored.reviewed_by_user_id is None


def test_citizen_cannot_reverify_a_finalized_document(
    client, session_factory, stub_pipeline
):
    stub_pipeline.outcome = review_outcome("Needs officer review.")
    citizen = citizen_header(client, "final-owner@example.com")
    document_id = upload(client, citizen).json()["document_id"]
    officer = officer_headers(client, session_factory, "final-off@example.com")
    assert (
        client.post(
            f"/api/v1/officers/documents/{document_id}/approve",
            json={},
            headers=officer,
        ).status_code
        == 200
    )
    again = client.post(f"/api/v1/documents/{document_id}/verify", headers=citizen)
    assert again.status_code == 409


def test_starting_service_attributes_the_authenticated_officer(
    client, session_factory
):
    citizen = citizen_header(client, "served-owner@example.com")
    officer = officer_headers(client, session_factory, "counter@example.com")
    created = create_appointment(client, citizen)
    assert created.status_code == 201, created.text
    appointment_id = created.json()["appointment_id"]
    assert created.json()["officer_id"] is None

    started = client.post(
        f"/api/v1/queue/appointments/{appointment_id}/start", headers=officer
    )
    assert started.status_code == 200, started.text
    officer_user_id = user_id_for(session_factory, "counter@example.com")
    officer_id = officer_id_for_user(session_factory, "counter@example.com")
    assert started.json()["officer_id"] == officer_id
    assert officer_id != officer_user_id

    db = session_factory()
    try:
        appointment = db.get(Appointment, appointment_id)
        assert appointment.officer_id == officer_id
    finally:
        db.close()


def test_citizen_cannot_assign_an_officer_on_create(client):
    headers = citizen_header(client, "no-assign@example.com")
    from tests.test_queue_api import create_payload

    response = client.post(
        "/api/v1/queue/appointments",
        json=create_payload(extra={"officer_id": 1}),
        headers=headers,
    )
    assert response.status_code == 422


def test_dashboard_officer_stats_use_attributed_records(
    client, session_factory, stub_pipeline
):
    stub_pipeline.outcome = review_outcome("Needs officer review.")
    citizen = citizen_header(client, "stats-owner@example.com")
    officer = officer_headers(client, session_factory, "stats-off@example.com")
    other = officer_headers(client, session_factory, "stats-other@example.com")

    first_doc = upload(client, citizen).json()["document_id"]
    second_doc = upload(client, citizen).json()["document_id"]
    assert (
        client.post(
            f"/api/v1/officers/documents/{first_doc}/approve", json={}, headers=officer
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/officers/documents/{second_doc}/reject",
            json={"reason": "Unreadable scan."},
            headers=officer,
        ).status_code
        == 200
    )

    created = create_appointment(client, citizen)
    appointment_id = created.json()["appointment_id"]
    assert (
        client.post(
            f"/api/v1/queue/appointments/{appointment_id}/start", headers=officer
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/queue/appointments/{appointment_id}/complete", headers=officer
        ).status_code
        == 200
    )

    body = client.get(SUMMARY_URL, headers=officer).json()
    assert_no_secrets(body)
    stats = {row["officer_id"]: row for row in body["officer_stats"]}
    mine_id = officer_id_for_user(session_factory, "stats-off@example.com")
    other_id = officer_id_for_user(session_factory, "stats-other@example.com")
    mine = stats[mine_id]
    assert mine["appointments_handled"] == 1
    assert mine["appointments_completed"] == 1
    assert mine["documents_reviewed"] == 2
    assert mine["documents_approved"] == 1
    assert mine["documents_rejected"] == 1
    assert mine["average_actual_wait"] is not None
    assert other_id not in stats

    citizen_headers = citizen_header(client, "stats-citizen@example.com")
    assert client.get(SUMMARY_URL, headers=citizen_headers).status_code == 403
    assert client.get(SUMMARY_URL).status_code == 401


def test_citizen_dashboard_is_available_and_officer_cannot_open_it(
    client, session_factory
):
    citizen = citizen_header(client, "home@example.com")
    response = client.get("/api/v1/citizens/dashboard", headers=citizen)
    assert response.status_code == 200
    assert response.json()["status"] == "available"
    officer = officer_headers(client, session_factory, "no-citizen-home@example.com")
    assert client.get("/api/v1/citizens/dashboard", headers=officer).status_code == 403


def test_frontend_queue_and_eligibility_pages_call_the_api():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "frontend" / "pages"
    queue = (root / "3_Queue_Wait_Time.py").read_text(encoding="utf-8")
    eligibility = (root / "5_Eligibility_Nudge.py").read_text(encoding="utf-8")
    auth = (
        Path(__file__).resolve().parents[1] / "frontend" / "utils" / "auth.py"
    ).read_text(encoding="utf-8")
    assert "/queue/appointments" in queue
    assert "/start" in queue
    assert "officer_id" in queue
    assert "/eligibility/questionnaire" in eligibility
    assert "advisory" in eligibility.lower()
    assert "/auth/register" in auth
