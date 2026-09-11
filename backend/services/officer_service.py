"""Business logic for the Officer Productivity Dashboard.

Will call ai_modules.officer_productivity once that module is built.
"""

from backend.schemas.common import MessageResponse


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Officer Productivity Dashboard",
        status="not_implemented",
        message="Productivity metrics and aggregation will be added later.",
    )
