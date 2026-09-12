"""API tests for Proactive Eligibility Nudge (Phase 7)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ai_modules.document_verification.states import VerificationStatus
from backend.core.roles import Role
from backend.models.eligibility_check import EligibilityCheck
from backend.models.government_document import GovernmentDocument
from backend.models.regulation import Regulation
from tests.factories import citizen_header, role_header

SAMPLE_CRITERIA = (
    "An applicant is eligible for an income certificate under this example "
    "scheme if the total annual household income is below 2,50,000 rupees, "
    "the applicant has been a resident of the district for at least one year, "
    "and the applicant is not already holding a valid income certificate "
    "issued in the same financial year."
)
SAMPLE_DOCUMENTS = (
    "The applicant must submit proof of identity, proof of residence, and "
    "proof of income."
)
PASSING = {
    "annual_household_income": 180000,
    "resident_of_district_at_least_one_year": True,
    "holds_income_certificate_this_year": False,
}


def add_regulation(session_factory, **overrides) -> int:
    values = {
        "scheme_name": "Example Income Certificate Scheme",
        "department": "Revenue",
        "eligibility_criteria": SAMPLE_CRITERIA,
        "required_documents": SAMPLE_DOCUMENTS,
        "circular_reference": "EXAMPLE/CIRC/2026/01",
    }
    values.update(overrides)
    db = session_factory()
    try:
        regulation = Regulation(**values)
        db.add(regulation)
        db.commit()
        return regulation.regulation_id
    finally:
        db.close()


def add_document(
    session_factory,
    citizen_email: str,
    document_type: str,
    status: str = VerificationStatus.VERIFIED.value,
) -> None:
    db = session_factory()
    try:
        from backend.models.citizen import Citizen
        from backend.models.user import User

        citizen = db.scalar(
            select(Citizen).join(User).where(User.email == citizen_email)
        )
        db.add(
            GovernmentDocument(
                citizen_id=citizen.citizen_id,
                document_type=document_type,
                verification_status=status,
                ocr_status="completed",
            )
        )
        db.commit()
    finally:
        db.close()


def booking_slot() -> str:
    when = datetime.now(timezone.utc) + timedelta(days=3)
    while when.weekday() >= 5:
        when += timedelta(days=1)
    return when.replace(hour=10, minute=0, second=0, microsecond=0).isoformat()


def stored_checks(session_factory) -> list[EligibilityCheck]:
    db = session_factory()
    try:
        return list(db.scalars(select(EligibilityCheck)).all())
    finally:
        db.close()


def test_citizen_can_retrieve_questionnaire(client, session_factory):
    regulation_id = add_regulation(session_factory)
    headers = citizen_header(client, "q@example.com")
    response = client.get(
        f"/api/v1/eligibility/questionnaire/{regulation_id}", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["regulation_id"] == regulation_id
    fields = {item["field_name"] for item in body["questions"]}
    assert "annual_household_income" in fields
    assert "operator" not in str(body).lower() or "less_than" not in str(body)
    assert "advisory" in body["advisory_notice"].lower()


def test_nonexistent_regulation_questionnaire_is_404(client):
    headers = citizen_header(client, "missing-reg@example.com")
    response = client.get("/api/v1/eligibility/questionnaire/99999", headers=headers)
    assert response.status_code == 404


def test_valid_answers_create_eligible_check(client, session_factory):
    regulation_id = add_regulation(session_factory)
    headers = citizen_header(client, "ok@example.com")
    for doc_type in ("Identity Proof", "Residence Proof", "Income Proof"):
        add_document(session_factory, "ok@example.com", doc_type)
    response = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": regulation_id, "answers": PASSING},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["result"] == "eligible"
    assert body["warning_issued"] is False
    assert body["missing_documents"] == []
    assert body["citizen_id"]
    rows = stored_checks(session_factory)
    assert len(rows) == 1
    assert rows[0].regulation_id == regulation_id
    assert rows[0].appointment_id is None
    assert rows[0].warning_issued is False


def test_failing_income_is_advisory_and_does_not_block_appointment(
    client, session_factory
):
    regulation_id = add_regulation(session_factory)
    headers = citizen_header(client, "fail@example.com")
    answers = dict(PASSING)
    answers["annual_household_income"] = 400000
    check = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": regulation_id, "answers": answers},
        headers=headers,
    )
    assert check.status_code == 201
    assert check.json()["result"] == "potentially_ineligible"
    assert check.json()["warning_issued"] is True
    assert "income" in check.json()["explanation"].lower()

    booked = client.post(
        "/api/v1/queue/appointments",
        json={
            "service_type": "Income Certificate",
            "appointment_date": booking_slot(),
        },
        headers=headers,
    )
    assert booked.status_code == 201, booked.text
    assert booked.json()["status"] == "scheduled"


def test_manual_review_does_not_block_appointment(client, session_factory):
    regulation_id = add_regulation(
        session_factory,
        scheme_name="Ambiguous Scheme",
        eligibility_criteria="Applicants must be residents of the district.",
        required_documents=None,
    )
    headers = citizen_header(client, "review@example.com")
    check = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": regulation_id, "answers": {}},
        headers=headers,
    )
    assert check.status_code == 201
    assert check.json()["result"] == "manual_review"
    booked = client.post(
        "/api/v1/queue/appointments",
        json={
            "service_type": "Income Certificate",
            "appointment_date": booking_slot(),
        },
        headers=headers,
    )
    assert booked.status_code == 201


def test_answer_validation_errors(client, session_factory):
    regulation_id = add_regulation(session_factory)
    headers = citizen_header(client, "bad@example.com")
    missing = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": regulation_id, "answers": {"annual_household_income": 1}},
        headers=headers,
    )
    assert missing.status_code == 422
    unknown = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": regulation_id, "answers": {**PASSING, "extra": 1}},
        headers=headers,
    )
    assert unknown.status_code == 422
    bad_type = client.post(
        "/api/v1/eligibility/check",
        json={
            "regulation_id": regulation_id,
            "answers": {**PASSING, "annual_household_income": "nope"},
        },
        headers=headers,
    )
    assert bad_type.status_code == 422
    assert stored_checks(session_factory) == []


def test_client_cannot_set_server_fields(client, session_factory):
    regulation_id = add_regulation(session_factory)
    headers = citizen_header(client, "noserver@example.com")
    for extra in (
        {"citizen_id": 1},
        {"result": "eligible"},
        {"warning_issued": False},
        {"missing_documents": []},
    ):
        response = client.post(
            "/api/v1/eligibility/check",
            json={"regulation_id": regulation_id, "answers": PASSING, **extra},
            headers=headers,
        )
        assert response.status_code == 422, extra
    assert stored_checks(session_factory) == []


def test_rejected_and_pending_documents_are_not_verified(client, session_factory):
    regulation_id = add_regulation(session_factory)
    headers = citizen_header(client, "docs@example.com")
    add_document(
        session_factory, "docs@example.com", "Identity Proof", VerificationStatus.REJECTED.value
    )
    add_document(
        session_factory, "docs@example.com", "Residence Proof", VerificationStatus.PENDING.value
    )
    add_document(
        session_factory,
        "docs@example.com",
        "Income Proof",
        VerificationStatus.NEEDS_REVIEW.value,
    )
    response = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": regulation_id, "answers": PASSING},
        headers=headers,
    )
    assert response.status_code == 201
    missing = response.json()["missing_documents"]
    assert "Proof of identity" in missing
    assert "Proof of residence" in missing
    assert "Proof of income" in missing
    assert response.json()["warning_issued"] is True
    assert response.json()["result"] == "eligible"


def test_verified_documents_clear_missing_list(client, session_factory):
    regulation_id = add_regulation(session_factory)
    headers = citizen_header(client, "verified-docs@example.com")
    add_document(session_factory, "verified-docs@example.com", "Identity Proof")
    add_document(session_factory, "verified-docs@example.com", "Residence Proof")
    add_document(session_factory, "verified-docs@example.com", "Income Proof")
    response = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": regulation_id, "answers": PASSING},
        headers=headers,
    )
    assert response.json()["missing_documents"] == []


def test_ownership_and_staff_access(client, session_factory):
    regulation_id = add_regulation(session_factory)
    owner = citizen_header(client, "owner-el@example.com")
    other = citizen_header(client, "other-el@example.com")
    created = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": regulation_id, "answers": PASSING},
        headers=owner,
    )
    check_id = created.json()["check_id"]
    assert client.get(f"/api/v1/eligibility/checks/{check_id}", headers=owner).status_code == 200
    assert client.get(f"/api/v1/eligibility/checks/{check_id}", headers=other).status_code == 404

    other_list = client.get("/api/v1/eligibility/checks", headers=other)
    assert other_list.status_code == 200
    assert other_list.json()["checks"] == []

    officer = role_header(client, session_factory, Role.OFFICER)
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    assert client.get(f"/api/v1/eligibility/checks/{check_id}", headers=officer).status_code == 200
    assert client.get(f"/api/v1/eligibility/checks/{check_id}", headers=admin).status_code == 200


def test_cannot_use_another_citizens_appointment(client, session_factory):
    regulation_id = add_regulation(session_factory)
    owner = citizen_header(client, "appt-owner@example.com")
    other = citizen_header(client, "appt-other@example.com")
    booked = client.post(
        "/api/v1/queue/appointments",
        json={
            "service_type": "Income Certificate",
            "appointment_date": booking_slot(),
        },
        headers=owner,
    )
    appointment_id = booked.json()["appointment_id"]
    response = client.post(
        "/api/v1/eligibility/check",
        json={
            "regulation_id": regulation_id,
            "appointment_id": appointment_id,
            "answers": PASSING,
        },
        headers=other,
    )
    assert response.status_code == 404
    own = client.post(
        "/api/v1/eligibility/check",
        json={
            "regulation_id": regulation_id,
            "appointment_id": appointment_id,
            "answers": PASSING,
        },
        headers=owner,
    )
    assert own.status_code == 201
    assert own.json()["appointment_id"] == appointment_id
    rows = stored_checks(session_factory)
    assert rows[0].appointment_id == appointment_id


def test_unauthenticated_check_rejected(client, session_factory):
    regulation_id = add_regulation(session_factory)
    response = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": regulation_id, "answers": PASSING},
    )
    assert response.status_code == 401


def test_eligibility_warning_does_not_cancel_appointment(client, session_factory):
    regulation_id = add_regulation(session_factory)
    headers = citizen_header(client, "keep-appt@example.com")
    booked = client.post(
        "/api/v1/queue/appointments",
        json={
            "service_type": "Income Certificate",
            "appointment_date": booking_slot(),
        },
        headers=headers,
    )
    appointment_id = booked.json()["appointment_id"]
    answers = dict(PASSING)
    answers["annual_household_income"] = 500000
    check = client.post(
        "/api/v1/eligibility/check",
        json={
            "regulation_id": regulation_id,
            "appointment_id": appointment_id,
            "answers": answers,
        },
        headers=headers,
    )
    assert check.json()["result"] == "potentially_ineligible"
    still = client.get(
        f"/api/v1/queue/appointments/{appointment_id}", headers=headers
    )
    assert still.status_code == 200
    assert still.json()["status"] == "scheduled"


def test_module_status_is_available(client):
    response = client.get("/api/v1/eligibility/status")
    assert response.status_code == 200
    assert response.json()["status"] == "available"


def test_patched_regulation_one_enables_automatic_eligibility_paths(
    client, session_factory
):
    """Ingested rows can have null structured fields until an admin PATCHes them."""
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    created = client.post(
        "/api/v1/regulations",
        json={
            "scheme_name": "Example Income Certificate Scheme",
            "department": "Revenue",
            "circular_reference": "EXAMPLE/CIRC/2026/01",
        },
        headers=admin,
    )
    assert created.status_code == 201
    assert created.json()["regulation_id"] == 1
    assert created.json()["eligibility_criteria"] is None
    assert created.json()["required_documents"] is None

    patched = client.patch(
        "/api/v1/regulations/1",
        json={
            "eligibility_criteria": SAMPLE_CRITERIA,
            "required_documents": SAMPLE_DOCUMENTS,
        },
        headers=admin,
    )
    assert patched.status_code == 200
    assert patched.json()["scheme_name"] == "Example Income Certificate Scheme"
    assert patched.json()["department"] == "Revenue"
    assert patched.json()["circular_reference"] == "EXAMPLE/CIRC/2026/01"
    assert patched.json()["eligibility_criteria"] == SAMPLE_CRITERIA
    assert patched.json()["required_documents"] == SAMPLE_DOCUMENTS

    questions = client.get(
        "/api/v1/eligibility/questionnaire/1", headers=admin
    ).json()
    fields = {item["field_name"] for item in questions["questions"]}
    assert fields == {
        "annual_household_income",
        "resident_of_district_at_least_one_year",
        "holds_income_certificate_this_year",
    }
    assert "advisory" in questions["advisory_notice"].lower()

    citizen = citizen_header(client, "reg1-elig@example.com")
    for document_type in ("Identity Proof", "Residence Proof", "Income Proof"):
        add_document(session_factory, "reg1-elig@example.com", document_type)

    eligible = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": 1, "answers": PASSING},
        headers=citizen,
    )
    assert eligible.status_code == 201, eligible.text
    assert eligible.json()["result"] == "eligible"
    assert eligible.json()["warning_issued"] is False
    assert eligible.json()["missing_documents"] == []

    failing = dict(PASSING)
    failing["annual_household_income"] = 250000
    ineligible = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": 1, "answers": failing},
        headers=citizen,
    )
    assert ineligible.status_code == 201
    assert ineligible.json()["result"] == "potentially_ineligible"

    booked = client.post(
        "/api/v1/queue/appointments",
        json={
            "service_type": "Income Certificate",
            "appointment_date": booking_slot(),
        },
        headers=citizen,
    )
    assert booked.status_code == 201

    ambiguous = client.post(
        "/api/v1/regulations",
        json={
            "scheme_name": "Ambiguous Scheme",
            "department": "Revenue",
            "eligibility_criteria": "Applicants must be residents of the district.",
        },
        headers=admin,
    )
    assert ambiguous.status_code == 201
    review = client.post(
        "/api/v1/eligibility/check",
        json={"regulation_id": ambiguous.json()["regulation_id"], "answers": {}},
        headers=citizen,
    )
    assert review.status_code == 201
    assert review.json()["result"] == "manual_review"
