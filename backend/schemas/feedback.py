"""Pydantic schemas for Citizen Feedback Sentiment Analysis.

The client may send only appointment_id and comments. Sentiment, urgency,
escalation, citizen_id and date_submitted are set on the server.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_COMMENTS_LENGTH = 2000


class FeedbackCreate(BaseModel):
    """Citizen-controlled fields for submitting feedback."""

    model_config = ConfigDict(extra="forbid")

    appointment_id: int = Field(ge=1)
    comments: str = Field(min_length=1, max_length=MAX_COMMENTS_LENGTH)

    @field_validator("comments")
    @classmethod
    def comments_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("comments must not be empty or whitespace")
        return stripped


class FeedbackRead(BaseModel):
    """Stored feedback plus server-derived analysis."""

    model_config = ConfigDict(from_attributes=True)

    feedback_id: int
    appointment_id: int
    citizen_id: int
    service_type: str | None = None
    sentiment: str
    urgency: str
    escalation_required: bool
    comments: str
    date_submitted: datetime


class FeedbackList(BaseModel):
    feedbacks: list[FeedbackRead] = Field(default_factory=list)
