"""Business logic for the Regulation RAG Assistant.

Will call ai_modules.regulation_rag once that module is built.
"""

from sqlalchemy.orm import Session

from backend.models.regulation import Regulation
from backend.schemas.common import MessageResponse
from backend.schemas.regulation import RegulationCreate


def create_regulation(db: Session, data: RegulationCreate) -> Regulation:
    """Store a new government scheme."""
    regulation = Regulation(**data.model_dump())
    db.add(regulation)
    db.commit()
    db.refresh(regulation)
    return regulation


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Regulation RAG Assistant",
        status="not_implemented",
        message="Retrieval, reranking and LLM answering will be added later.",
    )
