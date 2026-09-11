"""Errors raised by the document verification module."""


class DocumentError(Exception):
    """Base class for document verification failures."""


class UnsupportedDocumentError(DocumentError):
    """The uploaded file is not a supported document format."""


class DocumentTooLargeError(DocumentError):
    """The uploaded file is bigger than the configured limit."""


class OcrUnavailableError(DocumentError):
    """Tesseract or a supporting library is not installed."""


class OcrFailedError(DocumentError):
    """The document could not be read, even though OCR is available."""
