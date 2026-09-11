"""Saving uploaded documents on disk.

Files are written under the configured documents directory using a
server-generated name. The citizen's original file name never touches the
filesystem, and every read resolves the path and checks it is still inside the
storage directory, so a crafted name cannot escape it.
"""

from pathlib import Path

from backend.core.config import BASE_DIR, settings


def documents_dir() -> Path:
    """The directory uploaded documents are stored in, created if needed."""
    configured = Path(settings.documents_dir)
    directory = configured if configured.is_absolute() else BASE_DIR / configured
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_document(stored_filename: str, content: bytes) -> Path:
    """Write an uploaded file and return its path."""
    path = resolve_document_path(stored_filename)
    path.write_bytes(content)
    return path


def resolve_document_path(stored_filename: str) -> Path:
    """Turn a stored file name into a path inside the storage directory.

    Raises ValueError if the name would point anywhere else.
    """
    directory = documents_dir().resolve()
    # Only the final path element is used, so "../" cannot climb out.
    name = Path(str(stored_filename)).name
    if not name or name in {".", ".."}:
        raise ValueError("Invalid stored document name.")

    path = (directory / name).resolve()
    if path.parent != directory:
        raise ValueError("Resolved document path is outside the storage directory.")
    return path


def read_document(stored_filename: str) -> bytes:
    """Read a stored document back from disk."""
    return resolve_document_path(stored_filename).read_bytes()


def delete_document(stored_filename: str) -> None:
    """Remove a stored document, ignoring a file that is already gone."""
    try:
        resolve_document_path(stored_filename).unlink(missing_ok=True)
    except ValueError:
        return
