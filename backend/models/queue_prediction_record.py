"""A recorded wait-time prediction for one appointment.

predicted_wait_time is stored when the model runs. actual_wait_time stays
NULL until service genuinely starts. The two values are never copied from
each other.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.appointment import Appointment


class QueuePredictionRecord(Base):
    __tablename__ = "queue_prediction_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.appointment_id"), index=True
    )
    predicted_wait_time: Mapped[float] = mapped_column(Float)
    actual_wait_time: Mapped[float | None] = mapped_column(Float)
    predicted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    actual_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str] = mapped_column(String(40))

    appointment: Mapped["Appointment"] = relationship(
        back_populates="prediction_records"
    )

    def __repr__(self) -> str:
        return (
            f"<QueuePredictionRecord {self.id} appointment={self.appointment_id} "
            f"{self.model_version}>"
        )
