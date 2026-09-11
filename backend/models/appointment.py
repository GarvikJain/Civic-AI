"""Appointment entity.

An appointment is a citizen's booked visit to an office, handled by an officer.
ERD fields: AppointmentID, CitizenID, OfficerID, ServiceType, AppointmentDate,
QueueNumber, PredictedWaitTime, Status.

Lifecycle (status):
    scheduled  — waiting in the queue (counts toward live queue depth)
    in_service — the counter has started serving this citizen (still active)
    completed  — finished (excluded from live queue depth)
    cancelled  — withdrawn (excluded from live queue depth)

Actual wait (stored on QueuePredictionRecord, not invented here):
    service_started_at - queue_joined_at, in minutes
It stays NULL until service genuinely starts. It is never copied from
predicted_wait_time.

queue_joined_at is set when the appointment is created (the citizen enters the
CivicAI queue). service_started_at / service_completed_at are set by officer
status transitions. They are not client-supplied.
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
    from backend.models.queue_prediction_record import QueuePredictionRecord


class Appointment(Base):
    __tablename__ = "appointments"

    appointment_id: Mapped[int] = mapped_column(primary_key=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.citizen_id"))
    # An appointment can be booked before an officer is assigned to it.
    officer_id: Mapped[int | None] = mapped_column(ForeignKey("officers.officer_id"))
    service_type: Mapped[str] = mapped_column(String(120), index=True)
    appointment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    queue_number: Mapped[int | None] = mapped_column(Integer)
    # Filled in by the wait-time prediction service (minutes). Never accepted
    # from the client.
    predicted_wait_time: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)

    # Set by the server when the citizen joins the queue / when service events
    # actually happen. Used to compute actual wait; not part of the original ERD.
    queue_joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    service_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    service_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Parents
    citizen: Mapped["Citizen"] = relationship(back_populates="appointments")
    officer: Mapped["Officer | None"] = relationship(back_populates="appointments")

    # One appointment has many of each of these records.
    eligibility_checks: Mapped[list["EligibilityCheck"]] = relationship(
        back_populates="appointment"
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="appointment"
    )
    prediction_records: Mapped[list["QueuePredictionRecord"]] = relationship(
        back_populates="appointment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Appointment {self.appointment_id} {self.service_type} ({self.status})>"
