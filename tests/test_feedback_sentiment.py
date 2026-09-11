"""Unit tests for the local feedback sentiment and urgency classifiers."""

from pathlib import Path

import pytest

from ai_modules.feedback_sentiment.analyzer import analyze_feedback, escalation_required
from ai_modules.feedback_sentiment.errors import EmptyFeedbackError
from ai_modules.feedback_sentiment.sentiment import (
    NEGATIVE_THRESHOLD,
    POSITIVE_THRESHOLD,
    analyze_sentiment,
    score_sentiment,
)
from ai_modules.feedback_sentiment.urgency import analyze_urgency

ENGINE_DIR = Path(__file__).resolve().parents[1] / "ai_modules" / "feedback_sentiment"


def test_clearly_positive_feedback():
    text = "The officer was extremely helpful and the process was quick."
    assert analyze_sentiment(text) == "positive"
    assert analyze_urgency(text) == "low"
    result = analyze_feedback(text)
    assert result.escalation_required is False


def test_clearly_negative_feedback():
    text = "The officer was rude and the service was terrible."
    assert analyze_sentiment(text) == "negative"
    assert analyze_urgency(text) == "low"


def test_neutral_and_ambiguous_feedback():
    assert analyze_sentiment("The counter opened at the usual time.") == "neutral"
    assert analyze_sentiment("The service was okay.") == "neutral"
    assert analyze_sentiment("It was fine I guess.") == "neutral"


def test_boundary_scores_use_documented_thresholds():
    assert POSITIVE_THRESHOLD == 0.8
    assert NEGATIVE_THRESHOLD == -0.8
    # A single strong positive word sits on the positive side of the threshold.
    assert score_sentiment("good") >= POSITIVE_THRESHOLD
    assert analyze_sentiment("good") == "positive"
    # Weak positive language stays neutral.
    assert score_sentiment("okay") < POSITIVE_THRESHOLD
    assert analyze_sentiment("okay") == "neutral"


def test_negation_flips_nearby_sentiment_words():
    assert analyze_sentiment("The officer was not helpful.") == "negative"
    assert analyze_sentiment("It was not bad.") == "positive"


def test_urgency_low_medium_high():
    assert analyze_urgency("Thank you for a smooth visit.") == "low"
    assert (
        analyze_urgency(
            "My application has been pending for weeks and I have received no response."
        )
        == "medium"
    )
    assert (
        analyze_urgency("I am facing a serious issue and need immediate assistance.")
        == "high"
    )


def test_negative_but_low_urgency():
    result = analyze_feedback("The officer was rude and unhelpful.")
    assert result.sentiment == "negative"
    assert result.urgency == "low"
    assert result.escalation_required is False


def test_negative_and_high_urgency():
    result = analyze_feedback(
        "This is an emergency. The process failed and I was ignored."
    )
    assert result.sentiment == "negative"
    assert result.urgency == "high"
    assert result.escalation_required is True


def test_positive_but_urgent_issue():
    result = analyze_feedback(
        "The officer was extremely helpful. Please treat this as an emergency."
    )
    assert result.sentiment == "positive"
    assert result.urgency == "high"
    assert result.escalation_required is False


def test_not_urgent_is_not_high():
    assert analyze_urgency("This is not urgent and there is no emergency.") == "low"


def test_combined_escalation_matrix():
    assert escalation_required("negative", "high") is True
    assert escalation_required("negative", "medium") is False
    assert escalation_required("negative", "low") is False
    assert escalation_required("neutral", "high") is False
    assert escalation_required("positive", "high") is False


def test_escalation_from_analyze_feedback():
    negative_high = analyze_feedback(
        "I am facing a serious issue and need immediate assistance."
    )
    assert negative_high.sentiment == "negative"
    assert negative_high.urgency == "high"
    assert negative_high.escalation_required is True

    negative_medium = analyze_feedback(
        "My application has been pending for weeks and I have received no response."
    )
    assert negative_medium.sentiment == "negative"
    assert negative_medium.urgency == "medium"
    assert negative_medium.escalation_required is False

    positive_low = analyze_feedback(
        "The officer was extremely helpful and the process was quick."
    )
    assert positive_low.sentiment == "positive"
    assert positive_low.urgency == "low"
    assert positive_low.escalation_required is False


def test_spec_example_slow_nobody_helped():
    result = analyze_feedback(
        "The service was very slow and nobody helped me."
    )
    assert result.sentiment == "negative"
    assert result.urgency == "medium"
    assert result.escalation_required is False


def test_analyzer_is_deterministic():
    text = "My application has been pending for weeks and I have received no response."
    first = analyze_feedback(text)
    second = analyze_feedback(text)
    assert first == second
    assert first.as_dict() == second.as_dict()


def test_empty_text_is_rejected():
    with pytest.raises(EmptyFeedbackError):
        analyze_sentiment("   ")
    with pytest.raises(EmptyFeedbackError):
        analyze_urgency("")
    with pytest.raises(EmptyFeedbackError):
        analyze_feedback("\n")


def test_engine_source_does_not_call_external_llms():
    for path in ENGINE_DIR.glob("*.py"):
        lowered = path.read_text(encoding="utf-8").lower()
        assert "import groq" not in lowered
        assert "from groq" not in lowered
        assert "import openai" not in lowered
        assert "from openai" not in lowered
        assert "import httpx" not in lowered
        assert "from httpx" not in lowered
        assert "requests." not in lowered
