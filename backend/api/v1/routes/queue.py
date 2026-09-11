"""Module 3: Queue Wait-Time Prediction.

Predicts how long a citizen will wait at a government office. Only the route
skeleton exists for now.
"""

from fastapi import APIRouter

from backend.schemas.common import MessageResponse
from backend.services import queue_service

router = APIRouter(prefix="/queue", tags=["queue-prediction"])


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return queue_service.get_status()
