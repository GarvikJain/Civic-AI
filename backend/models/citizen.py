"""Citizen entity.

A citizen is the person using CivicAI to get a government service. This row is
the citizen's *profile*; logging in is handled by the User row it belongs to.

ERD fields: CitizenID, Name, Email, Phone, Password, Address.
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.appointment import Appointment
    from backend.models.citizen_query import CitizenQuery
    from backend.models.eligibility_check import EligibilityCheck
    from backend.models.feedback import Feedback
    from backend.models.government_document import GovernmentDocument
    from backend.models.user import User


class Citizen(Base):
    __tablename__ = "citizens"

    citizen_id: Mapped[int] = mapped_column(primary_key=True)
    # The login account this profile belongs to. Unique, so a user has at most
    # one citizen profile. This is what decides who owns a citizen's data;
    # email is only contact information.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    # In the ERD the citizen carries a password, but authentication lives on
    # User.hashed_password only. This column is left empty so no credential is
    # stored twice.
    password: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)

    # The login account behind this profile.
    user: Mapped["User"] = relationship(back_populates="citizen")

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
