"""Module 6: Citizen Feedback Sentiment Analysis.

Citizens submit comments after a completed appointment. Sentiment and urgency
are classified locally. The client cannot set those labels, citizen_id, or
the submission timestamp.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from backend.api.deps import require_role
from backend.core.roles import Role
from backend.db.session import get_db
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.feedback import FeedbackCreate, FeedbackList, FeedbackRead
from backend.services import feedback_service
from backend.services.citizen_service import CitizenProfileMissingError
from backend.services.feedback_service import (
    DuplicateFeedbackError,
    FeedbackAppointmentNotFoundError,
    FeedbackNotAllowedError,
    FeedbackNotFoundError,
)

router = APIRouter(prefix="/feedback", tags=["feedback-sentiment"])

CitizenUser = Depends(require_role(Role.CITIZEN))
SignedInUser = Depends(
    require_role(Role.CITIZEN, Role.OFFICER, Role.ADMINISTRATOR)
)


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return feedback_service.get_status()


@router.post(
    "",
    response_model=FeedbackRead,
    status_code=http_status.HTTP_201_CREATED,
)
def submit_feedback(
    payload: FeedbackCreate,
    current_user: User = CitizenUser,
    db: Session = Depends(get_db),
) -> FeedbackRead:
    """Store feedback for the caller's own completed appointment."""
    try:
        row = feedback_service.submit_feedback(
            db,
            current_user,
            appointment_id=payload.appointment_id,
            comments=payload.comments,
        )
    except FeedbackAppointmentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except (FeedbackNotAllowedError, DuplicateFeedbackError) as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
    return feedback_service.to_read_model(row)


@router.get("", response_model=FeedbackList)
def list_feedback(
    current_user: User = SignedInUser, db: Session = Depends(get_db)
) -> FeedbackList:
    """Citizens see their own feedback; officers and admins may list all."""
    try:
        rows = feedback_service.list_visible_feedback(db, current_user)
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
    return FeedbackList(
        feedbacks=[feedback_service.to_read_model(row) for row in rows]
    )


@router.get("/{feedback_id}", response_model=FeedbackRead)
def get_feedback(
    feedback_id: int,
    current_user: User = SignedInUser,
    db: Session = Depends(get_db),
) -> FeedbackRead:
    """One stored feedback row the caller is allowed to see."""
    try:
        row = feedback_service.get_visible_feedback(db, current_user, feedback_id)
    except FeedbackNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    return feedback_service.to_read_model(row)
