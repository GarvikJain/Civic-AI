"""CitizenQuery entity.

A question asked by a citizen and the answer the RAG assistant gave.
ERD fields: QueryID, CitizenID, RegulationID, QueryText, AIResponse, QueryTime.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.citizen import Citizen
    from backend.models.regulation import Regulation


class CitizenQuery(Base):
    __tablename__ = "citizen_queries"

    query_id: Mapped[int] = mapped_column(primary_key=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.citizen_id"))
    # A general question may not be about one specific scheme.
    regulation_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulations.regulation_id")
    )
    query_text: Mapped[str] = mapped_column(Text)
    # Filled in once the RAG assistant answers.
    ai_response: Mapped[str | None] = mapped_column(Text)
    query_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    citizen: Mapped["Citizen"] = relationship(back_populates="queries")
    regulation: Mapped["Regulation | None"] = relationship(back_populates="queries")

    def __repr__(self) -> str:
        return f"<CitizenQuery {self.query_id}>"
