"""Deterministic eligibility rules extracted from Regulation text.

Operators are a fixed set. Client input is never executed as code.
A criterion that cannot be parsed safely becomes an unsupported item and
leads to manual_review rather than a guessed rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ai_modules.document_verification.field_extraction import parse_amount
from ai_modules.eligibility_nudge.questionnaire import EligibilityQuestion, Questionnaire

OPERATORS = (
    "equals",
    "not_equals",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "in",
    "required",
)

# Same income-limit phrasing used when reading regulation eligibility text.
_INCOME_LIMIT = re.compile(
    r"income\s+(?:is\s+)?(?:below|under|less\s+than|not\s+exceeding|upto|up\s+to)"
    r"\s*(?:rs\.?|inr|₹)?\s*([\d][\d,]{2,15})",
    re.IGNORECASE,
)
_INCOME_BELOW = re.compile(
    r"(below|under|less\s+than|not\s+exceeding|upto|up\s+to)",
    re.IGNORECASE,
)
_RESIDENT_ONE_YEAR = re.compile(
    r"resident(?:\s+of\s+the\s+district)?\s+for\s+at\s+least\s+(?:one|1)\s+year",
    re.IGNORECASE,
)
_EXISTING_CERTIFICATE = re.compile(
    r"(?:not\s+already\s+holding|already\s+holding)\s+a\s+valid\s+income\s+certificate"
    r"(?:\s+issued\s+in\s+the\s+same\s+financial\s+year)?",
    re.IGNORECASE,
)
_PROOF_OF = re.compile(
    r"proof of (identity|residence|income)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EligibilityRule:
    """One explicit comparison against a questionnaire field."""

    rule_id: str
    field_name: str
    operator: str
    value: Any
    summary: str
    source_excerpt: str


@dataclass(frozen=True)
class UnsupportedCriterion:
    """Regulation wording that was not turned into a rule."""

    excerpt: str
    reason: str


@dataclass(frozen=True)
class ExtractedProgramme:
    rules: tuple[EligibilityRule, ...]
    questions: tuple[EligibilityQuestion, ...]
    unsupported: tuple[UnsupportedCriterion, ...]
    required_document_types: tuple[str, ...]


def _excerpt(match: re.Match[str], text: str, pad: int = 0) -> str:
    start = max(0, match.start() - pad)
    end = min(len(text), match.end() + pad)
    return " ".join(text[start:end].split())


def _income_rule(text: str) -> tuple[EligibilityRule, EligibilityQuestion] | None:
    match = _INCOME_LIMIT.search(text)
    if match is None:
        return None
    limit = parse_amount(match.group(1))
    if limit is None:
        return None
    comparator = _INCOME_BELOW.search(match.group(0))
    phrase = (comparator.group(1) if comparator else "below").lower()
    if phrase in {"not exceeding", "upto", "up to"}:
        operator = "less_than_or_equal"
        summary = (
            f"Total annual household income must not exceed {limit:,} rupees."
        )
    else:
        operator = "less_than"
        summary = (
            f"Total annual household income must be below {limit:,} rupees."
        )
    rule = EligibilityRule(
        rule_id="annual_household_income",
        field_name="annual_household_income",
        operator=operator,
        value=limit,
        summary=summary,
        source_excerpt=_excerpt(match, text),
    )
    question = EligibilityQuestion(
        question_id="annual_household_income",
        field_name="annual_household_income",
        question_text=(
            "What is the total annual household income in rupees?"
        ),
        answer_type="integer",
        required=True,
    )
    return rule, question


def _residence_rule(text: str) -> tuple[EligibilityRule, EligibilityQuestion] | None:
    match = _RESIDENT_ONE_YEAR.search(text)
    if match is None:
        return None
    rule = EligibilityRule(
        rule_id="resident_of_district_at_least_one_year",
        field_name="resident_of_district_at_least_one_year",
        operator="equals",
        value=True,
        summary=(
            "The applicant has been a resident of the district for at least one year."
        ),
        source_excerpt=_excerpt(match, text),
    )
    question = EligibilityQuestion(
        question_id="resident_of_district_at_least_one_year",
        field_name="resident_of_district_at_least_one_year",
        question_text=(
            "Have you been a resident of the district for at least one year?"
        ),
        answer_type="boolean",
        required=True,
    )
    return rule, question


def _existing_certificate_rule(
    text: str,
) -> tuple[EligibilityRule, EligibilityQuestion] | None:
    match = _EXISTING_CERTIFICATE.search(text)
    if match is None:
        return None
    rule = EligibilityRule(
        rule_id="holds_income_certificate_this_year",
        field_name="holds_income_certificate_this_year",
        operator="equals",
        value=False,
        summary=(
            "The applicant is not already holding a valid income certificate "
            "issued in the same financial year."
        ),
        source_excerpt=_excerpt(match, text),
    )
    question = EligibilityQuestion(
        question_id="holds_income_certificate_this_year",
        field_name="holds_income_certificate_this_year",
        question_text=(
            "Are you already holding a valid income certificate issued in the "
            "same financial year?"
        ),
        answer_type="boolean",
        required=True,
    )
    return rule, question


def _substantial_clause(clause: str) -> bool:
    cleaned = clause.strip(" .;,\n")
    if len(cleaned) < 24:
        return False
    return bool(
        re.search(
            r"\b(must|shall|eligible|income|resident|holding|caste|religion|"
            r"age|category|required)\b",
            cleaned,
            re.IGNORECASE,
        )
    )


def _clauses(text: str) -> list[str]:
    """Split criteria into clauses so unmatched wording can be flagged."""
    parts = re.split(
        r"(?<=[.;])\s+|(?:,\s+|\s+)(?:and\s+)?(?=the applicant\b)",
        text,
        flags=re.IGNORECASE,
    )
    return [part.strip(" .;,") for part in parts if part.strip(" .;,")]


def _clause_covered(clause: str, rules: list[EligibilityRule]) -> bool:
    lowered = clause.lower()
    for rule in rules:
        snippet = rule.source_excerpt.lower()
        if snippet and snippet in lowered:
            return True
        if rule.field_name == "annual_household_income" and "income" in lowered:
            return True
        if (
            rule.field_name == "resident_of_district_at_least_one_year"
            and "resident" in lowered
        ):
            return True
        if (
            rule.field_name == "holds_income_certificate_this_year"
            and "income certificate" in lowered
        ):
            return True
    return False


def required_document_types(required_documents: str | None) -> list[str]:
    """Human-readable required document labels from Regulation.required_documents."""
    if not required_documents or not required_documents.strip():
        return []
    proofs = _PROOF_OF.findall(required_documents)
    if proofs:
        labels = []
        seen: set[str] = set()
        for kind in proofs:
            label = f"Proof of {kind.lower()}"
            key = label.lower()
            if key not in seen:
                seen.add(key)
                labels.append(label)
        return labels

    parts = re.split(r"\s*(?:,|;|\band\b)\s*", required_documents)
    labels = []
    for part in parts:
        item = part.strip(" .")
        if len(item) < 3:
            continue
        if item.lower().startswith("the applicant must"):
            continue
        labels.append(item)
    return labels


def extract_programme(
    *,
    eligibility_criteria: str | None,
    required_documents: str | None,
    scheme_name: str = "",
    regulation_id: int | None = None,
) -> ExtractedProgramme:
    """Turn stored regulation fields into rules and questions.

    Only patterns that can be read unambiguously become rules. Anything else
    is recorded as unsupported so the evaluator can return manual_review.
    """
    rules: list[EligibilityRule] = []
    questions: list[EligibilityQuestion] = []
    unsupported: list[UnsupportedCriterion] = []
    text = (eligibility_criteria or "").strip()

    if text:
        for extractor in (_income_rule, _residence_rule, _existing_certificate_rule):
            found = extractor(text)
            if found is None:
                continue
            rule, question = found
            rules.append(rule)
            questions.append(question)

        if not rules:
            unsupported.append(
                UnsupportedCriterion(
                    excerpt=text[:240],
                    reason=(
                        "The eligibility wording could not be converted into a "
                        "deterministic rule."
                    ),
                )
            )
        else:
            for clause in _clauses(text):
                if not _substantial_clause(clause):
                    continue
                if _clause_covered(clause, rules):
                    continue
                # Lead-in such as "An applicant is eligible ... if" is ignored
                # when it does not state a separate requirement.
                if re.match(r"^(an?\s+)?applicant is eligible\b", clause, re.I):
                    continue
                unsupported.append(
                    UnsupportedCriterion(
                        excerpt=clause[:240],
                        reason=(
                            "This criterion could not be converted into a "
                            "deterministic rule."
                        ),
                    )
                )

    documents = tuple(required_document_types(required_documents))
    return ExtractedProgramme(
        rules=tuple(rules),
        questions=tuple(questions),
        unsupported=tuple(unsupported),
        required_document_types=documents,
    )


def questionnaire_for_programme(
    programme: ExtractedProgramme,
    *,
    regulation_id: int | None,
    scheme_name: str,
) -> Questionnaire:
    return Questionnaire(
        regulation_id=regulation_id,
        scheme_name=scheme_name,
        questions=list(programme.questions),
        required_document_types=list(programme.required_document_types),
        unsupported_criteria=[item.excerpt for item in programme.unsupported],
    )
