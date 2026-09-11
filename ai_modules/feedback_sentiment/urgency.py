"""Rule-based urgency classifier.

Urgency is **not** inferred from sentiment. A complaint can be negative and
still low urgency. Neutral or positive text can be high urgency when it
explicitly reports an emergency or safety issue.

This is a deterministic phrase/token matcher, not a trained model. Citizen
comments are never sent to Groq or any other external API.

Labels (exactly one):
    low | medium | high

Rules (first match wins):
    1. A high-urgency indicator that is not locally negated -> high
    2. Else a medium-urgency indicator that is not locally negated -> medium
    3. Else -> low

High-urgency concepts (explicit):
    immediate action, emergency, unsafe situation, threat, harassment, fraud,
    corruption, serious issue / serious service failure, legal action.

Medium-urgency concepts (delay / unanswered, not emergencies):
    pending for weeks, no response, still waiting, ignored, repeated attempts.

A negator in the three tokens before an indicator suppresses it
("this is not urgent" stays low).
"""

from __future__ import annotations

from ai_modules.feedback_sentiment.errors import EmptyFeedbackError
from ai_modules.feedback_sentiment.sentiment import NEGATORS, tokenize

URGENCY_LOW = "low"
URGENCY_MEDIUM = "medium"
URGENCY_HIGH = "high"

# Longest first so "serious service failure" wins over "serious".
HIGH_PHRASES: tuple[tuple[str, ...], ...] = (
    ("serious", "service", "failure"),
    ("life", "threatening"),
    ("immediate", "action"),
    ("immediate", "assistance"),
    ("need", "immediate"),
    ("unsafe", "situation"),
    ("legal", "action"),
    ("serious", "issue"),
    ("serious", "problem"),
)

HIGH_UNIGRAMS = frozenset(
    {
        "immediate",
        "immediately",
        "emergency",
        "emergencies",
        "urgent",
        "urgently",
        "unsafe",
        "danger",
        "dangerous",
        "threat",
        "threatened",
        "threatening",
        "harassment",
        "harassed",
        "harass",
        "fraud",
        "fraudulent",
        "corruption",
        "corrupt",
        "assault",
        "violence",
        "lawsuit",
        "bribe",
        "bribery",
    }
)

MEDIUM_PHRASES: tuple[tuple[str, ...], ...] = (
    ("again", "and", "again"),
    ("no", "one", "responded"),
    ("nobody", "responded"),
    ("nobody", "helped"),
    ("no", "one", "helped"),
    ("no", "response"),
    ("no", "reply"),
    ("no", "update"),
    ("no", "updates"),
    ("still", "waiting"),
    ("been", "waiting"),
    ("been", "pending"),
    ("pending", "for"),
    ("for", "weeks"),
    ("for", "days"),
    ("for", "months"),
    ("multiple", "times"),
    ("several", "times"),
    ("long", "delay"),
    ("ignored", "me"),
)

MEDIUM_UNIGRAMS = frozenset(
    {
        "ignored",
        "unresolved",
        "delayed",
        "delays",
    }
)


def _span_negated(tokens: list[str], start: int) -> bool:
    window = tokens[max(0, start - 3) : start]
    return any(token in NEGATORS for token in window)


def _first_phrase(
    tokens: list[str], phrases: tuple[tuple[str, ...], ...]
) -> tuple[str, ...] | None:
    ordered = sorted(phrases, key=len, reverse=True)
    index = 0
    while index < len(tokens):
        for words in ordered:
            width = len(words)
            if tokens[index : index + width] == list(words):
                if not _span_negated(tokens, index):
                    return words
                index += width
                break
        else:
            index += 1
    return None


def _first_unigram(tokens: list[str], lexicon: frozenset[str]) -> str | None:
    for index, token in enumerate(tokens):
        if token in lexicon and not _span_negated(tokens, index):
            return token
    return None


def analyze_urgency(text: str) -> str:
    """Classify feedback urgency as low, medium or high."""
    if text is None or not str(text).strip():
        raise EmptyFeedbackError("Feedback text is empty.")
    tokens = tokenize(text)
    if not tokens:
        raise EmptyFeedbackError("Feedback text is empty.")
    if _first_phrase(tokens, HIGH_PHRASES) or _first_unigram(tokens, HIGH_UNIGRAMS):
        return URGENCY_HIGH
    if _first_phrase(tokens, MEDIUM_PHRASES) or _first_unigram(
        tokens, MEDIUM_UNIGRAMS
    ):
        return URGENCY_MEDIUM
    return URGENCY_LOW
