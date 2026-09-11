"""Module 1: Regulation RAG Assistant.

Answers citizen questions about government regulations using retrieval over a
document collection plus a knowledge graph. Only the route skeleton exists
for now.
"""

from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy.orm import Session

from backend.api.deps import require_role
from backend.core.roles import Role
from backend.db.session import get_db
from backend.models.regulation import Regulation
from backend.schemas.common import MessageResponse
from backend.schemas.regulation import RegulationCreate, RegulationRead
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
