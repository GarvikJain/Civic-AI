"""Officer endpoints.

Module 4 (the productivity dashboard) is still a placeholder. The document
review endpoints below are the minimal officer workflow added in Phase 5.

Officer accounts are recognised by User.role, because Officer profile rows are
not linked to login accounts yet.
"""

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session

from backend.api.deps import require_role
from backend.core.roles import Role
from backend.db.session import get_db
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.document import (
    DocumentApproval,
    DocumentList,
    DocumentRead,
    DocumentReviewDecision,
)
from backend.schemas.feedback import FeedbackList
from backend.services import document_service, feedback_service, officer_service
from backend.services.document_service import (
    DocumentNotFoundError,
    DocumentNotReviewableError,
)

router = APIRouter(prefix="/officers", tags=["officer-productivity"])

# Officers review documents; administrators may do the same.
ReviewingUser = Depends(require_role(Role.OFFICER, Role.ADMINISTRATOR))


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return officer_service.get_status()


@router.get("/dashboard", response_model=MessageResponse)
def dashboard(current_user: User = ReviewingUser) -> MessageResponse:
    """The productivity dashboard. Citizens must not be able to open it."""
    return MessageResponse(
        module="Officer Productivity Dashboard",
        status="not_implemented",
        message=f"Signed in as {current_user.email}. Metrics come later.",
    )


@router.get("/documents/review", response_model=DocumentList)
def documents_awaiting_review(
    current_user: User = ReviewingUser, db: Session = Depends(get_db)
) -> DocumentList:
    """Documents the automated checks could not decide."""
    documents = document_service.list_documents_for_review(db)
    return DocumentList(
        documents=[document_service.to_read_model(document) for document in documents]
    )


@router.post("/documents/{document_id}/approve", response_model=DocumentRead)
def approve_document(
    document_id: int,
    decision: DocumentApproval | None = None,
    current_user: User = ReviewingUser,
    db: Session = Depends(get_db),
) -> DocumentRead:
    """Accept a document that needed review."""
    try:
        return document_service.approve_document(
            db, current_user, document_id, note=decision.note if decision else None
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except DocumentNotReviewableError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )


@router.get("/feedback/flagged", response_model=FeedbackList)
def flagged_feedback(
    current_user: User = ReviewingUser, db: Session = Depends(get_db)
) -> FeedbackList:
    """Negative + high-urgency feedback for the future productivity dashboard.

    Phase 9 will render these rows. This endpoint only lists them.
    """
    del current_user
    rows = feedback_service.list_flagged_feedback(db)
    return FeedbackList(
        feedbacks=[feedback_service.to_read_model(row) for row in rows]
    )


@router.post("/documents/{document_id}/reject", response_model=DocumentRead)
def reject_document(
    document_id: int,
    decision: DocumentReviewDecision,
    current_user: User = ReviewingUser,
    db: Session = Depends(get_db),
) -> DocumentRead:
    """Reject a document that needed review, with a reason."""
    try:
        return document_service.reject_document(
            db, current_user, document_id, reason=decision.reason
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except DocumentNotReviewableError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
