"""User model.

This is the single authentication identity for CivicAI. The role column decides
which parts of the platform a user may reach: citizen, officer or administrator.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.roles import Role
from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.citizen import Citizen
    from backend.models.officer import Officer


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.CITIZEN.value)
    # A disabled account keeps its history but can no longer log in.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # A user with role "citizen" has exactly one citizen profile. Officers and
    # administrators have an officer profile used for appointment attribution.
    citizen: Mapped["Citizen | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    officer: Mapped["Officer | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
