"""Officer entity.

An officer is the government employee who handles appointments.
ERD fields: OfficerID, Name, Department, Role, Email.

Phase 10 links an officer profile to the login User through user_id
(User.id → Officer.user_id). Email is stored for display but is not used to
decide who handled an appointment.
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.appointment import Appointment
    from backend.models.user import User


class Officer(Base):
    __tablename__ = "officers"

    officer_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(60))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    user: Mapped["User | None"] = relationship(back_populates="officer")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="officer")

    def __repr__(self) -> str:
        return f"<Officer {self.officer_id} {self.name} ({self.department})>"
