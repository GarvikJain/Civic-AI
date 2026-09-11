"""Feedback entity.

Feedback a citizen leaves after an appointment, used by the sentiment module.
ERD fields: FeedbackID, CitizenID, AppointmentID, Sentiment, Urgency,
Comments, DateSubmitted.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.appointment import Appointment
    from backend.models.citizen import Citizen


class Feedback(Base):
    __tablename__ = "feedback"

    feedback_id: Mapped[int] = mapped_column(primary_key=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.citizen_id"))
    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.appointment_id")
    )
    # Filled in by the sentiment module: positive / neutral / negative.
    sentiment: Mapped[str | None] = mapped_column(String(20))
    # low / medium / high
    urgency: Mapped[str | None] = mapped_column(String(20))
    comments: Mapped[str | None] = mapped_column(Text)
    date_submitted: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    citizen: Mapped["Citizen"] = relationship(back_populates="feedbacks")
    appointment: Mapped["Appointment"] = relationship(back_populates="feedbacks")

    def __repr__(self) -> str:
        return f"<Feedback {self.feedback_id} {self.sentiment}>"
