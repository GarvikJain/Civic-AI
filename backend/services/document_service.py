"""Business logic for Document Verification.

Will call ai_modules.document_verification once that module is built.
"""

from backend.schemas.common import MessageResponse


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Document Verification",
        status="not_implemented",
        message="OCR text extraction and validation rules will be added later.",
    )
