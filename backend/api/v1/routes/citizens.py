"""Citizen-only endpoints.

The citizen dashboard is a signed-in landing response. The six CivicAI
services live on their own routers and Streamlit pages.
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
        status="available",
        message=(
            f"Signed in as {current_user.full_name}. Use the Streamlit pages "
            "for regulation questions, documents, appointments, eligibility "
            "and feedback."
        ),
    )
