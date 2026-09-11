"""OCR service.

Images are read with Pillow and Tesseract. PDFs are handled with PyMuPDF: a
text-based PDF gives its text directly, and a scanned PDF is rendered to images
and then read with Tesseract.

Tesseract is configured once per process, not once per document.
"""

from dataclasses import dataclass, field

from ai_modules.document_verification.errors import (
    OcrFailedError,
    OcrUnavailableError,
)
from ai_modules.document_verification.preprocessing import prepare_for_ocr
from ai_modules.document_verification.states import OcrStatus

# Resolution used when rendering a PDF page for OCR.
PDF_RENDER_DPI = 200
# A PDF page with at least this much embedded text is trusted as text-based.
EMBEDDED_TEXT_THRESHOLD = 60


@dataclass
class OcrResult:
    """What OCR produced for one document."""

    text: str = ""
    status: OcrStatus = OcrStatus.PENDING
    pages: int = 0
    # How the text was obtained: tesseract / embedded_pdf_text / mixed
    method: str = ""
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.status is OcrStatus.COMPLETED


class OcrService:
    """Extracts text from images and PDFs.

    Pass `engine` to inject a stand-in with an `image_to_string` function, which
    is how the tests avoid needing Tesseract installed.
    """

    def __init__(self, tesseract_cmd: str = "", engine=None) -> None:
        self.tesseract_cmd = tesseract_cmd
        self._engine = engine
        self._configured = False

    @property
    def engine(self):
        """The pytesseract module, imported and configured once."""
        if self._engine is None:
            try:
                import pytesseract
            except ImportError as error:
                raise OcrUnavailableError(
                    "pytesseract is not installed. "
                    "Install it with: pip install -r requirements.txt"
                ) from error
            self._engine = pytesseract

        if not self._configured:
            # On Windows the Tesseract executable is usually not on PATH.
            if self.tesseract_cmd:
                self._engine.pytesseract.tesseract_cmd = self.tesseract_cmd
            self._configured = True
        return self._engine

    # --- images ------------------------------------------------------------

    def _open_image(self, content: bytes):
        try:
            import io

            from PIL import Image

            return Image.open(io.BytesIO(content))
        except ImportError as error:
            raise OcrUnavailableError(
                "Pillow is not installed. "
                "Install it with: pip install -r requirements.txt"
            ) from error
        except Exception as error:
            raise OcrFailedError(
                f"The image could not be opened: {type(error).__name__}"
            ) from error

    def _read_image(self, image) -> str:
        """Run Tesseract on one prepared image."""
        try:
            return self.engine.image_to_string(prepare_for_ocr(image))
        except OcrUnavailableError:
            raise
        except Exception as error:
            # A missing Tesseract binary surfaces here, not at import time.
            name = type(error).__name__
            if "TesseractNotFound" in name:
                raise OcrUnavailableError(
                    "The Tesseract OCR engine is not installed, or TESSERACT_CMD "
                    "does not point at tesseract.exe."
                ) from error
            raise OcrFailedError(f"Tesseract could not read the document: {name}") from error

    def extract_from_image(self, content: bytes) -> OcrResult:
        """Read text from a PNG or JPG."""
        image = self._open_image(content)
        text = self._read_image(image)
        return OcrResult(
            text=text.strip(),
            status=OcrStatus.COMPLETED,
            pages=1,
            method="tesseract",
        )

    # --- PDFs --------------------------------------------------------------

    def extract_from_pdf(self, content: bytes) -> OcrResult:
        """Read text from a PDF, using embedded text when it has any."""
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
        except ImportError as error:
            raise OcrUnavailableError(
                "PyMuPDF is not installed, so PDF documents cannot be read. "
                "Install it with: pip install -r requirements.txt"
            ) from error

        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception as error:
            raise OcrFailedError(
                f"The PDF could not be opened: {type(error).__name__}"
            ) from error

        page_texts: list[str] = []
        methods: set[str] = set()
        warnings: list[str] = []

        try:
            for page in document:
                embedded = (page.get_text() or "").strip()
                if len(embedded) >= EMBEDDED_TEXT_THRESHOLD:
                    page_texts.append(embedded)
                    methods.add("embedded_pdf_text")
                    continue

                # Scanned page: render it and hand it to Tesseract.
                image = self._render_page(page)
                if image is None:
                    warnings.append("A PDF page could not be rendered for OCR.")
                    continue
                page_texts.append(self._read_image(image).strip())
                methods.add("tesseract")
            pages = document.page_count
        finally:
            document.close()

        text = "\n\n".join(part for part in page_texts if part).strip()
        return OcrResult(
            text=text,
            status=OcrStatus.COMPLETED,
            pages=pages,
            method="mixed" if len(methods) > 1 else next(iter(methods), ""),
            warnings=warnings,
        )

    def _render_page(self, page):
        """Render one PDF page into a Pillow image."""
        try:
            import io

            from PIL import Image

            pixmap = page.get_pixmap(dpi=PDF_RENDER_DPI)
            return Image.open(io.BytesIO(pixmap.tobytes("png")))
        except Exception:
            return None

    # --- entry point -------------------------------------------------------

    def extract_text(self, content: bytes, kind: str) -> OcrResult:
        """Read a document. `kind` is "image" or "pdf".

        Never raises: a failure is reported as a failed OcrResult, so the
        caller can put the document into review instead of crashing.
        """
        try:
            if kind == "pdf":
                return self.extract_from_pdf(content)
            return self.extract_from_image(content)
        except (OcrUnavailableError, OcrFailedError) as error:
            return OcrResult(status=OcrStatus.FAILED, error=str(error))
