"""Citizen-only endpoints.

Citizen services themselves arrive in later phases; for now this file exists so
citizen-role access is wired up and tested.
"""

from fastapi import APIRouter, Depends

from backend.api.deps import require_role
from backend.core.roles import Role
from backend.models.user import User
from backend.schemas.common import MessageResponse

router = APIRouter(prefix="/citizens", tags=["citizens"])


@router.get("/dashboard", response_model=MessageResponse)
def dashboard(
    current_user: User = Depends(require_role(Role.CITIZEN)),
) -> MessageResponse:
    """Citizen home area. Only citizens may open it."""
    return MessageResponse(
        module="Citizen Dashboard",
        status="not_implemented",
        message=f"Signed in as {current_user.email}. Citizen services come later.",
    )
