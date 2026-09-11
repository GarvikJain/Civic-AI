"""Pulling structured fields out of OCR text.

Extraction is deliberately deterministic: each field is found by looking for
its printed label. No LLM is involved, and a field that is not present is
simply absent rather than guessed.
"""

import re
from dataclasses import dataclass, field

# Field name -> the patterns that can produce it, tried in order.
_FIELD_PATTERNS: dict[str, list[str]] = {
    "name": [
        r"(?:applicant|citizen|holder)\s+name\s*[:\-]\s*([A-Za-z][A-Za-z .'\-]{2,60})",
        r"\bname\s*[:\-]\s*([A-Za-z][A-Za-z .'\-]{2,60})",
    ],
    "address": [r"\baddress\s*[:\-]\s*([^\n]{5,150})"],
    "date": [
        r"(?:date\s+of\s+issue|issue\s+date|issued\s+on|dated)\s*[:\-]?\s*"
        r"(\d{1,2}[-/.\s]\d{1,2}[-/.\s]\d{2,4})",
        r"\bdate\s*[:\-]\s*(\d{1,2}[-/.\s]\d{1,2}[-/.\s]\d{2,4})",
    ],
    "certificate_number": [
        r"(?:certificate|document)\s*(?:no|number|#)\s*[:.\-]?\s*([A-Za-z0-9/\-]{3,30})"
    ],
    "document_number": [
        r"(?:identity|id)\s*(?:card)?\s*(?:no|number|#)\s*[:.\-]?\s*([A-Za-z0-9/\-]{3,30})"
    ],
    "income": [
        r"(?:annual|total|household)?\s*income\s*[:\-]?\s*"
        r"(?:rs\.?|inr|₹)?\s*([\d][\d,]{2,15})"
    ],
    "issuing_authority": [
        r"issuing\s+authority\s*[:\-]\s*([^\n]{3,80})",
        r"issued\s+by\s*[:\-]?\s*([^\n]{3,80})",
    ],
    "reference_number": [
        r"(?:scheme|reference|circular)\s*(?:no|number|ref)?\s*[:.\-]?\s*"
        r"([A-Za-z0-9/\-]{3,40})"
    ],
}


@dataclass
class ExtractedFields:
    """The fields found in a document."""

    values: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def has(self, name: str) -> bool:
        return bool(self.values.get(name))

    def as_dict(self) -> dict[str, str]:
        return dict(self.values)


def parse_amount(value: str | None) -> int | None:
    """Read "2,40,000" as 240000. Returns None if it is not a number."""
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def normalise_name(value: str | None) -> str:
    """Lowercase a name and drop anything that is not a letter or space."""
    if not value:
        return ""
    cleaned = re.sub(r"[^a-z\s]", " ", value.lower())
    return " ".join(cleaned.split())


def extract_fields(text: str) -> ExtractedFields:
    """Find every field whose label appears in the OCR text."""
    if not text:
        return ExtractedFields()

    found: dict[str, str] = {}
    for name, patterns in _FIELD_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = " ".join(match.group(1).split()).strip(" .,;:-")
                if value:
                    found[name] = value
                    break
    return ExtractedFields(values=found)
