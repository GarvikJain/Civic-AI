"""Proactive Eligibility Nudge.

Deterministic, regulation-backed screening. The actual eligible /
potentially_ineligible / manual_review decision is never made by an LLM.
Citizen answers are not sent to Groq.

Eligibility Nudge is an advisory screening feature. It does not constitute a
final government eligibility decision.
"""

from ai_modules.eligibility_nudge.evaluator import (
    RESULT_ELIGIBLE,
    RESULT_MANUAL_REVIEW,
    RESULT_POTENTIALLY_INELIGIBLE,
    EligibilityEvaluation,
    evaluate_rules,
    validate_answers,
)
from ai_modules.eligibility_nudge.questionnaire import EligibilityQuestion, Questionnaire

__all__ = [
    "EligibilityEvaluation",
    "EligibilityQuestion",
    "Questionnaire",
    "RESULT_ELIGIBLE",
    "RESULT_MANUAL_REVIEW",
    "RESULT_POTENTIALLY_INELIGIBLE",
    "evaluate_rules",
    "validate_answers",
]
