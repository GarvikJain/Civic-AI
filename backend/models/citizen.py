"""Citizen entity.

A citizen is the person using CivicAI to get a government service.
ERD fields: CitizenID, Name, Email, Phone, Password, Address.
"""

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.appointment import Appointment
    from backend.models.citizen_query import CitizenQuery
    from backend.models.eligibility_check import EligibilityCheck
    from backend.models.feedback import Feedback
    from backend.models.government_document import GovernmentDocument


class Citizen(Base):
    __tablename__ = "citizens"

    citizen_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    password: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)

    # One citizen has many of each of these records.
    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="citizen", cascade="all, delete-orphan"
    )
    documents: Mapped[list["GovernmentDocument"]] = relationship(
        back_populates="citizen", cascade="all, delete-orphan"
    )
    queries: Mapped[list["CitizenQuery"]] = relationship(
        back_populates="citizen", cascade="all, delete-orphan"
    )
    eligibility_checks: Mapped[list["EligibilityCheck"]] = relationship(
        back_populates="citizen", cascade="all, delete-orphan"
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="citizen", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Citizen {self.citizen_id} {self.name}>"
