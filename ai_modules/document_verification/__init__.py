"""Document Verification.

Pipeline:
1. Validate the uploaded file (file_validation.py).
2. Read the text with Tesseract, rendering PDF pages when needed
   (ocr_service.py, preprocessing.py).
3. Pull out fields by their printed labels (field_extraction.py).
4. Check the document against its rules and its regulation (rules.py).
5. Decide verified / rejected / needs officer review (pipeline.py).

The decision is fully deterministic. No document text is sent to an LLM.
Tesseract and Pillow are imported only when first used, so importing this
package is cheap and needs nothing installed.
"""

from ai_modules.document_verification.errors import (
    DocumentError,
    DocumentTooLargeError,
    OcrFailedError,
    OcrUnavailableError,
    UnsupportedDocumentError,
)
from ai_modules.document_verification.file_validation import (
    SUPPORTED_EXTENSIONS,
    ValidatedUpload,
    validate_upload,
)
from ai_modules.document_verification.ocr_service import OcrResult, OcrService
from ai_modules.document_verification.pipeline import (
    DocumentVerificationPipeline,
    VerificationOutcome,
    get_pipeline,
    reset_pipeline,
)
from ai_modules.document_verification.rules import (
    SUPPORTED_DOCUMENT_TYPES,
    RegulationRules,
    RuleMatcher,
    normalise_document_type,
)
from ai_modules.document_verification.states import OcrStatus, VerificationStatus

__all__ = [
    "SUPPORTED_DOCUMENT_TYPES",
    "SUPPORTED_EXTENSIONS",
    "DocumentError",
    "DocumentTooLargeError",
    "DocumentVerificationPipeline",
    "OcrFailedError",
    "OcrResult",
    "OcrService",
    "OcrStatus",
    "OcrUnavailableError",
    "RegulationRules",
    "RuleMatcher",
    "UnsupportedDocumentError",
    "ValidatedUpload",
    "VerificationOutcome",
    "VerificationStatus",
    "get_pipeline",
    "normalise_document_type",
    "reset_pipeline",
    "validate_upload",
]
