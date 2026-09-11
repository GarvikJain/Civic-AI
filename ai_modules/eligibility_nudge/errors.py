"""Errors for the eligibility nudge engine.

These are raised by the rule engine, not by FastAPI.
"""


class EligibilityError(ValueError):
    """Base error for eligibility evaluation."""


class InvalidAnswersError(EligibilityError):
    """Citizen answers do not match the server-defined questionnaire."""


class UnsupportedRegulationError(EligibilityError):
    """The regulation text cannot be converted into deterministic rules."""
