"""Pydantic schemas for document verification.

No schema exposes a filesystem path or the raw document text.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentRead(BaseModel):
    """An uploaded document and its verification state."""

    model_config = ConfigDict(from_attributes=True)

    document_id: int
    citizen_id: int
    regulation_id: int | None = None
    document_type: str
    upload_date: datetime
    ocr_status: str
    verification_status: str
    rejection_reason: str | None = None
    # Fields read off the document, if any were found.
    extracted_fields: dict[str, str] = Field(default_factory=dict)
    reviewed_by_user_id: int | None = None
    reviewed_at: datetime | None = None
    reviewer_name: str | None = None


class DocumentList(BaseModel):
    """A citizen's documents."""

    documents: list[DocumentRead] = Field(default_factory=list)


class DocumentReviewDecision(BaseModel):
    """An officer's reason for rejecting a document."""

    reason: str = Field(min_length=3, max_length=500)


class DocumentApproval(BaseModel):
    """An officer's optional note when approving a document."""

    note: str | None = Field(default=None, max_length=500)
