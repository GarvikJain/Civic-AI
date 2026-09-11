"""Declarative base class for all SQLAlchemy models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Every model in backend/models inherits from this class."""
