"""Citizen Feedback Sentiment Analysis.

Local, deterministic lexicon and rule classifiers. Feedback text is never sent
to Groq, OpenAI, or any other external API. This is not a transformer or
trained machine-learning model.
"""

from ai_modules.feedback_sentiment.analyzer import (
    FeedbackAnalysis,
    analyze_feedback,
    escalation_required,
)
from ai_modules.feedback_sentiment.errors import (
    EmptyFeedbackError,
    FeedbackSentimentError,
)
from ai_modules.feedback_sentiment.sentiment import analyze_sentiment
from ai_modules.feedback_sentiment.urgency import analyze_urgency

__all__ = [
    "EmptyFeedbackError",
    "FeedbackAnalysis",
    "FeedbackSentimentError",
    "analyze_feedback",
    "analyze_sentiment",
    "analyze_urgency",
    "escalation_required",
]
