"""Officer entity.

An officer is the government employee who handles appointments.
ERD fields: OfficerID, Name, Department, Role, Email.
"""

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.appointment import Appointment


class Officer(Base):
    __tablename__ = "officers"

    officer_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(60))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    # One officer handles many appointments.
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="officer")

    def __repr__(self) -> str:
        return f"<Officer {self.officer_id} {self.name} ({self.department})>"
