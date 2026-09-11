"""Module 6: Citizen Feedback Sentiment Analysis.

Classifies citizen feedback so offices can see where service is failing. Only
the route skeleton exists for now.
"""

from fastapi import APIRouter

from backend.schemas.common import MessageResponse
from backend.services import feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback-sentiment"])


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return feedback_service.get_status()
