"""Business logic for the Proactive Eligibility Nudge.

Will call ai_modules.eligibility_nudge once that module is built.
"""

from backend.schemas.common import MessageResponse


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Proactive Eligibility Nudge",
        status="not_implemented",
        message="Scheme matching and nudge generation will be added later.",
    )
