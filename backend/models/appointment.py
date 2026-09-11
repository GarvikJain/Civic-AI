"""Appointment entity.

An appointment is a citizen's booked visit to an office, handled by an officer.
ERD fields: AppointmentID, CitizenID, OfficerID, ServiceType, AppointmentDate,
QueueNumber, PredictedWaitTime, Status.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.citizen import Citizen
    from backend.models.eligibility_check import EligibilityCheck
    from backend.models.feedback import Feedback
    from backend.models.officer import Officer


class Appointment(Base):
    __tablename__ = "appointments"

    appointment_id: Mapped[int] = mapped_column(primary_key=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.citizen_id"))
    # An appointment can be booked before an officer is assigned to it.
    officer_id: Mapped[int | None] = mapped_column(ForeignKey("officers.officer_id"))
    service_type: Mapped[str] = mapped_column(String(120))
    appointment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    queue_number: Mapped[int | None] = mapped_column(Integer)
    # Filled in later by the wait-time prediction module (minutes).
    predicted_wait_time: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")

    # Parents
    citizen: Mapped["Citizen"] = relationship(back_populates="appointments")
    officer: Mapped["Officer | None"] = relationship(back_populates="appointments")

    # One appointment has many of each of these records.
    eligibility_checks: Mapped[list["EligibilityCheck"]] = relationship(
        back_populates="appointment"
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="appointment")

    def __repr__(self) -> str:
        return f"<Appointment {self.appointment_id} {self.service_type} ({self.status})>"
