"""Upload validation.

The file name is never trusted on its own: the extension and the file's own
leading bytes must agree, and the size must be within the configured limit.
Nothing here ever opens or runs the uploaded file.
"""

import uuid
from dataclasses import dataclass

from ai_modules.document_verification.errors import (
    DocumentTooLargeError,
    UnsupportedDocumentError,
)

# Extension -> the kind of document it claims to be.
SUPPORTED_EXTENSIONS = {
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".pdf": "pdf",
}

# The first bytes each supported format must start with.
_MAGIC_NUMBERS = {
    "png": b"\x89PNG\r\n\x1a\n",
    "jpeg": b"\xff\xd8\xff",
    "pdf": b"%PDF",
}

# An extension is only accepted when the file's leading bytes match it.
_EXTENSION_FORMATS = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".pdf": "pdf",
}

DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@dataclass(frozen=True)
class ValidatedUpload:
    """A file that passed validation."""

    extension: str
    kind: str  # "image" or "pdf"
    detected_format: str  # png / jpeg / pdf
    size_bytes: int
    stored_filename: str


def _extension_of(filename: str) -> str:
    """The lowercase extension of a file name, without trusting the path."""
    # Only the part after the last dot of the final path element is used, so a
    # name such as "../../etc/passwd.png" cannot reach outside storage.
    name = (filename or "").replace("\\", "/").split("/")[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[1].lower()


def detect_format(content: bytes) -> str | None:
    """Identify the real format from the file's leading bytes."""
    for name, magic in _MAGIC_NUMBERS.items():
        if content.startswith(magic):
            return name
    return None


def safe_stored_filename(extension: str) -> str:
    """A server-generated file name.

    The citizen's original file name is never used on disk, so it cannot
    influence the storage path.
    """
    return f"{uuid.uuid4().hex}{extension}"


def validate_upload(
    filename: str, content: bytes, max_bytes: int = DEFAULT_MAX_BYTES
) -> ValidatedUpload:
    """Check an uploaded file and describe it.

    Raises UnsupportedDocumentError or DocumentTooLargeError with a message
    that can be shown to the citizen.
    """
    extension = _extension_of(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedDocumentError(
            f"Unsupported file type '{extension or filename}'. "
            f"Supported types are: {supported}."
        )

    if not content:
        raise UnsupportedDocumentError("The uploaded file is empty.")

    if len(content) > max_bytes:
        limit_mb = max_bytes / (1024 * 1024)
        raise DocumentTooLargeError(
            f"The file is larger than the {limit_mb:.0f} MB upload limit."
        )

    detected = detect_format(content)
    if detected is None:
        raise UnsupportedDocumentError(
            "The file contents are not a readable PNG, JPG or PDF document."
        )

    # The extension must match what the bytes actually are. A .png that is
    # really a JPEG, or a .pdf that is really an image, is rejected rather
    # than being passed to OCR.
    expected_format = _EXTENSION_FORMATS[extension]
    if expected_format != detected:
        raise UnsupportedDocumentError(
            f"The file extension '{extension}' does not match its contents "
            f"({detected}). The file was not accepted."
        )

    return ValidatedUpload(
        extension=extension,
        kind=SUPPORTED_EXTENSIONS[extension],
        detected_format=detected,
        size_bytes=len(content),
        stored_filename=safe_stored_filename(extension),
    )
