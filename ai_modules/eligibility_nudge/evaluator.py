"""Evaluate questionnaire answers against extracted eligibility rules.

The decision never uses an LLM. The same answers against the same rules always
produce the same result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ai_modules.eligibility_nudge.errors import InvalidAnswersError
from ai_modules.eligibility_nudge.questionnaire import EligibilityQuestion, Questionnaire
from ai_modules.eligibility_nudge.rules import EligibilityRule, ExtractedProgramme

RESULT_ELIGIBLE = "eligible"
RESULT_POTENTIALLY_INELIGIBLE = "potentially_ineligible"
RESULT_MANUAL_REVIEW = "manual_review"

EXPLANATIONS = {
    RESULT_ELIGIBLE: (
        "Your responses satisfy the explicit eligibility criteria currently "
        "available in the regulation."
    ),
    RESULT_POTENTIALLY_INELIGIBLE: (
        "One or more responses do not satisfy the explicit criteria. Review "
        "the indicated requirement before proceeding. This is an advisory "
        "warning, not a legal determination that you are ineligible."
    ),
    RESULT_MANUAL_REVIEW: (
        "The available regulation text contains a criterion that cannot be "
        "evaluated automatically. Manual verification is recommended."
    ),
}


@dataclass
class RuleOutcome:
    rule_id: str
    summary: str
    passed: bool | None
    detail: str


@dataclass
class EligibilityEvaluation:
    result: str
    warning_issued: bool
    explanation: str
    failed_criteria: list[str] = field(default_factory=list)
    uncertain_criteria: list[str] = field(default_factory=list)
    missing_documents: list[str] = field(default_factory=list)
    outcomes: list[RuleOutcome] = field(default_factory=list)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    raise InvalidAnswersError("A boolean answer must be true or false.")


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        raise InvalidAnswersError("A number answer cannot be a boolean.")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        digits = value.replace(",", "").replace(" ", "").strip()
        if digits.isdigit() or (digits.startswith("-") and digits[1:].isdigit()):
            return int(digits)
    raise InvalidAnswersError("A numeric answer must be a whole number in rupees.")


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        raise InvalidAnswersError("A number answer cannot be a boolean.")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError as error:
            raise InvalidAnswersError("A decimal answer must be numeric.") from error
    raise InvalidAnswersError("A decimal answer must be numeric.")


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError as error:
            raise InvalidAnswersError("A date answer must be YYYY-MM-DD.") from error
    raise InvalidAnswersError("A date answer must be YYYY-MM-DD.")


def _as_string(value: Any) -> str:
    if value is None:
        raise InvalidAnswersError("A text answer is required.")
    text = str(value).strip()
    if not text:
        raise InvalidAnswersError("A text answer is required.")
    return text


def coerce_answer(question: EligibilityQuestion, raw: Any) -> Any:
    if question.answer_type == "boolean":
        return _as_bool(raw)
    if question.answer_type == "integer":
        return _as_int(raw)
    if question.answer_type == "decimal":
        return _as_float(raw)
    if question.answer_type == "date":
        return _as_date(raw)
    if question.answer_type == "choice":
        text = _as_string(raw)
        if question.options and text not in question.options:
            raise InvalidAnswersError(
                f"'{text}' is not a valid choice for {question.question_id}."
            )
        return text
    return _as_string(raw)


def validate_answers(questionnaire: Questionnaire, answers: dict[str, Any]) -> dict[str, Any]:
    """Reject unknown keys, missing required answers, and wrong types."""
    if not isinstance(answers, dict):
        raise InvalidAnswersError("Answers must be an object of field values.")

    allowed = {q.question_id for q in questionnaire.questions} | {
        q.field_name for q in questionnaire.questions
    }
    unknown = [key for key in answers if key not in allowed]
    if unknown:
        raise InvalidAnswersError(
            "Unknown answer fields: " + ", ".join(sorted(unknown))
        )

    coerced: dict[str, Any] = {}
    for question in questionnaire.questions:
        raw = answers.get(question.question_id, answers.get(question.field_name))
        if raw is None or raw == "":
            if question.required:
                raise InvalidAnswersError(
                    f"Missing required answer: {question.question_id}"
                )
            continue
        coerced[question.field_name] = coerce_answer(question, raw)
    return coerced


def _compare(operator: str, left: Any, right: Any) -> bool:
    if operator == "equals":
        return left == right
    if operator == "not_equals":
        return left != right
    if operator == "greater_than":
        return left > right
    if operator == "greater_than_or_equal":
        return left >= right
    if operator == "less_than":
        return left < right
    if operator == "less_than_or_equal":
        return left <= right
    if operator == "in":
        return left in right
    if operator == "required":
        return left is not None and left != "" and left is not False
    raise InvalidAnswersError(f"Unsupported operator: {operator}")


def evaluate_rules(
    programme: ExtractedProgramme,
    answers: dict[str, Any],
    *,
    missing_documents: list[str] | None = None,
) -> EligibilityEvaluation:
    """Apply every extracted rule. Unsupported criteria force manual_review."""
    outcomes: list[RuleOutcome] = []
    failed: list[str] = []
    for rule in programme.rules:
        left = answers.get(rule.field_name)
        passed = _compare(rule.operator, left, rule.value)
        detail = rule.summary
        if not passed:
            failed.append(rule.summary)
            detail = f"Not satisfied: {rule.summary}"
        outcomes.append(
            RuleOutcome(
                rule_id=rule.rule_id,
                summary=rule.summary,
                passed=passed,
                detail=detail,
            )
        )

    uncertain = [item.excerpt for item in programme.unsupported]
    missing = list(missing_documents or [])

    if failed:
        result = RESULT_POTENTIALLY_INELIGIBLE
    elif uncertain or not programme.rules:
        result = RESULT_MANUAL_REVIEW
    else:
        result = RESULT_ELIGIBLE

    explanation = EXPLANATIONS[result]
    if failed:
        explanation = explanation + " Failed criteria: " + "; ".join(failed)
    if uncertain and result == RESULT_MANUAL_REVIEW:
        explanation = explanation + " Uncertain criteria: " + "; ".join(uncertain)
    if missing:
        explanation = (
            explanation
            + " Required document may be missing: "
            + "; ".join(missing)
            + "."
        )

    warning = result != RESULT_ELIGIBLE or bool(missing)
    return EligibilityEvaluation(
        result=result,
        warning_issued=warning,
        explanation=explanation,
        failed_criteria=failed,
        uncertain_criteria=uncertain,
        missing_documents=missing,
        outcomes=outcomes,
    )
