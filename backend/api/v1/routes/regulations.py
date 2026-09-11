"""Module 1: Regulation RAG Assistant.

Answers citizen questions about government regulations using retrieval over a
document collection plus a knowledge graph. Only the route skeleton exists
for now.
"""

from fastapi import APIRouter

from backend.schemas.common import MessageResponse
from backend.services import regulation_service

router = APIRouter(prefix="/regulations", tags=["regulation-rag"])


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return regulation_service.get_status()
