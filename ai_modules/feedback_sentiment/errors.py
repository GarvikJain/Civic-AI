"""Errors for the local feedback sentiment engine.

These are raised by the analyzer, not by FastAPI.
"""


class FeedbackSentimentError(ValueError):
    """Base error for feedback sentiment or urgency analysis."""


class EmptyFeedbackError(FeedbackSentimentError):
    """The comments string is empty or only whitespace."""
