"""Module 5: Proactive Eligibility Nudge.

Citizens answer a short, server-defined questionnaire. A deterministic rule
engine compares the answers with the selected Regulation. The result is
advisory and never blocks appointment creation or document upload.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from ai_modules.eligibility_nudge.errors import InvalidAnswersError
from backend.api.deps import require_role
from backend.core.roles import Role
from backend.db.session import get_db
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.eligibility import (
    EligibilityCheckList,
    EligibilityCheckRead,
    EligibilityCheckRequest,
    QuestionnaireRead,
)
from backend.services import eligibility_service
from backend.services.citizen_service import CitizenProfileMissingError
from backend.services.eligibility_service import (
    EligibilityAppointmentNotFoundError,
    EligibilityCheckNotFoundError,
    EligibilityRegulationNotFoundError,
)

router = APIRouter(prefix="/eligibility", tags=["eligibility-nudge"])

CitizenUser = Depends(require_role(Role.CITIZEN))
SignedInUser = Depends(
    require_role(Role.CITIZEN, Role.OFFICER, Role.ADMINISTRATOR)
)


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return eligibility_service.get_status()


@router.get(
    "/questionnaire/{regulation_id}",
    response_model=QuestionnaireRead,
)
def get_questionnaire(
    regulation_id: int,
    current_user: User = SignedInUser,
    db: Session = Depends(get_db),
) -> QuestionnaireRead:
    """Server-defined questions for one regulation. No executable rules."""
    try:
        questionnaire = eligibility_service.build_questionnaire(db, regulation_id)
    except EligibilityRegulationNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    return QuestionnaireRead(
        regulation_id=questionnaire.regulation_id or regulation_id,
        scheme_name=questionnaire.scheme_name,
        questions=[question.as_public_dict() for question in questionnaire.questions],
        required_document_types=questionnaire.required_document_types,
        advisory_notice=questionnaire.advisory_notice,
        unsupported_criteria=questionnaire.unsupported_criteria,
    )


@router.post(
    "/check",
    response_model=EligibilityCheckRead,
    status_code=http_status.HTTP_201_CREATED,
)
def submit_check(
    payload: EligibilityCheckRequest,
    current_user: User = CitizenUser,
    db: Session = Depends(get_db),
) -> EligibilityCheckRead:
    """Evaluate answers and store an advisory EligibilityCheck."""
    try:
        check = eligibility_service.run_check(
            db,
            current_user,
            regulation_id=payload.regulation_id,
            answers=payload.answers,
            appointment_id=payload.appointment_id,
        )
    except EligibilityRegulationNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except EligibilityAppointmentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
    except InvalidAnswersError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )
    return eligibility_service.to_read_model(check)


@router.get("/checks", response_model=EligibilityCheckList)
def list_checks(
    current_user: User = SignedInUser, db: Session = Depends(get_db)
) -> EligibilityCheckList:
    """Checks this caller is allowed to see."""
    try:
        rows = eligibility_service.list_visible_checks(db, current_user)
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
    return EligibilityCheckList(
        checks=[eligibility_service.to_read_model(row) for row in rows]
    )


@router.get("/checks/{check_id}", response_model=EligibilityCheckRead)
def get_check(
    check_id: int,
    current_user: User = SignedInUser,
    db: Session = Depends(get_db),
) -> EligibilityCheckRead:
    """One stored check. Citizens only see their own."""
    try:
        check = eligibility_service.get_visible_check(db, current_user, check_id)
    except EligibilityCheckNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    return eligibility_service.to_read_model(check)
