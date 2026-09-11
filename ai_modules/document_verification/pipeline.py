"""The document verification pipeline.

    uploaded file
      -> OCR (image, or PDF text/render)
      -> extract fields by their printed labels
      -> check the rules for this document type and its regulation
      -> verified / rejected with the exact reason / needs officer review

A document is only marked verified when text was read, the applicable
regulation is known, rules exist for its type, and every rule passed. Anything
less goes to officer review rather than being verified or rejected on a guess.
Nothing is sent to an LLM.
"""

from dataclasses import dataclass, field
from functools import lru_cache

from ai_modules.document_verification.field_extraction import extract_fields
from ai_modules.document_verification.ocr_service import OcrResult, OcrService
from ai_modules.document_verification.rules import (
    DocumentContext,
    RegulationRules,
    RuleMatcher,
    normalise_document_type,
    rules_for,
)
from ai_modules.document_verification.states import OcrStatus, VerificationStatus

# Below this many characters the text is treated as unreadable rather than as
# a document that simply fails its rules.
MIN_USEFUL_TEXT_LENGTH = 25


@dataclass
class VerificationOutcome:
    """The result for one document."""

    ocr_status: OcrStatus
    verification_status: VerificationStatus
    reason: str | None = None
    fields: dict[str, str] = field(default_factory=dict)
    applied_rules: list[str] = field(default_factory=list)
    failed_rules: list[str] = field(default_factory=list)
    ocr_method: str = ""
    ocr_characters: int = 0
    ocr_error: str | None = None

    @property
    def needs_review(self) -> bool:
        return self.verification_status is VerificationStatus.NEEDS_REVIEW


class DocumentVerificationPipeline:
    """Runs OCR, extraction and rule matching for an uploaded document."""

    def __init__(
        self,
        ocr_service: OcrService | None = None,
        matcher: RuleMatcher | None = None,
        min_text_length: int = MIN_USEFUL_TEXT_LENGTH,
    ) -> None:
        self.ocr_service = ocr_service or OcrService()
        self.matcher = matcher or RuleMatcher()
        self.min_text_length = min_text_length

    def verify(
        self,
        content: bytes,
        kind: str,
        document_type: str,
        citizen_name: str | None = None,
        regulation: RegulationRules | None = None,
    ) -> VerificationOutcome:
        """Read a document and decide what happens to it."""
        ocr_result = self.ocr_service.extract_text(content, kind)
        return self.decide(
            ocr_result,
            document_type=document_type,
            citizen_name=citizen_name,
            regulation=regulation,
        )

    def decide(
        self,
        ocr_result: OcrResult,
        document_type: str,
        citizen_name: str | None = None,
        regulation: RegulationRules | None = None,
    ) -> VerificationOutcome:
        """Turn an OCR result into a verification decision."""
        base = VerificationOutcome(
            ocr_status=ocr_result.status,
            verification_status=VerificationStatus.NEEDS_REVIEW,
            ocr_method=ocr_result.method,
            ocr_characters=len(ocr_result.text or ""),
            ocr_error=ocr_result.error,
        )

        # 1. OCR could not read the file at all.
        if not ocr_result.succeeded:
            base.reason = (
                f"The document text could not be extracted, so it needs officer "
                f"review. ({ocr_result.error})"
                if ocr_result.error
                else "The document text could not be extracted, so it needs officer review."
            )
            return base

        text = (ocr_result.text or "").strip()

        # 2. Text was extracted, but there is too little of it to judge.
        if len(text) < self.min_text_length:
            base.reason = (
                "Too little text could be read from the document to check it "
                "automatically, so it needs officer review."
            )
            return base

        fields = extract_fields(text)
        base.fields = fields.as_dict()

        # 3. The applicable regulation is unknown, so no scheme rules apply.
        if regulation is None:
            base.reason = (
                "The applicable regulation could not be determined, so the "
                "document needs officer review."
            )
            return base

        # 4. We have no rules for this type of document.
        if rules_for(document_type) is None:
            base.reason = (
                f"No automated checks exist for document type "
                f"'{document_type}', so it needs officer review."
            )
            return base

        # 5. Check the rules.
        match = self.matcher.match(
            DocumentContext(
                document_type=document_type,
                text=text,
                fields=fields,
                citizen_name=citizen_name,
                regulation=regulation,
            )
        )
        base.applied_rules = match.applied_rules

        if match.passed:
            base.verification_status = VerificationStatus.VERIFIED
            base.reason = None
            return base

        base.verification_status = VerificationStatus.REJECTED
        base.reason = match.reason
        base.failed_rules = [failure.rule for failure in match.failures]
        return base


@lru_cache
def get_pipeline() -> DocumentVerificationPipeline:
    """The shared pipeline, so Tesseract is configured once per process."""
    from backend.core.config import settings

    return DocumentVerificationPipeline(
        ocr_service=OcrService(tesseract_cmd=settings.tesseract_cmd),
        min_text_length=settings.ocr_min_text_length,
    )


def reset_pipeline() -> None:
    """Drop the cached pipeline, so new configuration is picked up."""
    get_pipeline.cache_clear()


__all__ = [
    "DocumentVerificationPipeline",
    "OcrStatus",
    "RegulationRules",
    "VerificationOutcome",
    "VerificationStatus",
    "get_pipeline",
    "normalise_document_type",
    "reset_pipeline",
]
