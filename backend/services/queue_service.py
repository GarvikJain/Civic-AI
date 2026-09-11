"""Business logic for Queue Wait-Time Prediction.

Will call ai_modules.queue_prediction once that module is built.
"""

from backend.schemas.common import MessageResponse


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Queue Wait-Time Prediction",
        status="not_implemented",
        message="The wait-time regression model will be added later.",
    )
