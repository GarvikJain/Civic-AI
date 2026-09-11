"""Business logic for the Proactive Eligibility Nudge.

The rule engine in ai_modules.eligibility_nudge decides the result. This
module loads the Regulation, resolves the citizen through User.id ->
Citizen.user_id, checks verified documents, and stores EligibilityCheck rows.

Citizen answers are not sent to Groq. A warning never cancels an appointment.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ai_modules.document_verification.states import VerificationStatus
from ai_modules.eligibility_nudge.documents import missing_required_documents
from ai_modules.eligibility_nudge.errors import InvalidAnswersError
from ai_modules.eligibility_nudge.evaluator import evaluate_rules, validate_answers
from ai_modules.eligibility_nudge.questionnaire import Questionnaire
from ai_modules.eligibility_nudge.rules import (
    extract_programme,
    questionnaire_for_programme,
)
from backend.core.roles import Role
from backend.models.appointment import Appointment
from backend.models.eligibility_check import EligibilityCheck
from backend.models.government_document import GovernmentDocument
from backend.models.regulation import Regulation
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.eligibility import EligibilityCheckRead
from backend.services import citizen_service


class EligibilityRegulationNotFoundError(Exception):
    """The requested regulation does not exist."""


class EligibilityCheckNotFoundError(Exception):
    """The check does not exist, or this caller may not see it."""


class EligibilityAppointmentNotFoundError(Exception):
    """The appointment does not exist, or does not belong to this citizen."""


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Proactive Eligibility Nudge",
        status="available",
        message=(
            "Eligibility Nudge is an advisory screening feature. It does not "
            "constitute a final government eligibility decision."
        ),
    )


def _load_regulation(db: Session, regulation_id: int) -> Regulation:
    regulation = db.get(Regulation, regulation_id)
    if regulation is None:
        raise EligibilityRegulationNotFoundError("Regulation not found.")
    return regulation


def build_questionnaire(db: Session, regulation_id: int) -> Questionnaire:
    regulation = _load_regulation(db, regulation_id)
    programme = extract_programme(
        eligibility_criteria=regulation.eligibility_criteria,
        required_documents=regulation.required_documents,
        scheme_name=regulation.scheme_name,
        regulation_id=regulation.regulation_id,
    )
    return questionnaire_for_programme(
        programme,
        regulation_id=regulation.regulation_id,
        scheme_name=regulation.scheme_name,
    )


def _verified_document_types(db: Session, citizen_id: int) -> list[str]:
    rows = db.scalars(
        select(GovernmentDocument).where(
            GovernmentDocument.citizen_id == citizen_id,
            GovernmentDocument.verification_status == VerificationStatus.VERIFIED.value,
        )
    ).all()
    return [row.document_type for row in rows]


def _split_missing(stored: str | None) -> list[str]:
    if not stored:
        return []
    return [part.strip() for part in stored.split(",") if part.strip()]


def to_read_model(check: EligibilityCheck) -> EligibilityCheckRead:
    scheme = check.regulation.scheme_name if check.regulation is not None else None
    return EligibilityCheckRead(
        check_id=check.check_id,
        citizen_id=check.citizen_id,
        appointment_id=check.appointment_id,
        regulation_id=check.regulation_id,
        result=check.result,
        missing_documents=_split_missing(check.missing_documents),
        warning_issued=check.warning_issued,
        explanation=check.explanation,
        created_at=check.created_at,
        scheme_name=scheme,
    )


def _owned_appointment(
    db: Session, user: User, appointment_id: int, citizen_id: int
) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise EligibilityAppointmentNotFoundError("Appointment not found.")
    if user.role in (Role.OFFICER.value, Role.ADMINISTRATOR.value):
        return appointment
    if appointment.citizen_id != citizen_id:
        raise EligibilityAppointmentNotFoundError("Appointment not found.")
    return appointment


def run_check(
    db: Session,
    user: User,
    *,
    regulation_id: int,
    answers: dict,
    appointment_id: int | None = None,
) -> EligibilityCheck:
    """Evaluate answers and persist one EligibilityCheck. No Groq call."""
    citizen = citizen_service.get_citizen_for_user(db, user.id)
    regulation = _load_regulation(db, regulation_id)
    linked_appointment_id = None
    if appointment_id is not None:
        appointment = _owned_appointment(
            db, user, appointment_id, citizen.citizen_id
        )
        linked_appointment_id = appointment.appointment_id

    programme = extract_programme(
        eligibility_criteria=regulation.eligibility_criteria,
        required_documents=regulation.required_documents,
        scheme_name=regulation.scheme_name,
        regulation_id=regulation.regulation_id,
    )
    questionnaire = questionnaire_for_programme(
        programme,
        regulation_id=regulation.regulation_id,
        scheme_name=regulation.scheme_name,
    )
    coerced = validate_answers(questionnaire, answers)
    missing = missing_required_documents(
        list(programme.required_document_types),
        _verified_document_types(db, citizen.citizen_id),
    )
    evaluation = evaluate_rules(programme, coerced, missing_documents=missing)

    stored_missing = ", ".join(evaluation.missing_documents) or None
    check = EligibilityCheck(
        citizen_id=citizen.citizen_id,
        appointment_id=linked_appointment_id,
        regulation_id=regulation.regulation_id,
        result=evaluation.result,
        missing_documents=stored_missing,
        warning_issued=evaluation.warning_issued,
        explanation=evaluation.explanation,
    )
    try:
        db.add(check)
        db.commit()
        db.refresh(check)
    except Exception:
        db.rollback()
        raise
    return check


def get_visible_check(
    db: Session, user: User, check_id: int
) -> EligibilityCheck:
    check = db.scalar(
        select(EligibilityCheck)
        .options(joinedload(EligibilityCheck.regulation))
        .where(EligibilityCheck.check_id == check_id)
    )
    if check is None:
        raise EligibilityCheckNotFoundError("Eligibility check not found.")
    if user.role in (Role.OFFICER.value, Role.ADMINISTRATOR.value):
        return check
    citizen = citizen_service.find_citizen_for_user(db, user.id)
    if citizen is None or check.citizen_id != citizen.citizen_id:
        raise EligibilityCheckNotFoundError("Eligibility check not found.")
    return check


def list_visible_checks(db: Session, user: User) -> list[EligibilityCheck]:
    query = (
        select(EligibilityCheck)
        .options(joinedload(EligibilityCheck.regulation))
        .order_by(EligibilityCheck.check_id.desc())
    )
    if user.role in (Role.OFFICER.value, Role.ADMINISTRATOR.value):
        return list(db.scalars(query).unique().all())
    citizen = citizen_service.get_citizen_for_user(db, user.id)
    return list(
        db.scalars(
            query.where(EligibilityCheck.citizen_id == citizen.citizen_id)
        )
        .unique()
        .all()
    )
