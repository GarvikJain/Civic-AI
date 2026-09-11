"""API tests for Citizen Feedback Sentiment Analysis (Phase 8)."""

from datetime import datetime, timezone

from sqlalchemy import select

from backend.core.roles import Role
from backend.models.appointment import Appointment
from backend.models.citizen import Citizen
from backend.models.feedback import Feedback
from backend.models.user import User
from tests.factories import citizen_header, role_header

CREATE_URL = "/api/v1/feedback"
LIST_URL = "/api/v1/feedback"
FLAGGED_URL = "/api/v1/officers/feedback/flagged"

POSITIVE_TEXT = "The officer was extremely helpful and the process was quick."
NEGATIVE_MEDIUM_TEXT = (
    "My application has been pending for weeks and I have received no response."
)
NEGATIVE_HIGH_TEXT = "I am facing a serious issue and need immediate assistance."
MAX_COMMENTS = 2000


def add_appointment(session_factory, email: str, status: str = "completed") -> int:
    db = session_factory()
    try:
        citizen = db.scalar(select(Citizen).join(User).where(User.email == email))
        row = Appointment(
            citizen_id=citizen.citizen_id,
            service_type="Income Certificate",
            appointment_date=datetime.now(timezone.utc),
            status=status,
            queue_number=1,
        )
        db.add(row)
        db.commit()
        return row.appointment_id
    finally:
        db.close()


def stored_feedback(session_factory) -> list[Feedback]:
    db = session_factory()
    try:
        return list(db.scalars(select(Feedback)).all())
    finally:
        db.close()


def test_unauthenticated_submission_is_401(client, session_factory):
    response = client.post(
        CREATE_URL,
        json={"appointment_id": 1, "comments": POSITIVE_TEXT},
    )
    assert response.status_code == 401
    assert stored_feedback(session_factory) == []


def test_unauthenticated_list_is_401(client):
    response = client.get(LIST_URL)
    assert response.status_code == 401


def test_citizen_submits_own_completed_appointment(client, session_factory):
    headers = citizen_header(client, "own@example.com")
    appointment_id = add_appointment(session_factory, "own@example.com")
    response = client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": POSITIVE_TEXT},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["appointment_id"] == appointment_id
    assert body["sentiment"] == "positive"
    assert body["urgency"] == "low"
    assert body["escalation_required"] is False
    assert body["service_type"] == "Income Certificate"
    assert "citizen_id" in body
    rows = stored_feedback(session_factory)
    assert len(rows) == 1
    assert rows[0].sentiment == "positive"
    assert rows[0].urgency == "low"
    assert rows[0].comments == POSITIVE_TEXT


def test_citizen_cannot_submit_another_citizens_appointment(client, session_factory):
    owner = citizen_header(client, "owner@example.com")
    appointment_id = add_appointment(session_factory, "owner@example.com")
    other = citizen_header(client, "other@example.com")
    response = client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": POSITIVE_TEXT},
        headers=other,
    )
    assert response.status_code == 404
    assert stored_feedback(session_factory) == []
    # Owner can still submit afterwards.
    owned = client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": POSITIVE_TEXT},
        headers=owner,
    )
    assert owned.status_code == 201


def test_foreign_appointment_id_does_not_reveal_existence(client, session_factory):
    citizen_header(client, "owner2@example.com")
    appointment_id = add_appointment(session_factory, "owner2@example.com")
    other = citizen_header(client, "stranger@example.com")
    missing = client.post(
        CREATE_URL,
        json={"appointment_id": 99999, "comments": POSITIVE_TEXT},
        headers=other,
    )
    foreign = client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": POSITIVE_TEXT},
        headers=other,
    )
    assert missing.status_code == 404
    assert foreign.status_code == 404
    assert missing.json()["detail"] == foreign.json()["detail"]


def test_feedback_before_completion_is_rejected(client, session_factory):
    headers = citizen_header(client, "early@example.com")
    appointment_id = add_appointment(
        session_factory, "early@example.com", status="scheduled"
    )
    response = client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": POSITIVE_TEXT},
        headers=headers,
    )
    assert response.status_code == 409
    assert stored_feedback(session_factory) == []


def test_duplicate_feedback_is_rejected(client, session_factory):
    headers = citizen_header(client, "dup@example.com")
    appointment_id = add_appointment(session_factory, "dup@example.com")
    first = client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": POSITIVE_TEXT},
        headers=headers,
    )
    second = client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": NEGATIVE_MEDIUM_TEXT},
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 409
    rows = stored_feedback(session_factory)
    assert len(rows) == 1
    assert rows[0].comments == POSITIVE_TEXT


def test_empty_and_whitespace_comments_are_422(client, session_factory):
    headers = citizen_header(client, "blank@example.com")
    appointment_id = add_appointment(session_factory, "blank@example.com")
    empty = client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": ""},
        headers=headers,
    )
    whitespace = client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": "   \n"},
        headers=headers,
    )
    assert empty.status_code == 422
    assert whitespace.status_code == 422
    assert stored_feedback(session_factory) == []


def test_oversized_comments_are_422(client, session_factory):
    headers = citizen_header(client, "big@example.com")
    appointment_id = add_appointment(session_factory, "big@example.com")
    response = client.post(
        CREATE_URL,
        json={
            "appointment_id": appointment_id,
            "comments": "a" * (MAX_COMMENTS + 1),
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert stored_feedback(session_factory) == []


def test_max_length_comments_are_accepted(client, session_factory):
    headers = citizen_header(client, "max@example.com")
    appointment_id = add_appointment(session_factory, "max@example.com")
    comments = "helpful " + ("a" * (MAX_COMMENTS - 8))
    assert len(comments) == MAX_COMMENTS
    response = client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": comments},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert stored_feedback(session_factory)[0].comments == comments


def test_unexpected_and_server_fields_are_422(client, session_factory):
    headers = citizen_header(client, "extra@example.com")
    appointment_id = add_appointment(session_factory, "extra@example.com")
    for extra in (
        {"sentiment": "positive"},
        {"urgency": "high"},
        {"citizen_id": 1},
        {"escalation_required": True},
        {"escalation_status": True},
        {"date_submitted": "2026-01-01T00:00:00Z"},
        {"feedback_id": 9},
    ):
        response = client.post(
            CREATE_URL,
            json={
                "appointment_id": appointment_id,
                "comments": POSITIVE_TEXT,
                **extra,
            },
            headers=headers,
        )
        assert response.status_code == 422, extra
    assert stored_feedback(session_factory) == []


def test_officer_cannot_submit_citizen_feedback(client, session_factory):
    citizen_header(client, "served@example.com")
    appointment_id = add_appointment(session_factory, "served@example.com")
    officer = role_header(client, session_factory, Role.OFFICER)
    response = client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": POSITIVE_TEXT},
        headers=officer,
    )
    assert response.status_code == 403
    assert stored_feedback(session_factory) == []


def test_citizen_retrieves_only_own_feedback(client, session_factory):
    first = citizen_header(client, "one@example.com")
    second = citizen_header(client, "two@example.com")
    first_id = add_appointment(session_factory, "one@example.com")
    second_id = add_appointment(session_factory, "two@example.com")
    created = client.post(
        CREATE_URL,
        json={"appointment_id": first_id, "comments": POSITIVE_TEXT},
        headers=first,
    )
    client.post(
        CREATE_URL,
        json={"appointment_id": second_id, "comments": NEGATIVE_MEDIUM_TEXT},
        headers=second,
    )
    listed = client.get(LIST_URL, headers=first)
    assert listed.status_code == 200
    rows = listed.json()["feedbacks"]
    assert len(rows) == 1
    assert rows[0]["appointment_id"] == first_id

    own = client.get(f"{LIST_URL}/{created.json()['feedback_id']}", headers=first)
    assert own.status_code == 200
    other = client.get(
        f"{LIST_URL}/{created.json()['feedback_id']}", headers=second
    )
    assert other.status_code == 404


def test_officer_and_admin_can_retrieve_flagged_feedback(client, session_factory):
    citizen = citizen_header(client, "flag@example.com")
    low_id = add_appointment(session_factory, "flag@example.com")
    high_id = add_appointment(session_factory, "flag@example.com")
    client.post(
        CREATE_URL,
        json={"appointment_id": low_id, "comments": POSITIVE_TEXT},
        headers=citizen,
    )
    flagged = client.post(
        CREATE_URL,
        json={"appointment_id": high_id, "comments": NEGATIVE_HIGH_TEXT},
        headers=citizen,
    )
    assert flagged.status_code == 201
    assert flagged.json()["escalation_required"] is True

    officer = role_header(client, session_factory, Role.OFFICER)
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    for headers in (officer, admin):
        response = client.get(FLAGGED_URL, headers=headers)
        assert response.status_code == 200, response.text
        rows = response.json()["feedbacks"]
        assert len(rows) == 1
        assert rows[0]["sentiment"] == "negative"
        assert rows[0]["urgency"] == "high"
        assert rows[0]["escalation_required"] is True
        assert rows[0]["appointment_id"] == high_id
        assert rows[0]["service_type"] == "Income Certificate"

    listed = client.get(LIST_URL, headers=officer)
    assert listed.status_code == 200
    assert len(listed.json()["feedbacks"]) == 2


def test_non_officer_cannot_retrieve_flagged_feedback(client, session_factory):
    citizen = citizen_header(client, "nofog@example.com")
    appointment_id = add_appointment(session_factory, "nofog@example.com")
    client.post(
        CREATE_URL,
        json={"appointment_id": appointment_id, "comments": NEGATIVE_HIGH_TEXT},
        headers=citizen,
    )
    response = client.get(FLAGGED_URL, headers=citizen)
    assert response.status_code == 403


def test_unauthenticated_flagged_is_401(client):
    response = client.get(FLAGGED_URL)
    assert response.status_code == 401


def test_server_generates_labels_for_phase8_examples(client, session_factory):
    headers = citizen_header(client, "examples@example.com")
    cases = (
        (POSITIVE_TEXT, "positive", "low", False),
        (NEGATIVE_MEDIUM_TEXT, "negative", "medium", False),
        (NEGATIVE_HIGH_TEXT, "negative", "high", True),
    )
    for comments, sentiment, urgency, escalated in cases:
        appointment_id = add_appointment(session_factory, "examples@example.com")
        response = client.post(
            CREATE_URL,
            json={"appointment_id": appointment_id, "comments": comments},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["sentiment"] == sentiment
        assert body["urgency"] == urgency
        assert body["escalation_required"] is escalated


def test_module_status_is_available(client):
    response = client.get("/api/v1/feedback/status")
    assert response.status_code == 200
    assert response.json()["status"] == "available"
