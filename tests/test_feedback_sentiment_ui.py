"""Frontend presentation checks for Feedback Sentiment."""

import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

from utils.auth_store import COOKIE_NAME, DictTokenStore

PAGE = FRONTEND / "pages" / "6_Feedback_Sentiment.py"


def test_page_source_keeps_feedback_api_contract():
    page = PAGE.read_text(encoding="utf-8")
    assert '"/queue/appointments"' in page
    assert '"/feedback"' in page
    assert 'st.button("Submit feedback", type="primary")' in page
    assert 'st.selectbox(' in page
    assert '"Completed appointment"' in page
    assert 'st.text_area(' in page
    assert 'max_chars=2000' in page
    assert "height=160" in page
    assert '"appointment_id": chosen["appointment_id"]' in page
    assert '"comments": comments.strip()' in page
    assert "Only citizens can submit feedback for their own appointments." in page
    assert 'st.error("Backend is not reachable.")' in page
    assert "This feedback was flagged for officer attention." in page
    assert "Feedback can be submitted only for a completed appointment that" in page
    assert "does not already have comments." in page
    assert "Please enter a comment before submitting." in page
    assert "st.metric" not in page


def test_page_source_uses_civic_feedback_surfaces():
    page = PAGE.read_text(encoding="utf-8")
    assert "page_hero" in page
    assert "Feedback Sentiment" in page
    assert "Citizen feedback" in page
    assert "civicai-feedback" in page
    assert "civicai-feedback-result" in page
    assert "Flagged for officer attention" in page
    assert "feedback_analysis_rows" in page


def _signed_in(monkeypatch, *, role="citizen", get_impl=None, post_impl=None):
    from streamlit.testing.v1 import AppTest

    import utils.api_client as api_client
    import utils.auth as auth

    store = DictTokenStore({COOKIE_NAME: f"jwt-{role}"})
    monkeypatch.setattr(auth, "get_browser_token_store", lambda: store)

    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/auth/me":
            return {
                "id": 1,
                "email": f"{role}@example.com",
                "role": role,
                "full_name": f"Test {role.title()}",
                "is_active": True,
            }
        if get_impl:
            return get_impl(path, token=token, params=params, timeout=timeout)
        return []

    monkeypatch.setattr(auth, "get", fake_get)
    monkeypatch.setattr(api_client, "get", fake_get)
    monkeypatch.setattr(api_client, "post", post_impl or (lambda *args, **kwargs: {}))
    monkeypatch.setattr(auth, "post", lambda *args, **kwargs: {"access_token": "x"})

    at = AppTest.from_file(str(PAGE), default_timeout=10)
    at.run()
    assert not at.exception
    return at


def _appointment(appointment_id=4, status="completed"):
    return {
        "appointment_id": appointment_id,
        "service_type": "Income Certificate",
        "status": status,
        "appointment_date": "2026-09-10T10:00:00+00:00",
    }


def _get_lists(appointments=None, feedbacks=None):
    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/queue/appointments":
            return appointments if appointments is not None else [_appointment()]
        if path == "/feedback":
            return {"feedbacks": feedbacks or []}
        return {}

    return fake_get


def test_apptest_logged_out_shows_hero(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import utils.auth as auth

    monkeypatch.setattr(auth, "get_browser_token_store", lambda: DictTokenStore())
    at = AppTest.from_file(str(PAGE), default_timeout=10)
    at.run()
    assert not at.exception
    body = " ".join(str(item.value) for item in at.markdown)
    assert "Feedback Sentiment" in body
    assert "Citizen feedback" in body
    assert any(
        "Please sign in from the sidebar to submit feedback." in str(item.value)
        for item in at.info
    )
    assert not any(button.label == "Submit feedback" for button in at.button)


def test_apptest_empty_completed_appointments(monkeypatch):
    at = _signed_in(monkeypatch, get_impl=_get_lists(appointments=[]))
    assert any(item.value == "Submit feedback" for item in at.subheader)
    assert any(
        "Feedback can be submitted only for a completed appointment that "
        "does not already have comments."
        in str(item.value)
        for item in at.info
    )
    assert not any(button.label == "Submit feedback" for button in at.button)


def test_apptest_form_for_completed_appointment(monkeypatch):
    at = _signed_in(monkeypatch, get_impl=_get_lists())
    assert any(button.label == "Submit feedback" for button in at.button)
    assert at.selectbox
    assert at.text_area


def test_apptest_positive_result_uses_human_labels(monkeypatch):
    result = {
        "feedback_id": 11,
        "appointment_id": 4,
        "citizen_id": 1,
        "service_type": "Income Certificate",
        "sentiment": "positive",
        "urgency": "low",
        "escalation_required": False,
        "comments": "The officer was extremely helpful and the process was quick.",
        "date_submitted": "2026-09-12T10:00:00",
    }

    def post_impl(path, payload, token=None, timeout=None):
        assert path == "/feedback"
        assert payload["appointment_id"] == 4
        assert payload["comments"] == result["comments"]
        return result

    at = _signed_in(monkeypatch, get_impl=_get_lists(), post_impl=post_impl)
    at.text_area[0].set_value(result["comments"])
    [button for button in at.button if button.label == "Submit feedback"][0].click().run()
    assert not at.exception
    body = " ".join(str(item.value) for item in at.markdown)
    captions = " ".join(str(item.value) for item in at.success)
    assert "Feedback #11 saved for appointment #4." in captions
    assert "Positive" in body
    assert "Low" in body
    assert result["comments"] in " ".join(str(item.value) for item in at.markdown)
    assert not any(item.value == "positive" for item in at.markdown)
    assert not any(
        "This feedback was flagged for officer attention." in str(item.value)
        for item in at.warning
    )


def test_apptest_escalated_negative_high_urgency(monkeypatch):
    result = {
        "feedback_id": 12,
        "appointment_id": 4,
        "citizen_id": 1,
        "service_type": "Income Certificate",
        "sentiment": "negative",
        "urgency": "high",
        "escalation_required": True,
        "comments": "This is an emergency. The process failed and I was ignored.",
        "date_submitted": "2026-09-12T10:05:00",
    }

    at = _signed_in(
        monkeypatch,
        get_impl=_get_lists(),
        post_impl=lambda *args, **kwargs: result,
    )
    at.text_area[0].set_value(result["comments"])
    [button for button in at.button if button.label == "Submit feedback"][0].click().run()
    body = " ".join(str(item.value) for item in at.markdown)
    assert "Negative" in body
    assert "High" in body
    assert "Flagged for officer attention" in body
    assert any(
        "This feedback was flagged for officer attention." in str(item.value)
        for item in at.warning
    )
    assert not any(item.value == "negative" for item in at.markdown)
    assert not any(item.value == "high" for item in at.markdown)
    assert not any("Backend is not reachable." in str(item.value) for item in at.error)


def test_apptest_officer_forbidden_is_not_sentiment(monkeypatch):
    from requests import HTTPError

    class FakeResponse:
        status_code = 403
        text = "Forbidden"

        def json(self):
            return {"detail": "Forbidden"}

    def get_impl(path, token=None, params=None, timeout=None):
        raise HTTPError(response=FakeResponse())

    at = _signed_in(monkeypatch, role="officer", get_impl=get_impl)
    assert any(
        "Only citizens can submit feedback for their own appointments." in str(item.value)
        for item in at.error
    )
    assert not any(
        "This feedback was flagged for officer attention." in str(item.value)
        for item in at.warning
    )
