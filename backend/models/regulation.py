"""Regulation entity.

A regulation is a government scheme with its rules and required paperwork.
ERD fields: RegulationID, SchemeName, Department, EligibilityCriteria,
RequiredDocuments, CircularReference.
"""

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.citizen_query import CitizenQuery
    from backend.models.eligibility_check import EligibilityCheck
    from backend.models.government_document import GovernmentDocument


class Regulation(Base):
    __tablename__ = "regulations"

    regulation_id: Mapped[int] = mapped_column(primary_key=True)
    scheme_name: Mapped[str] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(120))
    eligibility_criteria: Mapped[str | None] = mapped_column(Text)
    required_documents: Mapped[str | None] = mapped_column(Text)
    circular_reference: Mapped[str | None] = mapped_column(String(200))

    # One regulation is referenced by many of each of these records.
    documents: Mapped[list["GovernmentDocument"]] = relationship(
        back_populates="regulation"
    )
    queries: Mapped[list["CitizenQuery"]] = relationship(back_populates="regulation")
    eligibility_checks: Mapped[list["EligibilityCheck"]] = relationship(
        back_populates="regulation"
    )

    def __repr__(self) -> str:
        return f"<Regulation {self.regulation_id} {self.scheme_name}>"
