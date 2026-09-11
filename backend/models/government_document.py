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
    # Set by the OCR step: pending / done / failed.
    ocr_status: Mapped[str] = mapped_column(String(20), default="pending")
    # Set by the verification step: pending / verified / rejected.
    verification_status: Mapped[str] = mapped_column(String(20), default="pending")
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    citizen: Mapped["Citizen"] = relationship(back_populates="documents")
    regulation: Mapped["Regulation | None"] = relationship(back_populates="documents")

    def __repr__(self) -> str:
        return f"<GovernmentDocument {self.document_id} {self.document_type}>"
