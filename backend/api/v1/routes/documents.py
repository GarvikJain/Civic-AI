"""Module 2: Document Verification.

Citizens upload a government document; it is validated, read with OCR and
checked against the rules of its regulation. Every endpoint here works on the
signed-in citizen's own documents only.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi import status as http_status
from sqlalchemy.orm import Session

from ai_modules.document_verification.errors import (
    DocumentTooLargeError,
    UnsupportedDocumentError,
)
from backend.api.deps import require_role
from backend.core.roles import Role
from backend.db.session import get_db
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.document import DocumentList, DocumentRead
from backend.services import document_service
from backend.services.citizen_service import CitizenProfileMissingError
from backend.services.document_service import (
    DocumentNotFoundError,
    RegulationNotFoundError,
)

router = APIRouter(prefix="/documents", tags=["document-verification"])

# Only citizens own documents, so every endpoint below requires that role.
CitizenUser = Depends(require_role(Role.CITIZEN))


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return document_service.get_status()


@router.post(
    "/upload", response_model=DocumentRead, status_code=http_status.HTTP_201_CREATED
)
def upload_document(
    file: UploadFile = File(..., description="PNG, JPG or PDF document"),
    document_type: str = Form(..., min_length=2, max_length=120),
    regulation_id: int | None = Form(default=None),
    current_user: User = CitizenUser,
    db: Session = Depends(get_db),
) -> DocumentRead:
    """Upload a document and verify it.

    The document is filed against the signed-in citizen; the request cannot
    choose whose document it is.
    """
    content = file.file.read()
    try:
        return document_service.upload_document(
            db=db,
            user=current_user,
            filename=file.filename or "",
            content=content,
            document_type=document_type,
            regulation_id=regulation_id,
        )
    except (UnsupportedDocumentError, DocumentTooLargeError) as error:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(error)
        )
    except RegulationNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(error)
        )
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )


@router.get("", response_model=DocumentList)
def list_documents(
    current_user: User = CitizenUser, db: Session = Depends(get_db)
) -> DocumentList:
    """Every document belonging to the signed-in citizen."""
    try:
        documents = document_service.list_own_documents(db, current_user)
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
    return DocumentList(
        documents=[document_service.to_read_model(document) for document in documents]
    )


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: int, current_user: User = CitizenUser, db: Session = Depends(get_db)
) -> DocumentRead:
    """One of the signed-in citizen's documents."""
    try:
        document = document_service.get_own_document(db, current_user, document_id)
    except DocumentNotFoundError as error:
        # Another citizen's document is reported as not found, so its
        # existence is not revealed.
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
    return document_service.to_read_model(document)


@router.post("/{document_id}/verify", response_model=DocumentRead)
def verify_document(
    document_id: int, current_user: User = CitizenUser, db: Session = Depends(get_db)
) -> DocumentRead:
    """Run verification again on a document the citizen already uploaded."""
    try:
        return document_service.reverify_own_document(db, current_user, document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
