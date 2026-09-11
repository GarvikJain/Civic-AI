"""Splitting regulation documents into retrievable chunks.

Chunking is deterministic: the same document always produces the same chunks
with the same IDs, so re-ingesting a file updates its chunks instead of adding
duplicates.

Section and clause headings are detected and carried on every chunk, so an
answer can cite the exact clause it came from.
"""

import hashlib
import re
from dataclasses import dataclass

from ai_modules.regulation_rag.ingestion import RegulationDocument

# "Section 4", "Clause 3.1", "Paragraph 2A", "Rule 7"
_HEADING = re.compile(
    r"^(?:section|clause|paragraph|para|rule|article)\s+([0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)",
    re.IGNORECASE,
)
# "3." or "3.1" at the start of a heading line
_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)[.)]\s+\S")


def detect_section(line: str) -> str | None:
    """Return the section label of a heading line, or None."""
    stripped = line.strip()
    if not stripped:
        return None

    match = _HEADING.match(stripped)
    if match:
        keyword = stripped.split()[0].rstrip(".").title()
        return f"{keyword} {match.group(1)}"

    match = _NUMBERED_HEADING.match(stripped)
    if match:
        return f"Section {match.group(1)}"
    return None


@dataclass(frozen=True)
class RegulationChunk:
    """A piece of a regulation, with everything needed to cite it."""

    chunk_id: str
    text: str
    source: str
    scheme_name: str
    chunk_index: int
    department: str | None = None
    circular_reference: str | None = None
    section: str | None = None
    regulation_id: int | None = None

    def as_metadata(self) -> dict[str, str | int]:
        """Metadata for the vector store.

        ChromaDB rejects None, so absent fields are left out rather than being
        filled in with a made-up value.
        """
        metadata: dict[str, str | int] = {
            "source": self.source,
            "scheme_name": self.scheme_name,
            "chunk_index": self.chunk_index,
        }
        if self.department:
            metadata["department"] = self.department
        if self.circular_reference:
            metadata["circular_reference"] = self.circular_reference
        if self.section:
            metadata["section"] = self.section
        if self.regulation_id is not None:
            metadata["regulation_id"] = self.regulation_id
        return metadata


def document_key(document: RegulationDocument) -> str:
    """A short stable ID for a document, based on its name and scheme."""
    raw = f"{document.source}|{document.scheme_name}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _split_into_sections(text: str) -> list[tuple[str | None, str]]:
    """Group the text into (section label, section text) pairs."""
    sections: list[tuple[str | None, list[str]]] = []
    current_label: str | None = None
    current_lines: list[str] = []

    for line in text.split("\n"):
        label = detect_section(line)
        if label is not None:
            if current_lines:
                sections.append((current_label, current_lines))
            current_label = label
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_label, current_lines))

    return [(label, "\n".join(lines).strip()) for label, lines in sections]


def _overlap_tail(text: str, overlap: int) -> str:
    """The last `overlap` characters of a chunk, cut at a word boundary."""
    if overlap <= 0 or len(text) <= overlap:
        return text if overlap > 0 else ""
    tail = text[-overlap:]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split one section into chunks, preferring paragraph boundaries."""
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    current = ""

    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        # A single paragraph longer than the limit is cut on word boundaries.
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            words = paragraph.split(" ")
            piece = ""
            for word in words:
                candidate = f"{piece} {word}".strip()
                if len(candidate) > chunk_size and piece:
                    chunks.append(piece)
                    piece = f"{_overlap_tail(piece, overlap)} {word}".strip()
                else:
                    piece = candidate
            if piece:
                current = piece
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) > chunk_size and current:
            chunks.append(current)
            tail = _overlap_tail(current, overlap)
            current = f"{tail}\n\n{paragraph}".strip() if tail else paragraph
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


def chunk_document(
    document: RegulationDocument, chunk_size: int = 900, overlap: int = 150
) -> list[RegulationChunk]:
    """Split a document into chunks that keep their citation metadata."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be zero or more and smaller than chunk_size")

    key = document_key(document)
    chunks: list[RegulationChunk] = []

    for section_label, section_text in _split_into_sections(document.text):
        for piece in _split_text(section_text, chunk_size, overlap):
            index = len(chunks)
            chunks.append(
                RegulationChunk(
                    chunk_id=f"{key}-{index:04d}",
                    text=piece,
                    source=document.source,
                    scheme_name=document.scheme_name,
                    chunk_index=index,
                    department=document.department,
                    circular_reference=document.circular_reference,
                    section=section_label,
                    regulation_id=document.regulation_id,
                )
            )
    return chunks
