"""EligibilityCheck entity.

The result of checking whether a citizen qualifies for a scheme.
ERD fields: CheckID, CitizenID, AppointmentID, RegulationID, Result,
MissingDocuments, WarningIssued.

Result values used by Phase 7:
    eligible
    potentially_ineligible
    manual_review

The check is advisory. A negative or review result does not block
appointments or document upload.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.appointment import Appointment
    from backend.models.citizen import Citizen
    from backend.models.regulation import Regulation


class EligibilityCheck(Base):
    __tablename__ = "eligibility_checks"

    check_id: Mapped[int] = mapped_column(primary_key=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.citizen_id"))
    # The proactive nudge module checks eligibility before any appointment
    # exists, so this can be empty.
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.appointment_id")
    )
    regulation_id: Mapped[int] = mapped_column(ForeignKey("regulations.regulation_id"))
    # eligible / potentially_ineligible / manual_review
    result: Mapped[str] = mapped_column(String(40))
    missing_documents: Mapped[str | None] = mapped_column(Text)
    warning_issued: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    citizen: Mapped["Citizen"] = relationship(back_populates="eligibility_checks")
    appointment: Mapped["Appointment | None"] = relationship(
        back_populates="eligibility_checks"
    )
    regulation: Mapped["Regulation"] = relationship(back_populates="eligibility_checks")

    def __repr__(self) -> str:
        return f"<EligibilityCheck {self.check_id} {self.result}>"
