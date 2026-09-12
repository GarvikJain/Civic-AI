"""Tests for the Regulation RAG API endpoints (Phase 4).

The RAG pipeline is replaced with a stand-in, so these tests never load a
model or call Groq.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from ai_modules.regulation_rag.config import RagConfig
from ai_modules.regulation_rag.errors import LlmUnavailableError
from ai_modules.regulation_rag.pipeline import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    Citation,
    RagAnswer,
)
from backend.core.roles import Role
from backend.models.citizen import Citizen
from backend.models.citizen_query import CitizenQuery
from backend.models.regulation import Regulation
from backend.models.user import User
from backend.services import regulation_service
from tests.factories import add_user, auth_header, citizen_header, role_header

QUERY_URL = "/api/v1/regulations/query"

GROUNDED_ANSWER = RagAnswer(
    answer="Submit proof of identity, residence and income (Section 3).",
    citations=[
        Citation(
            scheme_name="Income Certificate Scheme",
            circular_reference="CIRC/2026/11",
            section="Section 3",
            source="income.txt",
            regulation_id=None,
        )
    ],
    insufficient_evidence=False,
    evidence_count=1,
)


class StubPipeline:
    """Stands in for the real RAG pipeline."""

    def __init__(self, result=GROUNDED_ANSWER, error=None, config=None):
        self.result = result
        self.error = error
        self.config = config or RagConfig()
        self.questions = []
        self.ingested = []
        # A non-None graph means the service does not try to rebuild it.
        self.knowledge_graph = SimpleNamespace(
            graph=object(), refresh=lambda records: None
        )

    def answer(self, query):
        self.questions.append(query)
        if self.error is not None:
            raise self.error
        return self.result

    def ingest_documents(self, documents):
        self.ingested.extend(documents)
        return {document.source: 2 for document in documents}


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Install a stand-in pipeline and hand it to the test."""
    pipeline = StubPipeline()
    monkeypatch.setattr(regulation_service, "get_rag_pipeline", lambda: pipeline)
    return pipeline


def stored_queries(session_factory) -> list[CitizenQuery]:
    db = session_factory()
    try:
        return list(db.scalars(select(CitizenQuery)).all())
    finally:
        db.close()


# --- 11 & 12. authentication ------------------------------------------------


def test_authenticated_citizen_can_ask_a_question(client, stub_pipeline):
    headers = citizen_header(client)
    response = client.post(QUERY_URL, json={"query": "Which documents do I need?"}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Submit proof")
    assert body["insufficient_evidence"] is False
    assert body["citations"][0]["circular_reference"] == "CIRC/2026/11"
    assert stub_pipeline.questions == ["Which documents do I need?"]


def test_unauthenticated_user_cannot_ask_a_question(client, stub_pipeline):
    response = client.post(QUERY_URL, json={"query": "Which documents do I need?"})
    assert response.status_code == 401
    assert stub_pipeline.questions == []


def test_an_invalid_token_cannot_ask_a_question(client, stub_pipeline):
    response = client.post(
        QUERY_URL,
        json={"query": "Which documents do I need?"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401
    assert stub_pipeline.questions == []


def test_officers_may_also_ask_questions(client, session_factory, stub_pipeline):
    headers = role_header(client, session_factory, Role.OFFICER)
    response = client.post(QUERY_URL, json={"query": "What are the rules?"}, headers=headers)
    assert response.status_code == 200


def test_a_too_short_question_is_rejected(client, stub_pipeline):
    headers = citizen_header(client)
    response = client.post(QUERY_URL, json={"query": "a"}, headers=headers)
    assert response.status_code == 422
    assert stub_pipeline.questions == []


# --- 13 & 14. storing the query --------------------------------------------


def test_the_question_and_answer_are_stored(client, session_factory, stub_pipeline):
    headers = citizen_header(client, "asker@example.com")
    client.post(QUERY_URL, json={"query": "Which documents do I need?"}, headers=headers)

    queries = stored_queries(session_factory)
    assert len(queries) == 1
    assert queries[0].query_text == "Which documents do I need?"
    assert queries[0].ai_response.startswith("Submit proof")
    assert queries[0].query_time is not None


def test_the_stored_query_belongs_to_the_signed_in_citizen(
    client, session_factory, stub_pipeline
):
    """Ownership is resolved through User.id -> Citizen.user_id."""
    headers = citizen_header(client, "owner@example.com")
    client.post(QUERY_URL, json={"query": "Which documents do I need?"}, headers=headers)

    db = session_factory()
    try:
        user = db.scalar(select(User).where(User.email == "owner@example.com"))
        citizen = db.scalar(select(Citizen).where(Citizen.user_id == user.id))
        query = db.scalar(select(CitizenQuery))
        assert citizen is not None
        assert query.citizen_id == citizen.citizen_id
    finally:
        db.close()


def test_ownership_ignores_a_citizen_id_in_the_request_body(
    client, session_factory, stub_pipeline
):
    """The body must not be able to file a query under someone else's name."""
    headers = citizen_header(client, "owner@example.com")

    # Another citizen exists, and the request tries to blame them.
    add_user(session_factory, "other@example.com", Role.CITIZEN)
    db = session_factory()
    try:
        other_user = db.scalar(select(User).where(User.email == "other@example.com"))
        other_id = db.scalar(
            select(Citizen).where(Citizen.user_id == other_user.id)
        ).citizen_id
    finally:
        db.close()

    client.post(
        QUERY_URL,
        json={"query": "Which documents do I need?", "citizen_id": other_id},
        headers=headers,
    )

    db = session_factory()
    try:
        owner_user = db.scalar(select(User).where(User.email == "owner@example.com"))
        owner = db.scalar(select(Citizen).where(Citizen.user_id == owner_user.id))
        query = db.scalar(select(CitizenQuery))
        assert query.citizen_id == owner.citizen_id
        assert query.citizen_id != other_id
    finally:
        db.close()


def test_a_citizen_without_a_profile_gets_a_controlled_error(
    client, session_factory, stub_pipeline
):
    """An inconsistent account is reported, not silently repaired."""
    add_user(session_factory, "orphan@example.com", Role.CITIZEN, with_profile=False)
    headers = auth_header(client, "orphan@example.com")

    response = client.post(
        QUERY_URL, json={"query": "Which documents do I need?"}, headers=headers
    )

    assert response.status_code == 409
    assert "citizen profile" in response.json()["detail"].lower()
    # The pipeline is never run for an account we cannot attribute the query to.
    assert stub_pipeline.questions == []
    assert stored_queries(session_factory) == []


def test_a_relevant_regulation_is_linked_when_there_is_one(
    client, session_factory, stub_pipeline
):
    db = session_factory()
    try:
        regulation = Regulation(scheme_name="Income Certificate Scheme", department="Revenue")
        db.add(regulation)
        db.commit()
        regulation_id = regulation.regulation_id
    finally:
        db.close()

    stub_pipeline.result = RagAnswer(
        answer="Proof of income is required (Section 3).",
        citations=[Citation(scheme_name="Income Certificate Scheme", regulation_id=regulation_id)],
        evidence_count=1,
    )

    headers = citizen_header(client)
    client.post(QUERY_URL, json={"query": "Which documents do I need?"}, headers=headers)

    queries = stored_queries(session_factory)
    assert queries[0].regulation_id == regulation_id


def test_officer_questions_are_not_stored_as_citizen_queries(
    client, session_factory, stub_pipeline
):
    """Officers have no citizen profile, so nothing is filed against one."""
    headers = role_header(client, session_factory, Role.OFFICER)
    client.post(QUERY_URL, json={"query": "What are the rules?"}, headers=headers)

    assert stored_queries(session_factory) == []


# --- insufficient evidence and service failures -----------------------------


def test_insufficient_evidence_is_reported_without_citations(
    client, session_factory, stub_pipeline
):
    stub_pipeline.result = RagAnswer(
        answer=INSUFFICIENT_EVIDENCE_MESSAGE, citations=[], insufficient_evidence=True
    )
    headers = citizen_header(client)

    response = client.post(QUERY_URL, json={"query": "What is the moon made of?"}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_evidence"] is True
    assert body["answer"] == INSUFFICIENT_EVIDENCE_MESSAGE
    assert body["citations"] == []
    assert body["evidence_count"] == 0

    # The fallback answer is still recorded against the citizen.
    assert stored_queries(session_factory)[0].ai_response == INSUFFICIENT_EVIDENCE_MESSAGE


def test_a_missing_groq_key_returns_service_unavailable(client, stub_pipeline):
    stub_pipeline.error = LlmUnavailableError("GROQ_API_KEY is not configured.")
    headers = citizen_header(client)

    response = client.post(QUERY_URL, json={"query": "Which documents do I need?"}, headers=headers)

    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]


# --- 16. administrator-only endpoints --------------------------------------

REGULATION = {"scheme_name": "New Scheme", "department": "Revenue"}


def test_creating_a_regulation_is_still_administrator_only(client, session_factory):
    citizen = citizen_header(client)
    assert client.post("/api/v1/regulations", json=REGULATION, headers=citizen).status_code == 403

    officer = role_header(client, session_factory, Role.OFFICER)
    assert client.post("/api/v1/regulations", json=REGULATION, headers=officer).status_code == 403

    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    assert client.post("/api/v1/regulations", json=REGULATION, headers=admin).status_code == 201


def test_ingestion_is_administrator_only(client, session_factory, stub_pipeline):
    citizen = citizen_header(client)
    officer = role_header(client, session_factory, Role.OFFICER)
    assert client.post("/api/v1/regulations/ingest", headers=citizen).status_code == 403
    assert client.post("/api/v1/regulations/ingest", headers=officer).status_code == 403
    assert client.post("/api/v1/regulations/ingest").status_code == 401
    assert stub_pipeline.ingested == []


def test_administrator_can_ingest_local_documents(
    client, session_factory, stub_pipeline, tmp_path
):
    (tmp_path / "income.txt").write_text(
        "scheme_name: Income Certificate Scheme\n"
        "department: Revenue\n"
        "circular_reference: CIRC/2026/11\n"
        "---\n"
        "Section 2. Required Documents\nProof of income is required.\n",
        encoding="utf-8",
    )
    stub_pipeline.config = RagConfig(regulations_dir=tmp_path)
    headers = role_header(client, session_factory, Role.ADMINISTRATOR)

    response = client.post("/api/v1/regulations/ingest", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == 1
    assert body["chunks"] == 2
    assert body["chunks_per_document"] == {"income.txt": 2}

    # The scheme is now a regulation row, and the document knows its id.
    db = session_factory()
    try:
        regulation = db.scalar(
            select(Regulation).where(Regulation.scheme_name == "Income Certificate Scheme")
        )
        assert regulation is not None
        assert regulation.circular_reference == "CIRC/2026/11"
    finally:
        db.close()
    assert stub_pipeline.ingested[0].regulation_id == regulation.regulation_id


def test_the_status_endpoint_stays_public(client):
    response = client.get("/api/v1/regulations/status")
    assert response.status_code == 200
    assert response.json()["status"] == "available"


def test_signed_in_users_can_list_regulations_but_guests_cannot(
    client, session_factory
):
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    created = client.post("/api/v1/regulations", json=REGULATION, headers=admin)
    assert created.status_code == 201
    citizen = citizen_header(client, "reader@example.com")
    officer = role_header(client, session_factory, Role.OFFICER)
    for headers in (citizen, officer, admin):
        response = client.get("/api/v1/regulations", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()[0]["scheme_name"] == REGULATION["scheme_name"]
    assert client.get("/api/v1/regulations").status_code == 401


def test_administrator_can_update_a_regulation(client, session_factory):
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    created = client.post("/api/v1/regulations", json=REGULATION, headers=admin)
    regulation_id = created.json()["regulation_id"]
    response = client.patch(
        f"/api/v1/regulations/{regulation_id}",
        json={
            "eligibility_criteria": "Annual household income is below 2,50,000 rupees.",
            "required_documents": "Proof of identity, proof of residence, proof of income.",
        },
        headers=admin,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["regulation_id"] == regulation_id
    assert body["scheme_name"] == REGULATION["scheme_name"]
    assert body["department"] == REGULATION["department"]
    assert body["eligibility_criteria"].startswith("Annual household income")
    assert "proof of income" in body["required_documents"].lower()

    db = session_factory()
    try:
        stored = db.get(Regulation, regulation_id)
        assert stored.eligibility_criteria == body["eligibility_criteria"]
        assert stored.required_documents == body["required_documents"]
        assert stored.scheme_name == REGULATION["scheme_name"]
    finally:
        db.close()


def test_regulation_update_is_administrator_only(client, session_factory):
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    regulation_id = client.post(
        "/api/v1/regulations", json=REGULATION, headers=admin
    ).json()["regulation_id"]
    payload = {"department": "Transport"}
    citizen = citizen_header(client, "reg-update-citizen@example.com")
    officer = role_header(client, session_factory, Role.OFFICER)
    assert client.patch(
        f"/api/v1/regulations/{regulation_id}", json=payload, headers=citizen
    ).status_code == 403
    assert client.patch(
        f"/api/v1/regulations/{regulation_id}", json=payload, headers=officer
    ).status_code == 403
    assert client.patch(
        f"/api/v1/regulations/{regulation_id}", json=payload
    ).status_code == 401
    stored = client.get("/api/v1/regulations", headers=admin).json()[0]
    assert stored["department"] == "Revenue"


def test_updating_a_missing_regulation_is_404(client, session_factory):
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    response = client.patch(
        "/api/v1/regulations/99999",
        json={"department": "Revenue"},
        headers=admin,
    )
    assert response.status_code == 404


def test_partial_regulation_patch_preserves_omitted_fields(client, session_factory):
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    created = client.post(
        "/api/v1/regulations",
        json={
            "scheme_name": "Kept Scheme",
            "department": "Revenue",
            "eligibility_criteria": "Original criteria",
            "required_documents": "Original documents",
            "circular_reference": "CIRC/KEEP/1",
        },
        headers=admin,
    )
    regulation_id = created.json()["regulation_id"]
    response = client.patch(
        f"/api/v1/regulations/{regulation_id}",
        json={"eligibility_criteria": "Updated criteria only"},
        headers=admin,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scheme_name"] == "Kept Scheme"
    assert body["department"] == "Revenue"
    assert body["required_documents"] == "Original documents"
    assert body["circular_reference"] == "CIRC/KEEP/1"
    assert body["eligibility_criteria"] == "Updated criteria only"


def test_regulation_update_rejects_unknown_body_fields(client, session_factory):
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    regulation_id = client.post(
        "/api/v1/regulations", json=REGULATION, headers=admin
    ).json()["regulation_id"]
    response = client.patch(
        f"/api/v1/regulations/{regulation_id}",
        json={"regulation_id": 99, "department": "Revenue"},
        headers=admin,
    )
    assert response.status_code == 422


def test_frontend_has_admin_regulation_update_section():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[1]
        / "frontend"
        / "pages"
        / "1_Regulation_Assistant.py"
    ).read_text(encoding="utf-8")
    assert "Administrator: register a scheme" in text
    assert "Administrator: update existing regulation" in text
    assert 'role == "administrator"' in text
    assert "patch(" in text
