"""Document OCR and verification states.

OCR status and verification status are deliberately separate: text extraction
succeeding says nothing about whether the document satisfies the rules, so
ocr_status="completed" with verification_status="rejected" is a normal result.
"""

from enum import Enum


class OcrStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    VERIFIED = "verified"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
