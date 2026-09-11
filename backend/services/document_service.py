"""Business logic for Document Verification.

The OCR and rule matching live in ai_modules.document_verification. This module
connects them to the database, enforces citizen ownership and stores the result.

Ownership is always resolved as:

    JWT -> User.id -> Citizen.user_id -> Citizen.citizen_id -> document

Email is never used to decide who owns a document, and the client can never
choose a citizen_id.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ai_modules.document_verification.file_validation import validate_upload
from ai_modules.document_verification.rules import RegulationRules
from ai_modules.document_verification.states import OcrStatus, VerificationStatus
from backend.core.config import settings
from backend.models.citizen import Citizen
from backend.models.government_document import GovernmentDocument
from backend.models.regulation import Regulation
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.document import DocumentRead
from backend.services import citizen_service, document_storage


class DocumentNotFoundError(Exception):
    """The document does not exist, or does not belong to this citizen.

    One error covers both cases on purpose: telling a citizen that someone
    else's document exists would leak information.
    """


class RegulationNotFoundError(Exception):
    """The requested regulation does not exist."""


class DocumentNotReviewableError(Exception):
    """The document is not waiting for officer review, or is already final."""


FINAL_VERIFICATION_STATUSES = frozenset(
    {
        VerificationStatus.VERIFIED.value,
        VerificationStatus.REJECTED.value,
    }
)


def max_upload_bytes() -> int:
    return settings.max_upload_size_mb * 1024 * 1024


def get_verification_pipeline():
    """The shared verification pipeline.

    Wrapped in a function so the tests can replace it and so Tesseract is only
    configured when a document is actually processed.
    """
    from ai_modules.document_verification.pipeline import get_pipeline

    return get_pipeline()


def _load_regulation(db: Session, regulation_id: int | None) -> Regulation | None:
    """Look up a regulation the citizen asked for."""
    if regulation_id is None:
        return None
    regulation = db.get(Regulation, regulation_id)
    if regulation is None:
        raise RegulationNotFoundError(f"Regulation {regulation_id} does not exist.")
    return regulation


def resolve_regulation(
    db: Session, document_type: str, regulation_id: int | None
) -> Regulation | None:
    """Decide which regulation a document should be checked against.

    If the citizen named one, it is used. Otherwise a regulation is only chosen
    when exactly one scheme obviously matches the document type; anything less
    certain returns None, which sends the document to officer review instead of
    being checked against the wrong scheme.
    """
    if regulation_id is not None:
        return _load_regulation(db, regulation_id)

    words = [word for word in document_type.lower().split() if len(word) > 3]
    if not words:
        return None

    matches = [
        regulation
        for regulation in db.scalars(select(Regulation)).all()
        if all(word in regulation.scheme_name.lower() for word in words)
    ]
    return matches[0] if len(matches) == 1 else None


def _regulation_rules(regulation: Regulation | None) -> RegulationRules | None:
    """Convert a database row into the plain record the rules expect."""
    if regulation is None:
        return None
    return RegulationRules(
        regulation_id=regulation.regulation_id,
        scheme_name=regulation.scheme_name,
        department=regulation.department,
        eligibility_criteria=regulation.eligibility_criteria,
        required_documents=regulation.required_documents,
        circular_reference=regulation.circular_reference,
    )


def _store_outcome(
    document: GovernmentDocument, outcome, regulation: Regulation | None
) -> None:
    """Copy a verification outcome onto the document row."""
    document.ocr_status = outcome.ocr_status.value
    document.verification_status = outcome.verification_status.value
    document.rejection_reason = outcome.reason
    document.extracted_data = json.dumps(
        {
            "fields": outcome.fields,
            "applied_rules": outcome.applied_rules,
            "failed_rules": outcome.failed_rules,
            "ocr_method": outcome.ocr_method,
            "ocr_characters": outcome.ocr_characters,
        }
    )
    if regulation is not None:
        document.regulation_id = regulation.regulation_id


def extracted_fields_of(document: GovernmentDocument) -> dict[str, str]:
    """The fields stored for a document, or an empty dict."""
    if not document.extracted_data:
        return {}
    try:
        stored = json.loads(document.extracted_data)
    except ValueError:
        return {}
    fields = stored.get("fields") if isinstance(stored, dict) else None
    return fields if isinstance(fields, dict) else {}


def to_read_model(
    document: GovernmentDocument, db: Session | None = None
) -> DocumentRead:
    """The API view of a document, without any filesystem detail."""
    reviewer_name = None
    if document.reviewed_by_user_id is not None and db is not None:
        reviewer = db.get(User, document.reviewed_by_user_id)
        reviewer_name = reviewer.full_name if reviewer is not None else None
    return DocumentRead(
        document_id=document.document_id,
        citizen_id=document.citizen_id,
        regulation_id=document.regulation_id,
        document_type=document.document_type,
        upload_date=document.upload_date,
        ocr_status=document.ocr_status,
        verification_status=document.verification_status,
        rejection_reason=document.rejection_reason,
        extracted_fields=extracted_fields_of(document),
        reviewed_by_user_id=document.reviewed_by_user_id,
        reviewed_at=document.reviewed_at,
        reviewer_name=reviewer_name,
    )


# --- citizen operations -----------------------------------------------------


def upload_document(
    db: Session,
    user: User,
    filename: str,
    content: bytes,
    document_type: str,
    regulation_id: int | None = None,
) -> DocumentRead:
    """Validate, store and verify a document for the signed-in citizen."""
    citizen = citizen_service.get_citizen_for_user(db, user.id)

    # Raises UnsupportedDocumentError / DocumentTooLargeError for a bad file.
    validated = validate_upload(filename, content, max_bytes=max_upload_bytes())

    # Check the regulation before anything is written to disk.
    regulation = resolve_regulation(db, document_type, regulation_id)

    document_storage.save_document(validated.stored_filename, content)

    document = GovernmentDocument(
        citizen_id=citizen.citizen_id,
        regulation_id=regulation.regulation_id if regulation else None,
        document_type=document_type,
        ocr_status=OcrStatus.PENDING.value,
        verification_status=VerificationStatus.PROCESSING.value,
        stored_filename=validated.stored_filename,
    )
    db.add(document)
    db.flush()

    outcome = get_verification_pipeline().verify(
        content=content,
        kind=validated.kind,
        document_type=document_type,
        citizen_name=citizen.name,
        regulation=_regulation_rules(regulation),
    )
    _store_outcome(document, outcome, regulation)

    db.commit()
    db.refresh(document)
    return to_read_model(document, db)


def get_own_document(db: Session, user: User, document_id: int) -> GovernmentDocument:
    """One of the signed-in citizen's documents.

    Raises DocumentNotFoundError if it belongs to somebody else, so a citizen
    cannot reach another citizen's document by changing the id.
    """
    citizen = citizen_service.get_citizen_for_user(db, user.id)
    document = db.get(GovernmentDocument, document_id)
    if document is None or document.citizen_id != citizen.citizen_id:
        raise DocumentNotFoundError(f"Document {document_id} was not found.")
    return document


def list_own_documents(db: Session, user: User) -> list[GovernmentDocument]:
    """Every document belonging to the signed-in citizen, newest first."""
    citizen = citizen_service.get_citizen_for_user(db, user.id)
    return list(
        db.scalars(
            select(GovernmentDocument)
            .where(GovernmentDocument.citizen_id == citizen.citizen_id)
            .order_by(GovernmentDocument.document_id.desc())
        ).all()
    )


def reverify_own_document(db: Session, user: User, document_id: int) -> DocumentRead:
    """Run verification again on the citizen's stored file."""
    document = get_own_document(db, user, document_id)
    if document.verification_status in FINAL_VERIFICATION_STATUSES:
        raise DocumentNotReviewableError(
            "This document has already been finalized."
        )
    if not document.stored_filename:
        raise DocumentNotFoundError(
            f"The stored file for document {document_id} is no longer available."
        )

    try:
        content = document_storage.read_document(document.stored_filename)
    except (OSError, ValueError):
        raise DocumentNotFoundError(
            f"The stored file for document {document_id} could not be read."
        )

    validated_kind = "pdf" if document.stored_filename.lower().endswith(".pdf") else "image"
    regulation = _load_regulation(db, document.regulation_id)
    citizen = db.get(Citizen, document.citizen_id)

    outcome = get_verification_pipeline().verify(
        content=content,
        kind=validated_kind,
        document_type=document.document_type,
        citizen_name=citizen.name if citizen else None,
        regulation=_regulation_rules(regulation),
    )
    _store_outcome(document, outcome, regulation)
    db.commit()
    db.refresh(document)
    return to_read_model(document, db)


# --- officer operations -----------------------------------------------------


def list_documents_for_review(db: Session) -> list[GovernmentDocument]:
    """Documents an automated check could not decide."""
    return list(
        db.scalars(
            select(GovernmentDocument)
            .where(
                GovernmentDocument.verification_status
                == VerificationStatus.NEEDS_REVIEW.value
            )
            .order_by(GovernmentDocument.document_id)
        ).all()
    )


def _raise_if_not_reviewable(db: Session, document_id: int) -> None:
    document = db.get(GovernmentDocument, document_id)
    if document is None:
        raise DocumentNotFoundError(f"Document {document_id} was not found.")
    if document.verification_status in FINAL_VERIFICATION_STATUSES:
        raise DocumentNotReviewableError("This document has already been finalized.")
    raise DocumentNotReviewableError(
        f"Document {document_id} is not waiting for review "
        f"(status: {document.verification_status})."
    )


def _finalize_review(
    db: Session,
    officer: User,
    document_id: int,
    *,
    status: str,
    rejection_reason: str | None,
) -> GovernmentDocument:
    """Atomically apply a final officer decision.

    The WHERE clause requires needs_review so two concurrent decisions cannot
    both succeed. The winner's user id and timestamp are stored on the row,
    not in OCR JSON.
    """
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(GovernmentDocument)
        .where(
            GovernmentDocument.document_id == document_id,
            GovernmentDocument.verification_status
            == VerificationStatus.NEEDS_REVIEW.value,
        )
        .values(
            verification_status=status,
            rejection_reason=rejection_reason,
            reviewed_by_user_id=officer.id,
            reviewed_at=now,
        )
        .execution_options(synchronize_session="fetch")
    )
    if result.rowcount != 1:
        db.rollback()
        _raise_if_not_reviewable(db, document_id)
    document = db.get(GovernmentDocument, document_id)
    if document is None:
        db.rollback()
        raise DocumentNotFoundError(f"Document {document_id} was not found.")
    db.commit()
    db.refresh(document)
    return document


def approve_document(
    db: Session, officer: User, document_id: int, note: str | None = None
) -> DocumentRead:
    """An officer accepts a document that needed review."""
    del note
    document = _finalize_review(
        db,
        officer,
        document_id,
        status=VerificationStatus.VERIFIED.value,
        rejection_reason=None,
    )
    return to_read_model(document, db)


def reject_document(
    db: Session, officer: User, document_id: int, reason: str
) -> DocumentRead:
    """An officer rejects a document, giving the reason."""
    document = _finalize_review(
        db,
        officer,
        document_id,
        status=VerificationStatus.REJECTED.value,
        rejection_reason=reason,
    )
    return to_read_model(document, db)


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Document Verification",
        status="available",
        message="Upload a document at POST /api/v1/documents/upload.",
    )
