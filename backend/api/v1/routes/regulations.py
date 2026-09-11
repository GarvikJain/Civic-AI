"""Module 1: Regulation RAG Assistant.

Citizens ask questions in natural language; the answer is generated only from
the official regulations that have been ingested, with citations.
"""

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session

from ai_modules.regulation_rag.errors import RagError
from backend.api.deps import get_current_user, require_role
from backend.core.roles import Role
from backend.db.session import get_db
from backend.models.regulation import Regulation
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.regulation import (
    RegulationAnswer,
    RegulationCreate,
    RegulationIngestResult,
    RegulationQuery,
    RegulationRead,
)
from backend.services import regulation_service

router = APIRouter(prefix="/regulations", tags=["regulation-rag"])


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return regulation_service.get_status()


@router.post(
    "",
    response_model=RegulationRead,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(Role.ADMINISTRATOR))],
)
def create_regulation(
    data: RegulationCreate, db: Session = Depends(get_db)
) -> Regulation:
    """Register a government scheme. Administrators only."""
    return regulation_service.create_regulation(db, data)


@router.post("/query", response_model=RegulationAnswer)
def query_regulations(
    data: RegulationQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RegulationAnswer:
    """Answer a question from the official regulations.

    The query is recorded against the signed-in citizen; the request body
    cannot choose whose query it is.
    """
    try:
        return regulation_service.answer_citizen_query(db, current_user, data.query)
    except RagError as error:
        # A missing model or API key must not turn into a guessed answer.
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        )


@router.post(
    "/ingest",
    response_model=RegulationIngestResult,
    dependencies=[Depends(require_role(Role.ADMINISTRATOR))],
)
def ingest_regulations(db: Session = Depends(get_db)) -> RegulationIngestResult:
    """Load the regulation documents in data/regulations/. Administrators only."""
    try:
        return regulation_service.ingest_regulations(db)
    except RagError as error:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        )
