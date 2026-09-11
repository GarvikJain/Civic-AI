"""Module 5: Proactive Eligibility Nudge.

Tells citizens about schemes they are likely eligible for before they ask.
Only the route skeleton exists for now.
"""

from fastapi import APIRouter

from backend.schemas.common import MessageResponse
from backend.services import eligibility_service

router = APIRouter(prefix="/eligibility", tags=["eligibility-nudge"])


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return eligibility_service.get_status()
