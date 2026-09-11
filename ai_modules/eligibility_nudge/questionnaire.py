"""Server-controlled questionnaire items.

The client never defines questions. It only supplies answers keyed by
question_id / field_name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ANSWER_TYPES = (
    "boolean",
    "integer",
    "decimal",
    "string",
    "date",
    "choice",
)


@dataclass(frozen=True)
class EligibilityQuestion:
    """One question shown to the citizen."""

    question_id: str
    field_name: str
    question_text: str
    answer_type: str
    required: bool = True
    options: tuple[str, ...] = ()

    def as_public_dict(self) -> dict[str, Any]:
        payload = {
            "question_id": self.question_id,
            "field_name": self.field_name,
            "question_text": self.question_text,
            "answer_type": self.answer_type,
            "required": self.required,
        }
        if self.options:
            payload["options"] = list(self.options)
        return payload


@dataclass
class Questionnaire:
    """Questions and document hints derived from one regulation."""

    regulation_id: int | None
    scheme_name: str
    questions: list[EligibilityQuestion] = field(default_factory=list)
    required_document_types: list[str] = field(default_factory=list)
    advisory_notice: str = (
        "Eligibility Nudge is an advisory screening feature. It does not "
        "constitute a final government eligibility decision. You may still "
        "continue with the service after a warning."
    )
    unsupported_criteria: list[str] = field(default_factory=list)

    def question_by_id(self, question_id: str) -> EligibilityQuestion | None:
        for question in self.questions:
            if question.question_id == question_id or question.field_name == question_id:
                return question
        return None

    def required_ids(self) -> list[str]:
        return [q.question_id for q in self.questions if q.required]
