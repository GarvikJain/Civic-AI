"""Business logic for the Regulation RAG Assistant.

The AI work happens in ai_modules.regulation_rag. This module connects it to
the database and the API.
"""

from dataclasses import asdict, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.roles import Role
from backend.models.citizen_query import CitizenQuery
from backend.models.regulation import Regulation
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.regulation import (
    RegulationAnswer,
    RegulationCreate,
    RegulationIngestResult,
)
from backend.services import citizen_service


def create_regulation(db: Session, data: RegulationCreate) -> Regulation:
    """Store a new government scheme."""
    regulation = Regulation(**data.model_dump())
    db.add(regulation)
    db.commit()
    db.refresh(regulation)
    return regulation


def get_rag_pipeline():
    """The shared RAG pipeline.

    Imported lazily and wrapped in a function so that the AI models are only
    touched when they are actually needed, and so tests can replace it.
    """
    from ai_modules.regulation_rag.pipeline import get_pipeline

    return get_pipeline()


def _regulation_records(db: Session) -> list[dict]:
    """Regulation rows as plain dicts, for the knowledge graph."""
    regulations = db.scalars(select(Regulation)).all()
    return [
        {
            "scheme_name": regulation.scheme_name,
            "department": regulation.department,
            "eligibility_criteria": regulation.eligibility_criteria,
            "required_documents": regulation.required_documents,
            "circular_reference": regulation.circular_reference,
        }
        for regulation in regulations
    ]


def refresh_knowledge_graph(db: Session, pipeline=None) -> None:
    """Rebuild the knowledge graph from the regulations in the database."""
    pipeline = pipeline or get_rag_pipeline()
    pipeline.knowledge_graph.refresh(_regulation_records(db))


def answer_citizen_query(db: Session, user: User, query_text: str) -> RegulationAnswer:
    """Run the RAG pipeline for a question and record it.

    The asking citizen is found through User.id -> Citizen.user_id, so the
    request body can never choose whose query this is.
    """
    # Only citizens have a profile to file a query against. Officer and
    # administrator questions are answered but not stored.
    #
    # The profile is resolved before the pipeline runs, so a missing profile
    # fails immediately instead of after an LLM call.
    citizen = None
    if user.role == Role.CITIZEN.value:
        citizen = citizen_service.get_citizen_for_user(db, user.id)

    pipeline = get_rag_pipeline()

    # Build the graph once per process, from the current regulations.
    if pipeline.knowledge_graph.graph is None:
        refresh_knowledge_graph(db, pipeline)

    result = pipeline.answer(query_text)

    if citizen is not None:
        db.add(
            CitizenQuery(
                citizen_id=citizen.citizen_id,
                regulation_id=result.primary_regulation_id,
                query_text=query_text,
                ai_response=result.answer,
            )
        )
        db.commit()

    return RegulationAnswer(
        answer=result.answer,
        citations=[asdict(citation) for citation in result.citations],
        insufficient_evidence=result.insufficient_evidence,
        evidence_count=result.evidence_count,
    )


def ingest_regulations(db: Session) -> RegulationIngestResult:
    """Load the local regulation documents into the vector store.

    Each document's scheme is also stored in the regulations table, so answers
    can cite a real regulation row and the knowledge graph stays in step.
    """
    from ai_modules.regulation_rag.ingestion import load_documents

    pipeline = get_rag_pipeline()
    documents = load_documents(pipeline.config.regulations_dir)

    prepared = []
    for document in documents:
        regulation = db.scalar(
            select(Regulation).where(Regulation.scheme_name == document.scheme_name)
        )
        if regulation is None:
            regulation = Regulation(
                scheme_name=document.scheme_name,
                department=document.department or "Unspecified",
                circular_reference=document.circular_reference,
            )
            db.add(regulation)
            db.commit()
            db.refresh(regulation)
        prepared.append(replace(document, regulation_id=regulation.regulation_id))

    chunks_per_document = pipeline.ingest_documents(prepared)
    refresh_knowledge_graph(db, pipeline)

    return RegulationIngestResult(
        documents=len(prepared),
        chunks=sum(chunks_per_document.values()),
        chunks_per_document=chunks_per_document,
    )


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Regulation RAG Assistant",
        status="available",
        message="Ask a question at POST /api/v1/regulations/query.",
    )
