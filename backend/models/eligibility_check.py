"""EligibilityCheck entity.

The result of checking whether a citizen qualifies for a scheme.
ERD fields: CheckID, CitizenID, AppointmentID, RegulationID, Result,
MissingDocuments, WarningIssued.
"""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
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
    # eligible / not_eligible / incomplete
    result: Mapped[str] = mapped_column(String(20))
    missing_documents: Mapped[str | None] = mapped_column(Text)
    warning_issued: Mapped[bool] = mapped_column(Boolean, default=False)

    citizen: Mapped["Citizen"] = relationship(back_populates="eligibility_checks")
    appointment: Mapped["Appointment | None"] = relationship(
        back_populates="eligibility_checks"
    )
    regulation: Mapped["Regulation"] = relationship(back_populates="eligibility_checks")

    def __repr__(self) -> str:
        return f"<EligibilityCheck {self.check_id} {self.result}>"
