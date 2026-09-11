"""Module 2: Document Verification.

Checks uploaded citizen documents with OCR and rule-based validation. Only the
route skeleton exists for now.
"""

from fastapi import APIRouter

from backend.schemas.common import MessageResponse
from backend.services import document_service

router = APIRouter(prefix="/documents", tags=["document-verification"])


@router.get("/status", response_model=MessageResponse)
def status() -> MessageResponse:
    """Report whether this module is implemented."""
    return document_service.get_status()
