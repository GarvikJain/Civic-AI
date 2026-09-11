"""Combine sentiment and urgency into one deterministic analysis.

Escalation is derived, never accepted from the client:

    escalation_required = (sentiment == "negative") and (urgency == "high")

Negative + medium/low does not escalate. Neutral or positive + high urgency
also does not escalate; officers can still see high-urgency items in later
dashboard work by filtering on urgency.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_modules.feedback_sentiment.sentiment import (
    SENTIMENT_NEGATIVE,
    analyze_sentiment,
)
from ai_modules.feedback_sentiment.urgency import URGENCY_HIGH, analyze_urgency


@dataclass(frozen=True)
class FeedbackAnalysis:
    """Server-side labels for one feedback comment."""

    sentiment: str
    urgency: str
    escalation_required: bool

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "sentiment": self.sentiment,
            "urgency": self.urgency,
            "escalation_required": self.escalation_required,
        }


def escalation_required(sentiment: str, urgency: str) -> bool:
    """Officer attention is required only for negative + high urgency."""
    return sentiment == SENTIMENT_NEGATIVE and urgency == URGENCY_HIGH


def analyze_feedback(text: str) -> FeedbackAnalysis:
    """Run sentiment and urgency and derive escalation_required."""
    sentiment = analyze_sentiment(text)
    urgency = analyze_urgency(text)
    return FeedbackAnalysis(
        sentiment=sentiment,
        urgency=urgency,
        escalation_required=escalation_required(sentiment, urgency),
    )
