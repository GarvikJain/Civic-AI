"""Business logic for Citizen Feedback Sentiment Analysis.

Sentiment and urgency are produced by the local analyzer in
ai_modules.feedback_sentiment. Comments are never sent to Groq or any other
external API. Escalation is derived from those labels and is not stored.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ai_modules.feedback_sentiment.analyzer import analyze_feedback, escalation_required
from ai_modules.feedback_sentiment.sentiment import SENTIMENT_NEGATIVE
from ai_modules.feedback_sentiment.urgency import URGENCY_HIGH
from backend.core.roles import Role
from backend.models.appointment import Appointment
from backend.models.feedback import Feedback
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.feedback import FeedbackRead
from backend.services import citizen_service, queue_service


class FeedbackAppointmentNotFoundError(Exception):
    """The appointment does not exist, or this caller may not use it."""


class FeedbackNotFoundError(Exception):
    """The feedback does not exist, or this caller may not see it."""


class FeedbackNotAllowedError(Exception):
    """The appointment is not ready for feedback (not completed)."""


class DuplicateFeedbackError(Exception):
    """This appointment already has feedback."""


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Citizen Feedback Sentiment Analysis",
        status="available",
        message=(
            "Feedback comments are classified locally with a lexicon and "
            "rules. They are never sent to Groq or another external API."
        ),
    )


def to_read_model(row: Feedback) -> FeedbackRead:
    service_type = None
    if row.appointment is not None:
        service_type = row.appointment.service_type
    sentiment = row.sentiment or ""
    urgency = row.urgency or ""
    return FeedbackRead(
        feedback_id=row.feedback_id,
        appointment_id=row.appointment_id,
        citizen_id=row.citizen_id,
        service_type=service_type,
        sentiment=sentiment,
        urgency=urgency,
        escalation_required=escalation_required(sentiment, urgency),
        comments=row.comments or "",
        date_submitted=row.date_submitted,
    )


def _owned_appointment(
    db: Session, citizen_id: int, appointment_id: int
) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None or appointment.citizen_id != citizen_id:
        raise FeedbackAppointmentNotFoundError("Appointment not found.")
    return appointment


def _existing_for_appointment(db: Session, appointment_id: int) -> Feedback | None:
    return db.scalar(
        select(Feedback).where(Feedback.appointment_id == appointment_id)
    )


def submit_feedback(db: Session, user: User, appointment_id: int, comments: str) -> Feedback:
    """Analyse comments locally and store one Feedback row."""
    citizen = citizen_service.get_citizen_for_user(db, user.id)
    appointment = _owned_appointment(db, citizen.citizen_id, appointment_id)
    if appointment.status != queue_service.STATUS_COMPLETED:
        raise FeedbackNotAllowedError(
            "Feedback can only be submitted for a completed appointment."
        )
    if _existing_for_appointment(db, appointment.appointment_id) is not None:
        raise DuplicateFeedbackError(
            "Feedback has already been submitted for this appointment."
        )

    analysis = analyze_feedback(comments)
    row = Feedback(
        citizen_id=citizen.citizen_id,
        appointment_id=appointment.appointment_id,
        sentiment=analysis.sentiment,
        urgency=analysis.urgency,
        comments=comments,
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    loaded = db.scalar(
        select(Feedback)
        .options(joinedload(Feedback.appointment))
        .where(Feedback.feedback_id == row.feedback_id)
    )
    return loaded if loaded is not None else row


def get_visible_feedback(db: Session, user: User, feedback_id: int) -> Feedback:
    row = db.scalar(
        select(Feedback)
        .options(joinedload(Feedback.appointment))
        .where(Feedback.feedback_id == feedback_id)
    )
    if row is None:
        raise FeedbackNotFoundError("Feedback not found.")
    if user.role in (Role.OFFICER.value, Role.ADMINISTRATOR.value):
        return row
    citizen = citizen_service.find_citizen_for_user(db, user.id)
    if citizen is None or row.citizen_id != citizen.citizen_id:
        raise FeedbackNotFoundError("Feedback not found.")
    return row


def list_visible_feedback(db: Session, user: User) -> list[Feedback]:
    query = (
        select(Feedback)
        .options(joinedload(Feedback.appointment))
        .order_by(Feedback.date_submitted.desc(), Feedback.feedback_id.desc())
    )
    if user.role in (Role.OFFICER.value, Role.ADMINISTRATOR.value):
        return list(db.scalars(query).unique().all())
    citizen = citizen_service.get_citizen_for_user(db, user.id)
    return list(
        db.scalars(query.where(Feedback.citizen_id == citizen.citizen_id))
        .unique()
        .all()
    )


def list_flagged_feedback(
    db: Session,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    service_type: str | None = None,
    limit: int | None = None,
) -> list[Feedback]:
    """Negative + high urgency rows for the officer dashboard.

    Escalation is the Phase 8 rule: sentiment == negative AND urgency == high.
    Optional time and service filters are used by the dashboard summary.
    """
    query = (
        select(Feedback)
        .options(joinedload(Feedback.appointment))
        .where(
            Feedback.sentiment == SENTIMENT_NEGATIVE,
            Feedback.urgency == URGENCY_HIGH,
        )
        .order_by(Feedback.date_submitted.desc(), Feedback.feedback_id.desc())
    )
    if since is not None:
        query = query.where(Feedback.date_submitted >= since)
    if until is not None:
        query = query.where(Feedback.date_submitted < until)
    if service_type is not None:
        matching = select(Appointment.appointment_id).where(
            Appointment.service_type == service_type
        )
        query = query.where(Feedback.appointment_id.in_(matching))
    if limit is not None:
        query = query.limit(limit)
    return list(db.scalars(query).unique().all())
