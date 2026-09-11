"""API tests for document verification (Phase 5).

The OCR pipeline is replaced with a stand-in, so these tests never need
Tesseract. Ownership is always checked through User.id -> Citizen.user_id.
"""

import json

import pytest
from sqlalchemy import select

from ai_modules.document_verification.pipeline import VerificationOutcome
from ai_modules.document_verification.states import OcrStatus, VerificationStatus
from backend.core.roles import Role
from backend.models.citizen import Citizen
from backend.models.government_document import GovernmentDocument
from backend.models.regulation import Regulation
from backend.models.user import User
from backend.services import document_service
from tests.factories import add_user, auth_header, citizen_header, role_header
from tests.test_document_verification import jpeg_bytes, pdf_bytes, png_bytes

UPLOAD_URL = "/api/v1/documents/upload"


def verified_outcome(**overrides) -> VerificationOutcome:
    outcome = VerificationOutcome(
        ocr_status=OcrStatus.COMPLETED,
        verification_status=VerificationStatus.VERIFIED,
        fields={"name": "Test Citizen", "income": "1,80,000"},
        applied_rules=["required_field:name"],
        ocr_method="tesseract",
        ocr_characters=80,
    )
    for key, value in overrides.items():
        setattr(outcome, key, value)
    return outcome


def rejected_outcome(reason: str, rule: str) -> VerificationOutcome:
    return verified_outcome(
        verification_status=VerificationStatus.REJECTED,
        reason=reason,
        failed_rules=[rule],
        fields={"name": "Test Citizen"},
    )


def review_outcome(reason: str) -> VerificationOutcome:
    return VerificationOutcome(
        ocr_status=OcrStatus.COMPLETED,
        verification_status=VerificationStatus.NEEDS_REVIEW,
        reason=reason,
        ocr_method="tesseract",
        ocr_characters=40,
    )


class StubPipeline:
    """Stands in for the real OCR + rule-matching pipeline."""

    def __init__(self, outcome: VerificationOutcome | None = None):
        self.outcome = outcome or verified_outcome()
        self.calls: list[dict] = []

    def verify(self, **kwargs):
        self.calls.append(kwargs)
        return self.outcome


@pytest.fixture
def stub_pipeline(monkeypatch, tmp_path):
    """Install a stand-in pipeline and write files into a temporary folder."""
    from backend.core import config as config_module

    monkeypatch.setattr(config_module.settings, "documents_dir", str(tmp_path))
    pipeline = StubPipeline()
    monkeypatch.setattr(document_service, "get_verification_pipeline", lambda: pipeline)
    return pipeline


def add_regulation(session_factory, **kwargs) -> int:
    values = {
        "scheme_name": "Example Income Certificate Scheme",
        "department": "Revenue",
        "eligibility_criteria": "Annual household income is below 2,50,000 rupees.",
        "required_documents": "Income proof, identity proof, residence proof.",
        "circular_reference": "EXAMPLE/CIRC/2026/01",
    }
    values.update(kwargs)
    db = session_factory()
    try:
        regulation = Regulation(**values)
        db.add(regulation)
        db.commit()
        return regulation.regulation_id
    finally:
        db.close()


def upload(
    client,
    headers,
    content: bytes | None = None,
    filename: str = "scan.png",
    document_type: str = "Income Certificate",
    regulation_id: int | None = None,
    content_type: str = "image/png",
):
    data = {"document_type": document_type}
    if regulation_id is not None:
        data["regulation_id"] = str(regulation_id)
    files = {"file": (filename, content if content is not None else png_bytes(), content_type)}
    return client.post(UPLOAD_URL, data=data, files=files, headers=headers)


def stored_documents(session_factory) -> list[GovernmentDocument]:
    db = session_factory()
    try:
        return list(db.scalars(select(GovernmentDocument)).all())
    finally:
        db.close()


# --- uploads ----------------------------------------------------------------


def test_a_citizen_can_upload_a_png(client, session_factory, stub_pipeline):
    headers = citizen_header(client)
    response = upload(client, headers, png_bytes(), "scan.png")
    assert response.status_code == 201
    body = response.json()
    assert body["verification_status"] == "verified"
    assert body["ocr_status"] == "completed"
    assert "stored_filename" not in body
    assert stub_pipeline.calls


def test_a_citizen_can_upload_a_jpg(client, session_factory, stub_pipeline):
    headers = citizen_header(client)
    response = upload(
        client, headers, jpeg_bytes(), "scan.jpg", content_type="image/jpeg"
    )
    assert response.status_code == 201


def test_a_citizen_can_upload_a_pdf(client, session_factory, stub_pipeline):
    headers = citizen_header(client)
    response = upload(
        client, headers, pdf_bytes(), "scan.pdf", content_type="application/pdf"
    )
    assert response.status_code == 201
    assert stub_pipeline.calls[0]["kind"] == "pdf"


def test_an_unsupported_file_is_rejected(client, session_factory, stub_pipeline):
    headers = citizen_header(client)
    response = upload(
        client, headers, b"MZ executable", "payload.exe", content_type="application/octet-stream"
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]
    assert stored_documents(session_factory) == []
    assert stub_pipeline.calls == []


def test_an_oversized_file_is_rejected(client, session_factory, stub_pipeline, monkeypatch):
    from backend.core import config as config_module

    monkeypatch.setattr(config_module.settings, "max_upload_size_mb", 0)
    headers = citizen_header(client)
    response = upload(client, headers, png_bytes(), "scan.png")
    assert response.status_code == 400
    assert "upload limit" in response.json()["detail"]
    assert stored_documents(session_factory) == []


def test_unauthenticated_upload_is_rejected(client, stub_pipeline):
    response = upload(client, headers={})
    assert response.status_code == 401
    assert stub_pipeline.calls == []


def test_an_officer_cannot_upload_a_document(client, session_factory, stub_pipeline):
    headers = role_header(client, session_factory, Role.OFFICER)
    assert upload(client, headers).status_code == 403


# --- ownership --------------------------------------------------------------


def test_the_document_belongs_to_the_signed_in_citizen(
    client, session_factory, stub_pipeline
):
    headers = citizen_header(client, "owner@example.com")
    body = upload(client, headers).json()

    db = session_factory()
    try:
        user = db.scalar(select(User).where(User.email == "owner@example.com"))
        citizen = db.scalar(select(Citizen).where(Citizen.user_id == user.id))
        document = db.get(GovernmentDocument, body["document_id"])
        assert document.citizen_id == citizen.citizen_id
        assert citizen.user_id == user.id
    finally:
        db.close()


def test_a_citizen_can_list_and_fetch_their_own_document(
    client, session_factory, stub_pipeline
):
    headers = citizen_header(client)
    document_id = upload(client, headers).json()["document_id"]

    listed = client.get("/api/v1/documents", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["documents"][0]["document_id"] == document_id

    fetched = client.get(f"/api/v1/documents/{document_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["extracted_fields"]["name"] == "Test Citizen"


def test_a_citizen_cannot_fetch_another_citizens_document(
    client, session_factory, stub_pipeline
):
    owner = citizen_header(client, "owner@example.com")
    document_id = upload(client, owner).json()["document_id"]

    other = citizen_header(client, "other@example.com")
    response = client.get(f"/api/v1/documents/{document_id}", headers=other)
    assert response.status_code == 404
    listed = client.get("/api/v1/documents", headers=other)
    assert listed.json()["documents"] == []


def test_a_citizen_cannot_reverify_another_citizens_document(
    client, session_factory, stub_pipeline
):
    owner = citizen_header(client, "owner@example.com")
    document_id = upload(client, owner).json()["document_id"]

    other = citizen_header(client, "other@example.com")
    response = client.post(f"/api/v1/documents/{document_id}/verify", headers=other)
    assert response.status_code == 404


def test_upload_ignores_a_citizen_id_in_the_form(
    client, session_factory, stub_pipeline
):
    """The form cannot file a document under someone else's name."""
    owner = citizen_header(client, "owner@example.com")
    add_user(session_factory, "other@example.com", Role.CITIZEN)

    db = session_factory()
    try:
        other_user = db.scalar(select(User).where(User.email == "other@example.com"))
        other_id = db.scalar(
            select(Citizen).where(Citizen.user_id == other_user.id)
        ).citizen_id
    finally:
        db.close()

    files = {"file": ("scan.png", png_bytes(), "image/png")}
    data = {"document_type": "Income Certificate", "citizen_id": str(other_id)}
    response = client.post(UPLOAD_URL, data=data, files=files, headers=owner)
    assert response.status_code == 201

    db = session_factory()
    try:
        owner_user = db.scalar(select(User).where(User.email == "owner@example.com"))
        owner_citizen = db.scalar(
            select(Citizen).where(Citizen.user_id == owner_user.id)
        )
        document = db.scalar(select(GovernmentDocument))
        assert document.citizen_id == owner_citizen.citizen_id
        assert document.citizen_id != other_id
    finally:
        db.close()


def test_a_citizen_without_a_profile_gets_a_controlled_error(
    client, session_factory, stub_pipeline
):
    add_user(session_factory, "orphan@example.com", Role.CITIZEN, with_profile=False)
    headers = auth_header(client, "orphan@example.com")
    response = upload(client, headers)
    assert response.status_code == 409
    assert "citizen profile" in response.json()["detail"].lower()
    assert stub_pipeline.calls == []


# --- regulation linking -----------------------------------------------------


def test_a_valid_regulation_id_is_stored(client, session_factory, stub_pipeline):
    regulation_id = add_regulation(session_factory)
    headers = citizen_header(client)
    body = upload(client, headers, regulation_id=regulation_id).json()
    assert body["regulation_id"] == regulation_id


def test_an_invalid_regulation_id_is_rejected(client, session_factory, stub_pipeline):
    headers = citizen_header(client)
    response = upload(client, headers, regulation_id=9999)
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]
    assert stored_documents(session_factory) == []
    assert stub_pipeline.calls == []


def test_an_unknown_scheme_goes_to_officer_review(client, session_factory, stub_pipeline):
    stub_pipeline.outcome = review_outcome(
        "The applicable regulation could not be determined, so the document needs officer review."
    )
    headers = citizen_header(client)
    body = upload(client, headers, document_type="Other").json()
    assert body["verification_status"] == "needs_review"
    assert body["rejection_reason"].startswith("The applicable regulation")


# --- persistence ------------------------------------------------------------


def test_verification_state_and_extracted_fields_persist(
    client, session_factory, stub_pipeline
):
    stub_pipeline.outcome = rejected_outcome(
        "Required income field could not be found on the document.",
        "required_field:income",
    )
    headers = citizen_header(client)
    document_id = upload(client, headers).json()["document_id"]

    db = session_factory()
    try:
        document = db.get(GovernmentDocument, document_id)
        assert document.verification_status == "rejected"
        assert document.ocr_status == "completed"
        assert document.rejection_reason == (
            "Required income field could not be found on the document."
        )
        stored = json.loads(document.extracted_data)
        assert stored["fields"]["name"] == "Test Citizen"
        assert stored["failed_rules"] == ["required_field:income"]
        assert document.stored_filename.endswith(".png")
        assert "/" not in document.stored_filename
    finally:
        db.close()


# --- officer review / RBAC --------------------------------------------------


def test_a_citizen_cannot_open_the_officer_review_queue(
    client, session_factory, stub_pipeline
):
    headers = citizen_header(client)
    upload(client, headers)
    assert client.get("/api/v1/officers/documents/review", headers=headers).status_code == 403
    assert client.post(
        "/api/v1/officers/documents/1/approve", json={}, headers=headers
    ).status_code == 403
    assert client.post(
        "/api/v1/officers/documents/1/reject",
        json={"reason": "Not acceptable"},
        headers=headers,
    ).status_code == 403


def test_an_officer_can_review_approve_and_the_citizen_sees_it(
    client, session_factory, stub_pipeline
):
    stub_pipeline.outcome = review_outcome(
        "Too little text could be read from the document to check it automatically, so it needs officer review."
    )
    citizen = citizen_header(client, "owner@example.com")
    document_id = upload(client, citizen).json()["document_id"]

    officer = role_header(client, session_factory, Role.OFFICER)
    queue = client.get("/api/v1/officers/documents/review", headers=officer)
    assert queue.status_code == 200
    assert queue.json()["documents"][0]["document_id"] == document_id

    approved = client.post(
        f"/api/v1/officers/documents/{document_id}/approve", json={}, headers=officer
    )
    assert approved.status_code == 200
    assert approved.json()["verification_status"] == "verified"
    assert approved.json()["rejection_reason"] is None

    seen = client.get(f"/api/v1/documents/{document_id}", headers=citizen)
    assert seen.json()["verification_status"] == "verified"

    # Once decided, it leaves the queue and cannot be decided again.
    assert client.get("/api/v1/officers/documents/review", headers=officer).json()[
        "documents"
    ] == []
    again = client.post(
        f"/api/v1/officers/documents/{document_id}/approve", json={}, headers=officer
    )
    assert again.status_code == 409


def test_an_officer_can_reject_with_a_reason(client, session_factory, stub_pipeline):
    stub_pipeline.outcome = review_outcome("Needs officer review.")
    citizen = citizen_header(client)
    document_id = upload(client, citizen).json()["document_id"]
    officer = role_header(client, session_factory, Role.OFFICER)

    rejected = client.post(
        f"/api/v1/officers/documents/{document_id}/reject",
        json={"reason": "The scan is unreadable."},
        headers=officer,
    )
    assert rejected.status_code == 200
    assert rejected.json()["verification_status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "The scan is unreadable."


def test_an_administrator_can_review_documents(client, session_factory, stub_pipeline):
    stub_pipeline.outcome = review_outcome("Needs officer review.")
    citizen = citizen_header(client)
    document_id = upload(client, citizen).json()["document_id"]
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)

    queue = client.get("/api/v1/officers/documents/review", headers=admin)
    assert queue.status_code == 200
    assert queue.json()["documents"][0]["document_id"] == document_id

    approved = client.post(
        f"/api/v1/officers/documents/{document_id}/approve", json={}, headers=admin
    )
    assert approved.status_code == 200
    assert approved.json()["verification_status"] == "verified"


def test_the_status_endpoint_stays_public(client):
    response = client.get("/api/v1/documents/status")
    assert response.status_code == 200
    assert response.json()["status"] == "available"


def test_no_email_based_ownership_in_document_code():
    """Document ownership must not be resolved by matching email addresses."""
    from pathlib import Path

    roots = [
        Path("backend/services/document_service.py"),
        Path("backend/services/document_storage.py"),
        Path("backend/api/v1/routes/documents.py"),
        Path("backend/api/v1/routes/officers.py"),
    ]
    for path in roots:
        text = path.read_text(encoding="utf-8")
        assert "Citizen.email" not in text, path
        assert "get_or_create_citizen" not in text, path
