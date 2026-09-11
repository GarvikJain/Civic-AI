"""Module 4: Officer Productivity Dashboard.

Summarises how many applications each officer handles and how fast. Only the
route skeleton exists for now.
"""

from fastapi import APIRouter

from backend.schemas.common import MessageResponse
from backend.services import officer_service

router = APIRouter(prefix="/officers", tags=["officer-productivity"])


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return officer_service.get_status()
