"""API tests for the Officer Productivity Dashboard (Phase 9)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from backend.core.roles import Role
from backend.models.appointment import Appointment
from backend.models.citizen import Citizen
from backend.models.citizen_query import CitizenQuery
from backend.models.feedback import Feedback
from backend.models.government_document import GovernmentDocument
from backend.models.queue_prediction_record import QueuePredictionRecord
from backend.models.regulation import Regulation
from backend.models.user import User
from backend.services import officer_service, queue_service
from tests.factories import citizen_header, role_header

SUMMARY_URL = "/api/v1/officers/dashboard/summary"
DASHBOARD_URL = "/api/v1/officers/dashboard"
NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
FRONTEND_PAGE = (
    Path(__file__).resolve().parents[1] / "frontend" / "pages" / "4_Officer_Dashboard.py"
)
SERVICE_SOURCE = Path(__file__).resolve().parents[1] / "backend" / "services" / "officer_service.py"

FORBIDDEN_KEYS = {
    "password",
    "hashed_password",
    "access_token",
    "jwt",
    "token",
    "stored_filename",
    "extracted_data",
}


def freeze_clock(monkeypatch) -> None:
    monkeypatch.setattr(queue_service, "utcnow", lambda: NOW)


def citizen_id_for(session_factory, email: str) -> int:
    db = session_factory()
    try:
        citizen = db.scalar(select(Citizen).join(User).where(User.email == email))
        return citizen.citizen_id
    finally:
        db.close()


def add_regulation(session_factory, scheme_name="Income Certificate Scheme") -> int:
    db = session_factory()
    try:
        row = Regulation(
            scheme_name=scheme_name,
            department="Revenue",
            eligibility_criteria="Example",
            required_documents="Proof of identity",
        )
        db.add(row)
        db.commit()
        return row.regulation_id
    finally:
        db.close()


def add_appointment(
    session_factory,
    email: str,
    *,
    service_type="Income Certificate",
    when=None,
    predicted_wait_time=10.0,
    status="completed",
) -> int:
    db = session_factory()
    try:
        citizen = db.scalar(select(Citizen).join(User).where(User.email == email))
        row = Appointment(
            citizen_id=citizen.citizen_id,
            service_type=service_type,
            appointment_date=when or NOW,
            status=status,
            queue_number=1,
            predicted_wait_time=predicted_wait_time,
        )
        db.add(row)
        db.commit()
        return row.appointment_id
    finally:
        db.close()


def add_prediction(
    session_factory,
    appointment_id: int,
    *,
    predicted=10.0,
    actual=None,
) -> None:
    db = session_factory()
    try:
        db.add(
            QueuePredictionRecord(
                appointment_id=appointment_id,
                predicted_wait_time=predicted,
                actual_wait_time=actual,
                predicted_at=NOW,
                actual_recorded_at=NOW if actual is not None else None,
                model_version="queue-v1",
            )
        )
        db.commit()
    finally:
        db.close()


def add_document(
    session_factory,
    email: str,
    *,
    document_type="Income Certificate",
    status="verified",
    reason=None,
    uploaded_at=None,
) -> None:
    db = session_factory()
    try:
        citizen = db.scalar(select(Citizen).join(User).where(User.email == email))
        db.add(
            GovernmentDocument(
                citizen_id=citizen.citizen_id,
                document_type=document_type,
                verification_status=status,
                ocr_status="completed",
                rejection_reason=reason,
                upload_date=uploaded_at or NOW,
                stored_filename="must-not-appear.bin",
            )
        )
        db.commit()
    finally:
        db.close()


def add_query(
    session_factory,
    email: str,
    *,
    text="Which documents do I need?",
    regulation_id=None,
    when=None,
) -> None:
    db = session_factory()
    try:
        citizen = db.scalar(select(Citizen).join(User).where(User.email == email))
        db.add(
            CitizenQuery(
                citizen_id=citizen.citizen_id,
                regulation_id=regulation_id,
                query_text=text,
                ai_response="Stored answer that should not appear on the dashboard.",
                query_time=when or NOW,
            )
        )
        db.commit()
    finally:
        db.close()


def add_feedback_row(
    session_factory,
    email: str,
    appointment_id: int,
    *,
    sentiment,
    urgency,
    comments="comment",
    when=None,
) -> None:
    db = session_factory()
    try:
        citizen = db.scalar(select(Citizen).join(User).where(User.email == email))
        db.add(
            Feedback(
                citizen_id=citizen.citizen_id,
                appointment_id=appointment_id,
                sentiment=sentiment,
                urgency=urgency,
                comments=comments,
                date_submitted=when or NOW,
            )
        )
        db.commit()
    finally:
        db.close()


def assert_no_secrets(payload: dict) -> None:
    dumped = json.dumps(payload).lower()
    assert "hashed_password" not in dumped
    assert "access_token" not in dumped
    assert "stored_filename" not in dumped
    assert "must-not-appear.bin" not in dumped
    assert "data/documents" not in dumped
    assert "stored answer that should not appear" not in dumped

    def walk(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                assert key.lower() not in FORBIDDEN_KEYS, key
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)


def seed_dashboard(session_factory, email: str) -> dict[str, int]:
    regulation_id = add_regulation(session_factory)
    income = add_appointment(
        session_factory, email, service_type="Income Certificate", predicted_wait_time=10.0
    )
    birth = add_appointment(
        session_factory,
        email,
        service_type="Birth Certificate",
        predicted_wait_time=20.0,
    )
    old = add_appointment(
        session_factory,
        email,
        service_type="Income Certificate",
        predicted_wait_time=40.0,
        when=NOW - timedelta(days=10),
    )
    add_prediction(session_factory, income, predicted=10.0, actual=12.0)
    add_prediction(session_factory, birth, predicted=20.0, actual=None)
    add_prediction(session_factory, old, predicted=40.0, actual=30.0)

    add_document(session_factory, email, status="verified")
    add_document(
        session_factory,
        email,
        status="rejected",
        reason="Income exceeds the scheme limit.",
    )
    add_document(
        session_factory,
        email,
        status="rejected",
        reason="Income exceeds the scheme limit.",
    )
    add_document(
        session_factory,
        email,
        status="rejected",
        reason="Name does not match the application.",
    )
    add_document(session_factory, email, status="needs_review")
    add_document(session_factory, email, status="pending")
    add_document(
        session_factory,
        email,
        status="verified",
        document_type="Birth Certificate",
    )
    add_document(
        session_factory,
        email,
        status="verified",
        uploaded_at=NOW - timedelta(days=10),
    )

    add_query(session_factory, email, regulation_id=regulation_id)
    add_query(
        session_factory,
        email,
        text="How long is the residence requirement?",
        regulation_id=regulation_id,
    )
    add_query(session_factory, email, text="General office hours?", regulation_id=None)

    add_feedback_row(
        session_factory,
        email,
        income,
        sentiment="negative",
        urgency="high",
        comments="Emergency: the counter was unsafe.",
    )
    add_feedback_row(
        session_factory,
        email,
        birth,
        sentiment="negative",
        urgency="medium",
        comments="Pending for weeks with no response.",
    )
    extra = add_appointment(
        session_factory, email, service_type="Residence Certificate", predicted_wait_time=8.0
    )
    add_feedback_row(
        session_factory,
        email,
        extra,
        sentiment="positive",
        urgency="low",
        comments="The officer was extremely helpful and the process was quick.",
    )
    add_feedback_row(
        session_factory,
        email,
        old,
        sentiment="positive",
        urgency="high",
        comments="Kind staff but this is an emergency.",
        when=NOW - timedelta(days=10),
    )
    return {"income": income, "birth": birth, "old": old, "residence": extra}


def test_unauthenticated_dashboard_is_401(client):
    assert client.get(SUMMARY_URL).status_code == 401
    assert client.get(DASHBOARD_URL).status_code == 401


def test_citizen_dashboard_is_403(client):
    headers = citizen_header(client, "citizen-dash@example.com")
    assert client.get(SUMMARY_URL, headers=headers).status_code == 403
    assert client.get(DASHBOARD_URL, headers=headers).status_code == 403


def test_officer_and_admin_can_load_empty_dashboard(client, session_factory, monkeypatch):
    freeze_clock(monkeypatch)
    officer = role_header(client, session_factory, Role.OFFICER)
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    for headers in (officer, admin):
        response = client.get(SUMMARY_URL, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["module"] == "Officer Productivity Dashboard"
        assert body["overview"]["total_appointments"] == 0
        assert body["documents"]["total"] == 0
        assert body["feedback"]["escalated"] == 0
        assert body["flagged_feedback"] == []
        assert_no_secrets(body)


def test_document_counts_and_rejection_reasons(client, session_factory, monkeypatch):
    freeze_clock(monkeypatch)
    citizen_header(client, "docs@example.com")
    seed_dashboard(session_factory, "docs@example.com")
    headers = role_header(client, session_factory, Role.OFFICER)
    body = client.get(SUMMARY_URL, headers=headers).json()
    documents = body["documents"]
    assert documents["total"] == 8
    assert documents["verified"] == 3
    assert documents["rejected"] == 3
    assert documents["needs_review"] == 1
    assert documents["pending"] == 1
    reasons = {item["label"]: item["count"] for item in documents["top_rejection_reasons"]}
    assert reasons["Income exceeds the scheme limit."] == 2
    assert reasons["Name does not match the application."] == 1


def test_queue_counts_actual_wait_and_prediction_error(
    client, session_factory, monkeypatch
):
    freeze_clock(monkeypatch)
    citizen_header(client, "queue@example.com")
    seed_dashboard(session_factory, "queue@example.com")
    headers = role_header(client, session_factory, Role.OFFICER)
    body = client.get(SUMMARY_URL, headers=headers).json()
    queue = body["queue"]
    assert queue["total_appointments"] == 4
    assert queue["today_appointments"] == 3
    assert queue["average_predicted_wait"] == 19.5
    assert queue["average_actual_wait"] == 21.0
    assert queue["average_absolute_error"] == 6.0
    assert queue["records_with_actual_wait"] == 2
    by_service = {row["service_type"]: row["count"] for row in queue["by_service_type"]}
    assert by_service["Income Certificate"] == 2
    assert by_service["Birth Certificate"] == 1
    assert by_service["Residence Certificate"] == 1


def test_null_actual_wait_is_not_treated_as_zero(client, session_factory, monkeypatch):
    freeze_clock(monkeypatch)
    citizen_header(client, "null-wait@example.com")
    appointment_id = add_appointment(
        session_factory, "null-wait@example.com", predicted_wait_time=50.0
    )
    add_prediction(session_factory, appointment_id, predicted=50.0, actual=None)
    headers = role_header(client, session_factory, Role.OFFICER)
    queue = client.get(SUMMARY_URL, headers=headers).json()["queue"]
    assert queue["average_predicted_wait"] == 50.0
    assert queue["average_actual_wait"] is None
    assert queue["average_absolute_error"] is None
    assert queue["records_with_actual_wait"] == 0


def test_query_counts_use_scheme_not_pii(client, session_factory, monkeypatch):
    freeze_clock(monkeypatch)
    headers_citizen = citizen_header(client, "queries@example.com")
    seed_dashboard(session_factory, "queries@example.com")
    officer = role_header(client, session_factory, Role.OFFICER)
    queries = client.get(SUMMARY_URL, headers=officer).json()["queries"]
    assert queries["total"] == 3
    labels = {item["label"]: item["count"] for item in queries["by_scheme"]}
    assert labels["Income Certificate Scheme"] == 2
    assert labels["Unspecified"] == 1
    assert queries["service_filter_applied"] is False
    dumped = json.dumps(queries)
    assert "citizen_id" not in dumped
    assert headers_citizen  # citizen exists; id must not leak in this section
    assert citizen_id_for(session_factory, "queries@example.com")
    assert "ai_response" not in dumped
    assert "Stored answer" not in dumped


def test_feedback_and_flagged_escalation(client, session_factory, monkeypatch):
    freeze_clock(monkeypatch)
    citizen_header(client, "fb@example.com")
    ids = seed_dashboard(session_factory, "fb@example.com")
    officer = role_header(client, session_factory, Role.OFFICER)
    body = client.get(SUMMARY_URL, headers=officer).json()
    feedback = body["feedback"]
    assert feedback["total"] == 4
    assert feedback["positive"] == 2
    assert feedback["negative"] == 2
    assert feedback["urgency_high"] == 2
    assert feedback["urgency_medium"] == 1
    assert feedback["urgency_low"] == 1
    assert feedback["escalated"] == 1
    flagged = body["flagged_feedback"]
    assert len(flagged) == 1
    assert flagged[0]["appointment_id"] == ids["income"]
    assert flagged[0]["sentiment"] == "negative"
    assert flagged[0]["urgency"] == "high"
    assert "citizen_id" not in flagged[0]
    by_service = {row["service_type"]: row for row in feedback["by_service_type"]}
    assert by_service["Income Certificate"]["escalated"] == 1
    assert by_service["Birth Certificate"]["negative"] == 1
    assert by_service["Birth Certificate"]["escalated"] == 0


def test_service_type_filter(client, session_factory, monkeypatch):
    freeze_clock(monkeypatch)
    citizen_header(client, "filter@example.com")
    seed_dashboard(session_factory, "filter@example.com")
    officer = role_header(client, session_factory, Role.OFFICER)
    body = client.get(
        SUMMARY_URL,
        headers=officer,
        params={"service_type": "Birth Certificate"},
    ).json()
    assert body["service_type"] == "Birth Certificate"
    assert body["queue"]["total_appointments"] == 1
    assert body["documents"]["total"] == 1
    assert body["documents"]["verified"] == 1
    assert body["feedback"]["total"] == 1
    assert body["feedback"]["negative"] == 1
    assert body["flagged_feedback"] == []
    assert body["queries"]["total"] == 3
    assert body["queries"]["service_filter_applied"] is False


def test_time_filters(client, session_factory, monkeypatch):
    freeze_clock(monkeypatch)
    citizen_header(client, "time@example.com")
    seed_dashboard(session_factory, "time@example.com")
    officer = role_header(client, session_factory, Role.OFFICER)
    today = client.get(
        SUMMARY_URL, headers=officer, params={"period": "today"}
    ).json()
    week = client.get(
        SUMMARY_URL, headers=officer, params={"period": "last_7_days"}
    ).json()
    month = client.get(
        SUMMARY_URL, headers=officer, params={"period": "last_30_days"}
    ).json()
    all_time = client.get(SUMMARY_URL, headers=officer).json()

    assert today["queue"]["total_appointments"] == 3
    assert week["queue"]["total_appointments"] == 3
    assert month["queue"]["total_appointments"] == 4
    assert all_time["queue"]["total_appointments"] == 4
    assert today["documents"]["total"] == 7
    assert month["documents"]["total"] == 8
    assert today["feedback"]["total"] == 3
    assert all_time["feedback"]["total"] == 4


def test_invalid_filters_are_422(client, session_factory):
    officer = role_header(client, session_factory, Role.OFFICER)
    bad_period = client.get(
        SUMMARY_URL, headers=officer, params={"period": "last_year"}
    )
    bad_service = client.get(
        SUMMARY_URL, headers=officer, params={"service_type": "Passport"}
    )
    assert bad_period.status_code == 422
    assert bad_service.status_code == 422


def test_legacy_dashboard_path_matches_summary(client, session_factory, monkeypatch):
    freeze_clock(monkeypatch)
    officer = role_header(client, session_factory, Role.OFFICER)
    summary = client.get(SUMMARY_URL, headers=officer).json()
    legacy = client.get(DASHBOARD_URL, headers=officer).json()
    summary.pop("generated_at", None)
    legacy.pop("generated_at", None)
    assert summary == legacy


def test_dashboard_does_not_use_csv_or_llm():
    source = SERVICE_SOURCE.read_text(encoding="utf-8").lower()
    assert ".csv" not in source
    assert "dataset_generator" not in source
    assert "import groq" not in source
    assert "from groq" not in source
    assert "openai" not in source


def test_frontend_dashboard_uses_backend_and_hides_from_citizens():
    text = FRONTEND_PAGE.read_text(encoding="utf-8")
    assert "/officers/dashboard/summary" in text
    assert "403" in text
    assert "officers and administrators" in text.lower()
    assert "Flagged feedback" in text
    assert "Document verification" in text
    assert "Officer handling statistics" in text
    assert "st.bar_chart" in text
    assert "citizen_id" not in text.lower() or "citizen {" in text
    # Review queue may mention citizen_id for the existing officer workflow.
    assert "hashed_password" not in text
    assert "GROQ" not in text or "does not call Groq" in text


def test_module_status_is_available(client):
    response = client.get("/api/v1/officers/status")
    assert response.status_code == 200
    assert response.json()["status"] == "available"
