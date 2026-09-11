"""Rule matching for uploaded documents.

Each rule is a small object with a name and a check. A failed check returns the
exact reason it failed, so a rejection always names a real broken rule and no
reason is ever invented.

Rules live here rather than in the API routes, so they can be read, tested and
extended in one place.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from ai_modules.document_verification.field_extraction import (
    ExtractedFields,
    normalise_name,
    parse_amount,
)

# Human labels used in rejection reasons.
FIELD_LABELS = {
    "name": "applicant name",
    "address": "address",
    "date": "issue date",
    "certificate_number": "certificate number",
    "document_number": "identity document number",
    "income": "income",
    "issuing_authority": "issuing authority",
    "reference_number": "reference number",
}


@dataclass(frozen=True)
class RegulationRules:
    """The regulation a document is checked against.

    A plain dataclass, so this module never imports the database models.
    """

    regulation_id: int | None = None
    scheme_name: str = ""
    department: str | None = None
    eligibility_criteria: str | None = None
    required_documents: str | None = None
    circular_reference: str | None = None


@dataclass(frozen=True)
class DocumentContext:
    """Everything a rule is allowed to look at."""

    document_type: str
    text: str
    fields: ExtractedFields
    citizen_name: str | None = None
    regulation: RegulationRules | None = None
    today: date = field(default_factory=date.today)


@dataclass(frozen=True)
class RuleFailure:
    """One broken rule and why."""

    rule: str
    reason: str


@dataclass
class RuleMatchResult:
    """The outcome of checking every applicable rule."""

    applied_rules: list[str] = field(default_factory=list)
    failures: list[RuleFailure] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def reason(self) -> str | None:
        """All failure reasons, in the order the rules ran."""
        if not self.failures:
            return None
        return " ".join(failure.reason for failure in self.failures)


# --- individual rules -------------------------------------------------------


@dataclass(frozen=True)
class RequiredField:
    """The document must contain a field."""

    field_name: str

    @property
    def name(self) -> str:
        return f"required_field:{self.field_name}"

    def check(self, context: DocumentContext) -> RuleFailure | None:
        if context.fields.has(self.field_name):
            return None
        label = FIELD_LABELS.get(self.field_name, self.field_name)
        return RuleFailure(
            rule=self.name,
            reason=f"Required {label} field could not be found on the document.",
        )


@dataclass(frozen=True)
class NumericField:
    """A field must be readable as a number."""

    field_name: str

    @property
    def name(self) -> str:
        return f"numeric_field:{self.field_name}"

    def check(self, context: DocumentContext) -> RuleFailure | None:
        raw = context.fields.get(self.field_name)
        if raw is None:
            # RequiredField reports the missing field; no duplicate reason.
            return None
        if parse_amount(raw) is None:
            label = FIELD_LABELS.get(self.field_name, self.field_name)
            return RuleFailure(
                rule=self.name,
                reason=f"The {label} value '{raw}' could not be read as a number.",
            )
        return None


@dataclass(frozen=True)
class NameMatchesCitizen:
    """The name on the document must match the registered citizen profile."""

    name = "name_matches_citizen"

    def check(self, context: DocumentContext) -> RuleFailure | None:
        document_name = normalise_name(context.fields.get("name"))
        citizen_name = normalise_name(context.citizen_name)
        if not document_name or not citizen_name:
            # Nothing to compare; RequiredField covers a missing name.
            return None

        if document_name == citizen_name:
            return None
        # Allow extra words on the document, such as a middle name.
        document_words = set(document_name.split())
        citizen_words = set(citizen_name.split())
        if citizen_words and citizen_words.issubset(document_words):
            return None

        return RuleFailure(
            rule=self.name,
            reason=(
                f"Applicant name on the document ('{context.fields.get('name')}') "
                f"does not match the registered citizen profile "
                f"('{context.citizen_name}')."
            ),
        )


@dataclass(frozen=True)
class IssueDateNotInFuture:
    """A document cannot have been issued in the future."""

    name = "issue_date_not_in_future"
    _FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %m %Y", "%d-%m-%y", "%d/%m/%y")

    def check(self, context: DocumentContext) -> RuleFailure | None:
        raw = context.fields.get("date")
        if not raw:
            return None

        for pattern in self._FORMATS:
            try:
                issued = datetime.strptime(raw.strip(), pattern).date()
            except ValueError:
                continue
            if issued > context.today:
                return RuleFailure(
                    rule=self.name,
                    reason=f"The issue date on the document ({raw}) is in the future.",
                )
            return None
        # An unparseable date is not treated as a failure here; the format
        # varies too much between offices to reject on it.
        return None


@dataclass(frozen=True)
class DocumentTypeAllowedByRegulation:
    """The document type must be one the scheme actually asks for."""

    name = "document_type_allowed_by_regulation"
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
    }

    def check(self, context: DocumentContext) -> RuleFailure | None:
        regulation = context.regulation
        if regulation is None or not regulation.required_documents:
            return None

        required = set(re.split(r"[^a-z]+", regulation.required_documents.lower()))
        required -= {""}
        distinctive = [
            word
            for word in re.split(r"[^a-z]+", context.document_type.lower())
            if word and word not in self._GENERIC_WORDS
        ]
        if not distinctive:
            return None
        # A distinctive word of the document type must appear in the scheme's
        # required-documents list. Generic words such as "proof" are ignored.
        if any(word in required for word in distinctive):
            return None

        return RuleFailure(
            rule=self.name,
            reason=(
                f"The document type '{context.document_type}' is not listed in the "
                f"required documents for {regulation.scheme_name}."
            ),
        )


@dataclass(frozen=True)
class IncomeWithinRegulationLimit:
    """Income on the document must respect the scheme's income limit.

    The limit is only applied when the eligibility text states it in a form
    this rule can read, so no limit is ever assumed.
    """

    name = "income_within_regulation_limit"
    _LIMIT = re.compile(
        r"income\s+(?:is\s+)?(?:below|under|less\s+than|not\s+exceeding|upto|up\s+to)"
        r"\s*(?:rs\.?|inr|₹)?\s*([\d][\d,]{2,15})",
        re.IGNORECASE,
    )

    def limit_for(self, context: DocumentContext) -> int | None:
        regulation = context.regulation
        if regulation is None or not regulation.eligibility_criteria:
            return None
        match = self._LIMIT.search(regulation.eligibility_criteria)
        return parse_amount(match.group(1)) if match else None

    def check(self, context: DocumentContext) -> RuleFailure | None:
        limit = self.limit_for(context)
        income = parse_amount(context.fields.get("income"))
        if limit is None or income is None:
            return None

        if income > limit:
            return RuleFailure(
                rule=self.name,
                reason=(
                    f"The income on the document ({income:,}) exceeds the limit of "
                    f"{limit:,} in the eligibility criteria for "
                    f"{context.regulation.scheme_name}."
                ),
            )
        return None


# --- rule sets --------------------------------------------------------------


def normalise_document_type(document_type: str) -> str:
    """Turn "Income Certificate" into "income_certificate"."""
    words = [word for word in re.split(r"[^a-z0-9]+", (document_type or "").lower()) if word]
    return "_".join(words)


# The rules that apply to each document type we know how to check.
DOCUMENT_RULES: dict[str, list] = {
    "income_certificate": [
        RequiredField("name"),
        RequiredField("certificate_number"),
        RequiredField("issuing_authority"),
        RequiredField("income"),
        NumericField("income"),
        NameMatchesCitizen(),
        IssueDateNotInFuture(),
    ],
    "identity_proof": [
        RequiredField("name"),
        RequiredField("document_number"),
        NameMatchesCitizen(),
    ],
    "residence_proof": [
        RequiredField("name"),
        RequiredField("address"),
        RequiredField("issuing_authority"),
        NameMatchesCitizen(),
    ],
}

# Rules that apply to every document once its regulation is known.
REGULATION_RULES = [
    DocumentTypeAllowedByRegulation(),
    IncomeWithinRegulationLimit(),
]

SUPPORTED_DOCUMENT_TYPES = sorted(DOCUMENT_RULES)


def rules_for(document_type: str) -> list | None:
    """The rule set for a document type, or None if we have no rules for it."""
    return DOCUMENT_RULES.get(normalise_document_type(document_type))


class RuleMatcher:
    """Checks a document against its rule set and the regulation's rules."""

    def match(self, context: DocumentContext) -> RuleMatchResult:
        result = RuleMatchResult()

        applicable = rules_for(context.document_type) or []
        if context.regulation is not None:
            applicable = applicable + REGULATION_RULES

        for rule in applicable:
            result.applied_rules.append(rule.name)
            failure = rule.check(context)
            if failure is not None:
                result.failures.append(failure)

        return result
