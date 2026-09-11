"""Lexicon-and-rule sentiment classifier.

This is **not** a transformer, LLM, or trained scikit-learn model. It scores
feedback with a fixed word/phrase list, simple negation, and intensifiers.
The same text always produces the same label. Citizen comments are never sent
to Groq or any other external API.

Labels (exactly one):
    positive | neutral | negative

Scoring:
    1. Normalise to lowercase words.
    2. Add the weights of matched multi-word phrases (longest first).
    3. Score remaining tokens from the unigram lexicons.
    4. A negator in the three tokens before a lexicon hit flips its sign
       ("not helpful" is negative; "not bad" is positive).
    5. An intensifier in the two tokens before a hit multiplies its weight
       by 1.5 ("extremely slow").

Thresholds (documented, fixed):
    score >= POSITIVE_THRESHOLD (0.8)  -> positive
    score <= NEGATIVE_THRESHOLD (-0.8) -> negative
    otherwise                          -> neutral
"""

from __future__ import annotations

import re

from ai_modules.feedback_sentiment.errors import EmptyFeedbackError

SENTIMENT_POSITIVE = "positive"
SENTIMENT_NEUTRAL = "neutral"
SENTIMENT_NEGATIVE = "negative"

POSITIVE_THRESHOLD = 0.8
NEGATIVE_THRESHOLD = -0.8

_TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")

NEGATORS = frozenset(
    {
        "not",
        "never",
        "no",
        "nobody",
        "neither",
        "without",
        "n't",
        "cannot",
        "can't",
        "don't",
        "didn't",
        "doesn't",
        "isn't",
        "wasn't",
        "aren't",
        "weren't",
        "won't",
    }
)

INTENSIFIERS = frozenset(
    {
        "extremely",
        "very",
        "really",
        "highly",
        "incredibly",
        "so",
        "quite",
        "seriously",
        "truly",
        "especially",
    }
)

# Longest phrases first. Weights are added to the running score.
POSITIVE_PHRASES: tuple[tuple[tuple[str, ...], float], ...] = (
    (("extremely", "helpful"), 2.5),
    (("very", "helpful"), 2.0),
    (("highly", "recommend"), 2.0),
    (("well", "done"), 1.5),
    (("thank", "you"), 1.2),
)

NEGATIVE_PHRASES: tuple[tuple[tuple[str, ...], float], ...] = (
    (("nobody", "helped"), -2.0),
    (("no", "one", "helped"), -2.0),
    (("no", "response"), -2.0),
    (("no", "reply"), -2.0),
    (("not", "helpful"), -1.8),
    (("did", "not", "help"), -1.8),
    (("did", "nothing"), -1.5),
    (("waste", "of", "time"), -1.8),
    (("still", "waiting"), -1.2),
)

POSITIVE_UNIGRAMS: dict[str, float] = {
    "helpful": 1.5,
    "excellent": 2.0,
    "outstanding": 2.0,
    "amazing": 1.5,
    "wonderful": 1.5,
    "great": 1.5,
    "love": 1.5,
    "satisfied": 1.5,
    "appreciate": 1.2,
    "pleased": 1.2,
    "efficient": 1.2,
    "quick": 1.2,
    "fast": 1.2,
    "best": 1.2,
    "good": 1.0,
    "kind": 1.0,
    "polite": 1.0,
    "professional": 1.0,
    "friendly": 1.0,
    "courteous": 1.0,
    "smooth": 1.0,
    "easy": 1.0,
    "happy": 1.0,
    "thanks": 1.0,
    "thank": 1.0,
    "clear": 0.6,
    "fine": 0.4,
    "okay": 0.4,
    "ok": 0.3,
}

NEGATIVE_UNIGRAMS: dict[str, float] = {
    "terrible": 2.0,
    "worst": 2.0,
    "horrible": 1.8,
    "awful": 1.8,
    "useless": 1.5,
    "rude": 1.5,
    "unhelpful": 1.5,
    "disappointed": 1.5,
    "incompetent": 1.5,
    "unacceptable": 1.5,
    "ignored": 1.5,
    "corrupt": 1.5,
    "harassment": 1.5,
    "fraud": 1.5,
    "unsafe": 1.5,
    "slow": 1.2,
    "failed": 1.2,
    "failure": 1.2,
    "poor": 1.2,
    "frustrating": 1.2,
    "pending": 1.2,
    "unresolved": 1.2,
    "bad": 1.2,
    "angry": 1.0,
    "delayed": 1.0,
    "broken": 1.0,
    "nobody": 1.0,
    "complaint": 0.8,
    "issue": 0.8,
    "problem": 0.8,
    "delay": 0.8,
    "waiting": 0.6,
}


def normalize_text(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    lowered = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    cleaned = re.sub(r"[^a-z0-9'\s]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def tokenize(text: str) -> list[str]:
    """Split normalised feedback into lowercase word tokens."""
    return _TOKEN_RE.findall(normalize_text(text))


def _match_phrases(
    tokens: list[str],
    phrases: tuple[tuple[tuple[str, ...], float], ...],
) -> tuple[list[str], float]:
    """Score phrase hits and return the leftover tokens."""
    leftover: list[str] = []
    score = 0.0
    index = 0
    ordered = sorted(phrases, key=lambda item: len(item[0]), reverse=True)
    while index < len(tokens):
        matched = False
        for words, weight in ordered:
            width = len(words)
            if tokens[index : index + width] == list(words):
                score += weight
                index += width
                matched = True
                break
        if not matched:
            leftover.append(tokens[index])
            index += 1
    return leftover, score


def _is_negated(tokens: list[str], index: int) -> bool:
    start = max(0, index - 3)
    return any(token in NEGATORS for token in tokens[start:index])


def _intensifier(tokens: list[str], index: int) -> float:
    start = max(0, index - 2)
    if any(token in INTENSIFIERS for token in tokens[start:index]):
        return 1.5
    return 1.0


def score_sentiment(text: str) -> float:
    """Return the numeric sentiment score used by analyze_sentiment."""
    tokens = tokenize(text)
    if not tokens:
        raise EmptyFeedbackError("Feedback text is empty.")

    leftover, score = _match_phrases(tokens, POSITIVE_PHRASES + NEGATIVE_PHRASES)
    for index, token in enumerate(leftover):
        if token in NEGATORS or token in INTENSIFIERS:
            continue
        if token in POSITIVE_UNIGRAMS:
            weight = POSITIVE_UNIGRAMS[token] * _intensifier(leftover, index)
            score += -weight if _is_negated(leftover, index) else weight
        elif token in NEGATIVE_UNIGRAMS:
            weight = NEGATIVE_UNIGRAMS[token] * _intensifier(leftover, index)
            score += weight if _is_negated(leftover, index) else -weight
    return score


def analyze_sentiment(text: str) -> str:
    """Classify feedback as positive, neutral or negative."""
    if text is None or not str(text).strip():
        raise EmptyFeedbackError("Feedback text is empty.")
    score = score_sentiment(text)
    if score >= POSITIVE_THRESHOLD:
        return SENTIMENT_POSITIVE
    if score <= NEGATIVE_THRESHOLD:
        return SENTIMENT_NEGATIVE
    return SENTIMENT_NEUTRAL
