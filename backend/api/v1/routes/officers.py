"""Officer endpoints.

Module 4 is the productivity dashboard: SQL aggregations over live CivicAI
records for officer and administrator accounts. Document review and flagged
feedback remain available on the same router.

Officer accounts are recognised by User.role, because Officer profile rows are
not linked to login accounts yet.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
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
from backend.schemas.officer import DashboardSummary
from backend.services import document_service, feedback_service, officer_service
from backend.services.document_service import (
    DocumentNotFoundError,
    DocumentNotReviewableError,
)
from backend.services.officer_service import InvalidDashboardFilterError

router = APIRouter(prefix="/officers", tags=["officer-productivity"])

# Officers review documents; administrators may do the same.
ReviewingUser = Depends(require_role(Role.OFFICER, Role.ADMINISTRATOR))


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return officer_service.get_status()


def _summary_or_422(
    db: Session, period: str, service_type: str | None
) -> DashboardSummary:
    try:
        return officer_service.build_dashboard_summary(
            db, period=period, service_type=service_type
        )
    except InvalidDashboardFilterError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    current_user: User = ReviewingUser,
    db: Session = Depends(get_db),
    period: str = Query(default="all"),
    service_type: str | None = Query(default=None),
) -> DashboardSummary:
    """Aggregated officer analytics. Citizens must not be able to open it."""
    del current_user
    return _summary_or_422(db, period, service_type)


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    current_user: User = ReviewingUser,
    db: Session = Depends(get_db),
    period: str = Query(default="all"),
    service_type: str | None = Query(default=None),
) -> DashboardSummary:
    """Same payload as /dashboard/summary, kept for existing clients."""
    del current_user
    return _summary_or_422(db, period, service_type)


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
    """Negative + high-urgency feedback for the officer dashboard."""
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
