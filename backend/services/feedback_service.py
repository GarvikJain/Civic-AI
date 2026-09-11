"""Business logic for Citizen Feedback Sentiment Analysis.

Will call ai_modules.feedback_sentiment once that module is built.
"""

from backend.schemas.common import MessageResponse


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Citizen Feedback Sentiment Analysis",
        status="not_implemented",
        message="The sentiment classifier will be added later.",
    )
