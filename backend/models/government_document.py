"""GovernmentDocument entity.

A document uploaded by a citizen, checked by the document verification module.
ERD fields: DocumentID, CitizenID, RegulationID, DocumentType, UploadDate,
OCRStatus, VerificationStatus, RejectionReason.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.citizen import Citizen
    from backend.models.regulation import Regulation


class GovernmentDocument(Base):
    __tablename__ = "government_documents"

    document_id: Mapped[int] = mapped_column(primary_key=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.citizen_id"))
    # A document can be uploaded without being tied to a scheme yet.
    regulation_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulations.regulation_id")
    )
    document_type: Mapped[str] = mapped_column(String(120))
    upload_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Set by the OCR step: pending / completed / failed.
    ocr_status: Mapped[str] = mapped_column(String(20), default="pending")
    # Set by the verification step:
    # pending / processing / verified / rejected / needs_review.
    verification_status: Mapped[str] = mapped_column(String(20), default="pending")
    # Why a document was rejected, or why it needs review. Always the text of a
    # rule that actually failed, or the officer's rejection reason.
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    # Final officer review (needs_review → verified/rejected). Not used for
    # automated decisions. Identity is User.id, not Officer.officer_id.
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # The server-generated file name inside the documents directory. The
    # citizen's original file name is never used, and this is never returned by
    # the API, so no filesystem path is exposed.
    stored_filename: Mapped[str | None] = mapped_column(String(120))
    # Fields found by OCR, stored as JSON text so SQLite needs no extra type.
    extracted_data: Mapped[str | None] = mapped_column(Text)

    citizen: Mapped["Citizen"] = relationship(back_populates="documents")
    regulation: Mapped["Regulation | None"] = relationship(back_populates="documents")

    def __repr__(self) -> str:
        return f"<GovernmentDocument {self.document_id} {self.document_type}>"
