"""Loading regulation documents from the local data directory.

Documents are plain text files placed under data/regulations/ by hand. Nothing
is downloaded from the internet.

A file may start with a small metadata header so that citations can name the
scheme and circular it came from:

    scheme_name: Income Certificate Scheme
    department: Revenue
    circular_reference: CIRC/2026/11
    ---
    Section 1. Eligibility
    ...

Without a header the file name is used as the scheme name.
"""

import re
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_SUFFIXES = {".txt", ".md"}

# Keys understood in the document header. Anything else is ignored.
_HEADER_KEYS = {
    "scheme_name",
    "department",
    "circular_reference",
    "regulation_id",
}
_HEADER_SEPARATOR = "---"
_HEADER_LINE = re.compile(r"^([a-zA-Z_]+)\s*:\s*(.*)$")


@dataclass(frozen=True)
class RegulationDocument:
    """One regulation document with its metadata."""

    source: str
    text: str
    scheme_name: str
    department: str | None = None
    circular_reference: str | None = None
    regulation_id: int | None = None


def parse_header(raw_text: str) -> tuple[dict[str, str], str]:
    """Split an optional "key: value" header from the document body."""
    lines = raw_text.splitlines()
    header: dict[str, str] = {}

    # A header only counts if a separator line follows the key/value lines.
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line == _HEADER_SEPARATOR:
            body = "\n".join(lines[index + 1 :])
            return header, body

        match = _HEADER_LINE.match(line)
        if not match:
            break
        key, value = match.group(1).lower(), match.group(2).strip()
        if key in _HEADER_KEYS and value:
            header[key] = value
        index += 1

    # No separator found, so the whole file is the body.
    return {}, raw_text


def clean_text(text: str) -> str:
    """Tidy up whitespace without losing paragraph breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse runs of spaces and tabs, and drop trailing spaces per line.
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    # At most one blank line between paragraphs.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_document(path: Path) -> RegulationDocument:
    """Read one regulation file into a RegulationDocument."""
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Unsupported regulation file type: {path.suffix}. "
            f"Supported types: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )

    raw_text = path.read_text(encoding="utf-8")
    header, body = parse_header(raw_text)

    regulation_id = header.get("regulation_id")
    return RegulationDocument(
        source=path.name,
        text=clean_text(body),
        scheme_name=header.get("scheme_name") or path.stem.replace("_", " ").title(),
        department=header.get("department"),
        circular_reference=header.get("circular_reference"),
        regulation_id=int(regulation_id) if regulation_id and regulation_id.isdigit() else None,
    )


def load_documents(directory: Path) -> list[RegulationDocument]:
    """Load every supported regulation file in a directory, sorted by name."""
    if not directory.exists():
        return []

    documents = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            document = load_document(path)
            if document.text:
                documents.append(document)
    return documents
