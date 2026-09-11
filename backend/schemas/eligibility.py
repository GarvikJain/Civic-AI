"""Pydantic schemas for Proactive Eligibility Nudge.

Request and response models are separate. The client cannot set citizen_id,
result, warning_issued or missing_documents.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EligibilityQuestionRead(BaseModel):
    question_id: str
    field_name: str
    question_text: str
    answer_type: str
    required: bool = True
    options: list[str] = Field(default_factory=list)


class QuestionnaireRead(BaseModel):
    regulation_id: int
    scheme_name: str
    questions: list[EligibilityQuestionRead]
    required_document_types: list[str] = Field(default_factory=list)
    advisory_notice: str
    unsupported_criteria: list[str] = Field(default_factory=list)


class EligibilityCheckRequest(BaseModel):
    """Citizen-controlled fields for an eligibility screening."""

    model_config = ConfigDict(extra="forbid")

    regulation_id: int
    appointment_id: int | None = None
    answers: dict[str, Any] = Field(default_factory=dict)


class EligibilityCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_id: int
    citizen_id: int
    appointment_id: int | None
    regulation_id: int
    result: str
    missing_documents: list[str] = Field(default_factory=list)
    warning_issued: bool
    explanation: str | None = None
    created_at: datetime | None = None
    scheme_name: str | None = None


class EligibilityCheckList(BaseModel):
    checks: list[EligibilityCheckRead] = Field(default_factory=list)
