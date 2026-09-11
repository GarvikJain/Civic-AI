"""Compare required regulation documents with the citizen's verified uploads.

Rejected, pending and needs_review documents are not treated as present.
An Income Certificate is the scheme output, not proof of income, unless the
regulation explicitly asks for an income certificate.
"""

from __future__ import annotations

import re

from ai_modules.document_verification.rules import normalise_document_type

_GENERIC_WORDS = {
    "proof",
    "of",
    "the",
    "a",
    "an",
    "and",
    "or",
    "only",
    "document",
    "documents",
    "card",
    "copy",
    "recent",
    "registered",
}


def _tokens(value: str) -> set[str]:
    words = [word for word in re.split(r"[^a-z0-9]+", (value or "").lower()) if word]
    return {word for word in words if word not in _GENERIC_WORDS}


def document_covers_requirement(document_type: str, required_item: str) -> bool:
    """True when a verified document type reasonably matches one required item."""
    if not document_type or not required_item:
        return False
    # Applying for an income certificate does not itself prove income.
    if (
        normalise_document_type(document_type) == "income_certificate"
        and "certificate" not in _tokens(required_item)
    ):
        return False
    required_tokens = _tokens(required_item)
    document_tokens = _tokens(document_type)
    if not required_tokens or not document_tokens:
        return False
    return bool(required_tokens & document_tokens)


def missing_required_documents(
    required_items: list[str],
    verified_document_types: list[str],
) -> list[str]:
    """Required labels that no verified document type covers."""
    missing: list[str] = []
    for item in required_items:
        if any(
            document_covers_requirement(document_type, item)
            for document_type in verified_document_types
        ):
            continue
        missing.append(item)
    return missing
