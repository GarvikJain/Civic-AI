"""Frontend presentation checks for Eligibility Nudge."""

import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

from utils.auth_store import COOKIE_NAME, DictTokenStore

PAGE = FRONTEND / "pages" / "5_Eligibility_Nudge.py"


def test_page_source_keeps_eligibility_api_contract():
    page = PAGE.read_text(encoding="utf-8")
    assert "/eligibility/questionnaire" in page
    assert '"/eligibility/check"' in page
    assert '"/eligibility/checks"' in page
    assert 'st.button("Check eligibility", type="primary")' in page
    assert 'role == "citizen"' in page
    assert "collect_answer" in page
    assert 'key = f"elig-{question[\'question_id\']}"' in page
    assert 'st.checkbox(label, key=key)' in page
    assert "st.number_input(label, min_value=0, step=1000, key=key)" in page
    assert "st.number_input(label, min_value=0.0, step=0.1, key=key)" in page
    assert "advisory_notice" in page
    assert "This is an advisory screening. It is not a final government decision." in page
    assert "Missing verified documents:" in page
    assert "Failed criteria" in page
    assert 'st.write(result["result"])' not in page
    assert "Approved" not in page
    assert "Guaranteed eligible" not in page
    assert "Application accepted" not in page


def test_page_source_uses_civic_eligibility_surfaces():
    page = PAGE.read_text(encoding="utf-8")
    assert "page_hero" in page
    assert "Eligibility Nudge" in page
    assert "Preliminary guidance" in page
    assert "civicai-scheme" in page
    assert "civicai-questions" in page
    assert "civicai-eligible" in page
    assert "civicai-ineligible" in page
    assert "civicai-manual" in page
    assert "Documents to prepare" in page


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


def _questionnaire():
    return {
        "regulation_id": 1,
        "scheme_name": "Example Income Certificate Scheme",
        "advisory_notice": "Eligibility Nudge is an advisory screening feature.",
        "unsupported_criteria": [],
        "questions": [
            {
                "question_id": "income",
                "field_name": "annual_household_income",
                "question_text": "What is your annual household income?",
                "answer_type": "integer",
                "required": True,
                "options": [],
            }
        ],
        "required_document_types": ["Identity Proof"],
    }


def _get_with_scheme(result=None, previous=None):
    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/regulations":
            return [
                {
                    "regulation_id": 1,
                    "scheme_name": "Example Income Certificate Scheme",
                    "department": "Revenue",
                }
            ]
        if path.startswith("/eligibility/questionnaire/"):
            return _questionnaire()
        if path == "/eligibility/checks":
            return {"checks": previous or []}
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
    assert "Eligibility Nudge" in body
    assert "Preliminary guidance" in body
    assert any(
        "Please sign in from the sidebar to run an eligibility check." in str(item.value)
        for item in at.info
    )


def test_apptest_questionnaire_and_check_button(monkeypatch):
    at = _signed_in(monkeypatch, get_impl=_get_with_scheme())
    assert any(item.value == "Select a scheme" for item in at.subheader)
    assert any(item.value == "Eligibility questions" for item in at.subheader)
    assert any("advisory screening" in str(item.value).lower() for item in at.info)
    assert any(button.label == "Check eligibility" for button in at.button)
    assert at.number_input


def test_apptest_eligible_result_is_not_an_approval(monkeypatch):
    result = {
        "check_id": 1,
        "result": "eligible",
        "explanation": "Your responses satisfy the explicit eligibility criteria currently available in the regulation.",
        "missing_documents": [],
        "warning_issued": False,
        "scheme_name": "Example Income Certificate Scheme",
    }

    def post_impl(path, payload, token=None, timeout=None):
        assert path == "/eligibility/check"
        assert payload["regulation_id"] == 1
        assert "answers" in payload
        return result

    at = _signed_in(monkeypatch, get_impl=_get_with_scheme(), post_impl=post_impl)
    at.number_input[0].set_value(180000)
    [button for button in at.button if button.label == "Check eligibility"][0].click().run()
    assert not at.exception
    labels = [str(item.value) for item in at.markdown]
    assert any(">Eligible<" in item or item == "Eligible" for item in labels)
    assert not any(item == "eligible" for item in labels)
    assert not any("Approved" in item for item in labels)
    assert any("advisory screening" in str(item.value).lower() for item in at.caption)


def test_apptest_potentially_ineligible_and_missing_documents(monkeypatch):
    result = {
        "check_id": 2,
        "result": "potentially_ineligible",
        "explanation": (
            "One or more responses do not satisfy the explicit criteria. "
            "Failed criteria: Total annual household income must be below 250,000 rupees."
        ),
        "missing_documents": ["Identity Proof", "Income Proof"],
        "warning_issued": True,
    }

    at = _signed_in(
        monkeypatch,
        get_impl=_get_with_scheme(),
        post_impl=lambda *args, **kwargs: result,
    )
    [button for button in at.button if button.label == "Check eligibility"][0].click().run()
    labels = [str(item.value) for item in at.markdown]
    captions = [str(item.value) for item in at.caption]
    assert any(">Potentially ineligible<" in item or item == "Potentially ineligible" for item in labels)
    assert sum(1 for item in labels if ">Potentially ineligible<" in item or item == "Potentially ineligible") == 1
    assert not any(item == "potentially_ineligible" for item in labels)
    assert any("**Failed criteria**" in item or item == "**Failed criteria**" for item in labels)
    assert any("250,000 rupees" in item for item in labels)
    assert any("**Documents to prepare**" in item or item == "**Documents to prepare**" for item in labels)
    assert any("Missing verified documents:" in item for item in captions)
    assert any("Identity Proof" in item for item in labels)
    assert any("Income Proof" in item for item in labels)


def test_apptest_officer_cannot_submit_a_check(monkeypatch):
    at = _signed_in(monkeypatch, role="officer", get_impl=_get_with_scheme())
    assert not any(button.label == "Check eligibility" for button in at.button)
    assert any(
        "Citizens submit checks. Staff can review stored results through the API."
        in str(item.value)
        for item in at.caption
    )


def test_apptest_check_http_error_is_not_an_eligibility_result(monkeypatch):
    from requests import HTTPError

    class FakeResponse:
        text = "Check failed"

        def json(self):
            return {"detail": "Check failed"}

    def post_impl(*args, **kwargs):
        raise HTTPError(response=FakeResponse())

    at = _signed_in(monkeypatch, get_impl=_get_with_scheme(), post_impl=post_impl)
    [button for button in at.button if button.label == "Check eligibility"][0].click().run()
    assert not at.exception
    assert any("Check failed" in str(item.value) for item in at.error)
    assert not any(item.value == "Eligible" for item in at.subheader)
    assert not any(item.value == "Potentially ineligible" for item in at.subheader)
    assert not any(item.value == "Manual review" for item in at.subheader)


def test_apptest_manual_review_is_not_an_error(monkeypatch):
    result = {
        "check_id": 3,
        "result": "manual_review",
        "explanation": "The available regulation text contains a criterion that cannot be evaluated automatically.",
        "missing_documents": [],
        "warning_issued": False,
    }
    at = _signed_in(
        monkeypatch,
        get_impl=_get_with_scheme(),
        post_impl=lambda *args, **kwargs: result,
    )
    [button for button in at.button if button.label == "Check eligibility"][0].click().run()
    labels = [str(item.value) for item in at.markdown]
    assert any(">Manual review<" in item or item == "Manual review" for item in labels)
    assert sum(1 for item in labels if ">Manual review<" in item or item == "Manual review") == 1
    assert not any(item == "manual_review" for item in labels)
    assert not any("Backend is not reachable." in str(item.value) for item in at.error)
    assert any("cannot be evaluated automatically" in item for item in labels)
