"""Unit tests for the document verification module.

Nothing here needs Tesseract, PyMuPDF's OCR path or any network access: images
are drawn with Pillow, PDFs are built in memory, and Tesseract is replaced by a
stub that returns fixed text.
"""

import io

import pytest

from ai_modules.document_verification.errors import (
    DocumentTooLargeError,
    UnsupportedDocumentError,
)
from ai_modules.document_verification.field_extraction import (
    extract_fields,
    normalise_name,
    parse_amount,
)
from ai_modules.document_verification.file_validation import (
    detect_format,
    safe_stored_filename,
    validate_upload,
)
from ai_modules.document_verification.ocr_service import OcrResult, OcrService
from ai_modules.document_verification.pipeline import DocumentVerificationPipeline
from ai_modules.document_verification.preprocessing import prepare_for_ocr
from ai_modules.document_verification.rules import (
    DocumentContext,
    RegulationRules,
    RuleMatcher,
    normalise_document_type,
    rules_for,
)
from ai_modules.document_verification.states import OcrStatus, VerificationStatus

INCOME_CERTIFICATE_TEXT = """GOVERNMENT OF EXAMPLE STATE
REVENUE DEPARTMENT
INCOME CERTIFICATE
Certificate Number: EX/INC/2026/0001
Name: Test Citizen
Address: 12 Example Road, Example City
Annual Income: Rs. 1,80,000
Issuing Authority: Tahsildar, Example Taluk
Date of Issue: 12-01-2026
"""

EXAMPLE_REGULATION = RegulationRules(
    regulation_id=1,
    scheme_name="Example Income Certificate Scheme",
    department="Revenue",
    eligibility_criteria=(
        "Applicants are eligible if the total annual household income is below "
        "2,50,000 rupees."
    ),
    required_documents="Proof of identity, proof of residence, recent income proof.",
    circular_reference="EXAMPLE/CIRC/2026/01",
)


# --- helpers ----------------------------------------------------------------


def png_bytes(text: str = "CivicAI", size=(600, 200)) -> bytes:
    """A real PNG, drawn locally."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).text((10, 80), text, fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes(text: str = "CivicAI") -> bytes:
    """A real JPEG, drawn locally."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (600, 200), "white")
    ImageDraw.Draw(image).text((10, 80), text, fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def pdf_bytes(text: str = INCOME_CERTIFICATE_TEXT) -> bytes:
    """A small text-based PDF, built in memory."""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    data = document.tobytes()
    document.close()
    return data


class StubTesseract:
    """Stands in for the pytesseract module."""

    def __init__(self, text: str = INCOME_CERTIFICATE_TEXT, error: Exception | None = None):
        self.text = text
        self.error = error
        self.calls = 0

    def image_to_string(self, image):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.text


class TesseractNotFoundError(Exception):
    """Named like pytesseract's own error, which the service detects by name."""


class StubOcr:
    """An OCR service that returns a fixed result."""

    def __init__(self, result: OcrResult):
        self.result = result
        self.calls: list[tuple[int, str]] = []

    def extract_text(self, content: bytes, kind: str) -> OcrResult:
        self.calls.append((len(content), kind))
        return self.result


def completed(text: str = INCOME_CERTIFICATE_TEXT) -> OcrResult:
    return OcrResult(text=text, status=OcrStatus.COMPLETED, pages=1, method="tesseract")


def pipeline_with(result: OcrResult) -> DocumentVerificationPipeline:
    return DocumentVerificationPipeline(ocr_service=StubOcr(result))


# --- 1-6: file handling -----------------------------------------------------


def test_valid_png_is_accepted():
    validated = validate_upload("scan.png", png_bytes())
    assert validated.kind == "image"
    assert validated.detected_format == "png"


def test_valid_jpg_is_accepted():
    validated = validate_upload("scan.jpg", jpeg_bytes())
    assert validated.kind == "image"
    assert validated.detected_format == "jpeg"


def test_valid_pdf_is_accepted():
    validated = validate_upload("scan.pdf", pdf_bytes())
    assert validated.kind == "pdf"
    assert validated.detected_format == "pdf"


def test_unsupported_extension_is_rejected():
    with pytest.raises(UnsupportedDocumentError) as error:
        validate_upload("payload.exe", b"MZ\x90\x00 not a document")
    assert "Unsupported file type" in str(error.value)


def test_renamed_executable_is_rejected_even_with_an_image_extension():
    # The extension alone is never trusted.
    with pytest.raises(UnsupportedDocumentError) as error:
        validate_upload("payload.png", b"MZ\x90\x00 windows executable")
    assert "not a readable PNG, JPG or PDF" in str(error.value)


def test_pdf_bytes_with_an_image_extension_are_rejected():
    with pytest.raises(UnsupportedDocumentError) as error:
        validate_upload("really_a_pdf.png", pdf_bytes())
    assert "does not match its contents" in str(error.value)


def test_jpeg_bytes_with_a_png_extension_are_rejected():
    with pytest.raises(UnsupportedDocumentError) as error:
        validate_upload("scan.png", jpeg_bytes())
    assert "does not match its contents" in str(error.value)


def test_empty_file_is_rejected():
    with pytest.raises(UnsupportedDocumentError):
        validate_upload("scan.png", b"")


def test_oversized_file_is_rejected():
    with pytest.raises(DocumentTooLargeError) as error:
        validate_upload("scan.png", png_bytes(size=(50, 50)), max_bytes=10)
    assert "upload limit" in str(error.value)


def test_traversal_filename_is_reduced_to_its_extension():
    validated = validate_upload("../../../../etc/passwd.png", png_bytes())
    # The stored name is generated, so nothing from the original name survives.
    assert "passwd" not in validated.stored_filename
    assert "/" not in validated.stored_filename and "\\" not in validated.stored_filename
    assert validated.stored_filename.endswith(".png")


def test_stored_filenames_are_unique():
    assert safe_stored_filename(".png") != safe_stored_filename(".png")


def test_storage_strips_path_components_from_the_stored_name(tmp_path, monkeypatch):
    """A stored name with '..' cannot climb out of the documents directory."""
    from backend.core import config as config_module
    from backend.services import document_storage

    monkeypatch.setattr(config_module.settings, "documents_dir", str(tmp_path))
    path = document_storage.resolve_document_path("../../etc/passwd.png")
    assert path.parent == tmp_path.resolve()
    assert path.name == "passwd.png"


def test_storage_rejects_dot_and_empty_names(tmp_path, monkeypatch):
    from backend.core import config as config_module
    from backend.services import document_storage

    monkeypatch.setattr(config_module.settings, "documents_dir", str(tmp_path))
    with pytest.raises(ValueError, match="Invalid stored document name"):
        document_storage.resolve_document_path("..")
    with pytest.raises(ValueError, match="Invalid stored document name"):
        document_storage.resolve_document_path("")


def test_storage_writes_only_inside_the_documents_directory(tmp_path, monkeypatch):
    from backend.core import config as config_module
    from backend.services import document_storage

    monkeypatch.setattr(config_module.settings, "documents_dir", str(tmp_path))
    path = document_storage.save_document("abc123.png", b"hello")
    assert path.parent == tmp_path.resolve()
    assert path.read_bytes() == b"hello"
    assert document_storage.read_document("abc123.png") == b"hello"


def test_detect_format_reads_the_leading_bytes():
    assert detect_format(png_bytes()) == "png"
    assert detect_format(jpeg_bytes()) == "jpeg"
    assert detect_format(pdf_bytes()) == "pdf"
    assert detect_format(b"#!/bin/sh\necho hi") is None


# --- 13-15: OCR -------------------------------------------------------------


def test_ocr_reads_an_image_with_the_stubbed_engine():
    service = OcrService(engine=StubTesseract("Name: Test Citizen"))
    result = service.extract_text(png_bytes(), "image")
    assert result.status is OcrStatus.COMPLETED
    assert result.text == "Name: Test Citizen"
    assert result.method == "tesseract"


def test_ocr_failure_is_reported_instead_of_raising():
    engine = StubTesseract(error=TesseractNotFoundError("tesseract is not installed"))
    result = OcrService(engine=engine).extract_text(png_bytes(), "image")
    assert result.status is OcrStatus.FAILED
    assert "Tesseract OCR engine is not installed" in result.error


def test_ocr_reports_a_broken_image_as_failed():
    result = OcrService(engine=StubTesseract()).extract_text(b"\x89PNG\r\n\x1a\nbroken", "image")
    assert result.status is OcrStatus.FAILED
    assert "could not be opened" in result.error


def test_text_based_pdf_is_read_without_tesseract():
    engine = StubTesseract("should not be used")
    service = OcrService(engine=engine)
    result = service.extract_text(pdf_bytes(), "pdf")
    assert result.status is OcrStatus.COMPLETED
    assert result.method == "embedded_pdf_text"
    assert "INCOME CERTIFICATE" in result.text
    assert engine.calls == 0


def test_scanned_pdf_page_falls_back_to_tesseract():
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    document = fitz.open()
    document.new_page()  # an empty page carries no embedded text
    data = document.tobytes()
    document.close()

    engine = StubTesseract("Name: Test Citizen")
    result = OcrService(engine=engine).extract_text(data, "pdf")
    assert result.status is OcrStatus.COMPLETED
    assert result.method == "tesseract"
    assert engine.calls == 1


def test_preprocessing_does_not_change_the_original_image():
    from PIL import Image

    original = Image.open(io.BytesIO(png_bytes()))
    before = original.tobytes()
    prepared = prepare_for_ocr(original)

    assert original.tobytes() == before
    assert original.mode == "RGB"
    assert prepared.mode == "L"
    # Small scans are enlarged to help Tesseract.
    assert prepared.size[0] >= original.size[0]


def test_preprocessing_handles_a_very_large_image():
    from PIL import Image

    prepared = prepare_for_ocr(Image.new("RGB", (4000, 500), "white"))
    assert prepared.size[0] == 3000


# --- 16-17: field extraction ------------------------------------------------


def test_fields_are_extracted_from_labelled_text():
    fields = extract_fields(INCOME_CERTIFICATE_TEXT).as_dict()
    assert fields["name"] == "Test Citizen"
    assert fields["certificate_number"] == "EX/INC/2026/0001"
    assert fields["income"] == "1,80,000"
    assert fields["issuing_authority"] == "Tahsildar, Example Taluk"
    assert fields["date"] == "12-01-2026"
    assert fields["address"] == "12 Example Road, Example City"


def test_missing_fields_are_absent_rather_than_invented():
    text = "INCOME CERTIFICATE\nName: Test Citizen\nIssuing Authority: Tahsildar\n"
    fields = extract_fields(text)
    assert fields.has("name")
    assert not fields.has("income")
    assert fields.get("income") is None
    assert "income" not in fields.as_dict()


def test_amounts_and_names_are_normalised():
    assert parse_amount("1,80,000") == 180000
    assert parse_amount("Rs. 90,500") == 90500
    assert parse_amount("not a number") is None
    assert parse_amount(None) is None
    assert normalise_name("  Test   CITIZEN. ") == "test citizen"


# --- 18-22: rule matching ---------------------------------------------------


def test_document_type_is_normalised_to_its_rule_set():
    assert normalise_document_type("Income Certificate") == "income_certificate"
    assert rules_for("Income Certificate") is not None
    assert rules_for("Marriage Photograph") is None


def test_a_valid_document_passes_every_rule():
    context = DocumentContext(
        document_type="Income Certificate",
        text=INCOME_CERTIFICATE_TEXT,
        fields=extract_fields(INCOME_CERTIFICATE_TEXT),
        citizen_name="Test Citizen",
        regulation=EXAMPLE_REGULATION,
    )
    result = RuleMatcher().match(context)
    assert result.passed
    assert result.reason is None
    assert "required_field:income" in result.applied_rules


def test_missing_income_names_the_rule_that_failed():
    text = INCOME_CERTIFICATE_TEXT.replace("Annual Income: Rs. 1,80,000", "")
    result = RuleMatcher().match(
        DocumentContext(
            document_type="Income Certificate",
            text=text,
            fields=extract_fields(text),
            citizen_name="Test Citizen",
            regulation=EXAMPLE_REGULATION,
        )
    )
    assert not result.passed
    assert result.failures[0].rule == "required_field:income"
    assert result.reason == "Required income field could not be found on the document."


def test_income_above_the_regulation_limit_is_rejected():
    text = INCOME_CERTIFICATE_TEXT.replace("1,80,000", "9,90,000")
    result = RuleMatcher().match(
        DocumentContext(
            document_type="Income Certificate",
            text=text,
            fields=extract_fields(text),
            citizen_name="Test Citizen",
            regulation=EXAMPLE_REGULATION,
        )
    )
    assert not result.passed
    assert [failure.rule for failure in result.failures] == [
        "income_within_regulation_limit"
    ]
    assert "exceeds the limit of 250,000" in result.reason


def test_a_name_that_belongs_to_someone_else_is_rejected():
    result = RuleMatcher().match(
        DocumentContext(
            document_type="Income Certificate",
            text=INCOME_CERTIFICATE_TEXT,
            fields=extract_fields(INCOME_CERTIFICATE_TEXT),
            citizen_name="Another Person",
            regulation=EXAMPLE_REGULATION,
        )
    )
    assert not result.passed
    assert result.failures[0].rule == "name_matches_citizen"
    assert "does not match the registered citizen profile" in result.reason


def test_a_middle_name_on_the_document_still_matches():
    text = INCOME_CERTIFICATE_TEXT.replace("Name: Test Citizen", "Name: Test Kumar Citizen")
    result = RuleMatcher().match(
        DocumentContext(
            document_type="Income Certificate",
            text=text,
            fields=extract_fields(text),
            citizen_name="Test Citizen",
            regulation=EXAMPLE_REGULATION,
        )
    )
    assert result.passed


def test_an_income_limit_is_only_applied_when_the_regulation_states_one():
    regulation = RegulationRules(
        regulation_id=2,
        scheme_name="Example Income Certificate Scheme",
        eligibility_criteria="Applicants must be residents of the district.",
        required_documents="Income proof.",
    )
    text = INCOME_CERTIFICATE_TEXT.replace("1,80,000", "9,90,000")
    result = RuleMatcher().match(
        DocumentContext(
            document_type="Income Certificate",
            text=text,
            fields=extract_fields(text),
            citizen_name="Test Citizen",
            regulation=regulation,
        )
    )
    assert result.passed


def test_a_document_type_the_scheme_does_not_ask_for_is_rejected():
    regulation = RegulationRules(
        regulation_id=3,
        scheme_name="Example Income Certificate Scheme",
        required_documents="Proof of identity only.",
    )
    result = RuleMatcher().match(
        DocumentContext(
            document_type="Residence Proof",
            text="Name: Test Citizen\nAddress: 12 Example Road\nIssued by: Village Officer",
            fields=extract_fields(
                "Name: Test Citizen\nAddress: 12 Example Road\nIssued by: Village Officer"
            ),
            citizen_name="Test Citizen",
            regulation=regulation,
        )
    )
    assert not result.passed
    assert result.failures[0].rule == "document_type_allowed_by_regulation"
    assert "is not listed in the required documents" in result.reason


def test_every_rejection_reason_belongs_to_a_rule_that_ran():
    text = INCOME_CERTIFICATE_TEXT.replace("Certificate Number: EX/INC/2026/0001", "")
    result = RuleMatcher().match(
        DocumentContext(
            document_type="Income Certificate",
            text=text,
            fields=extract_fields(text),
            citizen_name="Test Citizen",
            regulation=EXAMPLE_REGULATION,
        )
    )
    assert not result.passed
    for failure in result.failures:
        assert failure.rule in result.applied_rules
        assert failure.reason


# --- pipeline decisions -----------------------------------------------------


def test_pipeline_verifies_a_good_document():
    outcome = pipeline_with(completed()).verify(
        content=png_bytes(),
        kind="image",
        document_type="Income Certificate",
        citizen_name="Test Citizen",
        regulation=EXAMPLE_REGULATION,
    )
    assert outcome.ocr_status is OcrStatus.COMPLETED
    assert outcome.verification_status is VerificationStatus.VERIFIED
    assert outcome.reason is None
    assert outcome.fields["income"] == "1,80,000"


def test_pipeline_rejects_with_the_exact_reason():
    text = INCOME_CERTIFICATE_TEXT.replace("Annual Income: Rs. 1,80,000", "")
    outcome = pipeline_with(completed(text)).verify(
        content=png_bytes(),
        kind="image",
        document_type="Income Certificate",
        citizen_name="Test Citizen",
        regulation=EXAMPLE_REGULATION,
    )
    # OCR succeeding does not make a document verified.
    assert outcome.ocr_status is OcrStatus.COMPLETED
    assert outcome.verification_status is VerificationStatus.REJECTED
    assert outcome.reason == "Required income field could not be found on the document."
    assert outcome.failed_rules == ["required_field:income"]


def test_pipeline_sends_a_failed_ocr_document_to_review():
    failed = OcrResult(status=OcrStatus.FAILED, error="Tesseract is not installed.")
    outcome = pipeline_with(failed).verify(
        content=png_bytes(),
        kind="image",
        document_type="Income Certificate",
        citizen_name="Test Citizen",
        regulation=EXAMPLE_REGULATION,
    )
    assert outcome.ocr_status is OcrStatus.FAILED
    assert outcome.verification_status is VerificationStatus.NEEDS_REVIEW
    assert "needs officer review" in outcome.reason
    assert "Tesseract is not installed." in outcome.reason


def test_pipeline_sends_an_unreadable_document_to_review():
    outcome = pipeline_with(completed("Name: T")).verify(
        content=png_bytes(),
        kind="image",
        document_type="Income Certificate",
        citizen_name="Test Citizen",
        regulation=EXAMPLE_REGULATION,
    )
    assert outcome.ocr_status is OcrStatus.COMPLETED
    assert outcome.verification_status is VerificationStatus.NEEDS_REVIEW
    assert "Too little text" in outcome.reason


def test_pipeline_needs_review_when_the_regulation_is_unknown():
    outcome = pipeline_with(completed()).verify(
        content=png_bytes(),
        kind="image",
        document_type="Income Certificate",
        citizen_name="Test Citizen",
        regulation=None,
    )
    assert outcome.verification_status is VerificationStatus.NEEDS_REVIEW
    assert "applicable regulation could not be determined" in outcome.reason


def test_pipeline_needs_review_for_an_unknown_document_type():
    outcome = pipeline_with(completed()).verify(
        content=png_bytes(),
        kind="image",
        document_type="Marriage Photograph",
        citizen_name="Test Citizen",
        regulation=EXAMPLE_REGULATION,
    )
    assert outcome.verification_status is VerificationStatus.NEEDS_REVIEW
    assert "No automated checks exist" in outcome.reason


def test_pipeline_never_calls_an_llm():
    import ai_modules.document_verification.pipeline as pipeline_module
    import ai_modules.document_verification.rules as rules_module

    for module in (pipeline_module, rules_module):
        source = module.__doc__ or ""
        assert "groq" not in source.lower()
    # The module must not import the Groq client at all.
    from pathlib import Path

    package = Path(pipeline_module.__file__).parent
    for path in package.glob("*.py"):
        assert "groq" not in path.read_text(encoding="utf-8").lower(), path.name
