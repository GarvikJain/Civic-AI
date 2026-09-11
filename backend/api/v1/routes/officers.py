"""Module 4: Officer Productivity Dashboard.

Summarises how many applications each officer handles and how fast. Only the
route skeleton exists for now.
"""

from fastapi import APIRouter, Depends

from backend.api.deps import require_role
from backend.core.roles import Role
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.services import officer_service

router = APIRouter(prefix="/officers", tags=["officer-productivity"])


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return officer_service.get_status()


@router.get("/dashboard", response_model=MessageResponse)
def dashboard(
    current_user: User = Depends(require_role(Role.OFFICER, Role.ADMINISTRATOR)),
) -> MessageResponse:
    """The productivity dashboard. Citizens must not be able to open it."""
    return MessageResponse(
        module="Officer Productivity Dashboard",
        status="not_implemented",
        message=f"Signed in as {current_user.email}. Metrics come later.",
    )
