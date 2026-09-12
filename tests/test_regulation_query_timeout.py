"""Frontend timeout handling for Regulation Assistant queries."""

import sys
from pathlib import Path

import requests

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

from utils.api_client import TIMEOUT_SECONDS, post
from utils.auth_store import COOKIE_NAME, DictTokenStore

PAGE = FRONTEND / "pages" / "1_Regulation_Assistant.py"
CLIENT = FRONTEND / "utils" / "api_client.py"


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _capture_post(monkeypatch):
    captured = {}

    def fake_requests_post(url, json=None, headers=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["timeout"] = timeout
        captured["json"] = json
        return _FakeResponse({"ok": True})

    monkeypatch.setattr("utils.api_client.requests.post", fake_requests_post)
    return captured


def test_regulation_query_uses_120_second_timeout(monkeypatch):
    captured = _capture_post(monkeypatch)
    post("/regulations/query", {"query": "What documents are required?"}, token="jwt")
    assert captured["timeout"] == 120
    assert captured["url"].endswith("/api/v1/regulations/query")


def test_other_posts_keep_the_default_timeout(monkeypatch):
    captured = _capture_post(monkeypatch)
    post("/auth/login", {"email": "a@b.c", "password": "secret"})
    assert captured["timeout"] == TIMEOUT_SECONDS == 10


def test_explicit_ingest_timeout_is_unchanged(monkeypatch):
    captured = _capture_post(monkeypatch)
    post("/regulations/ingest", {}, token="jwt", timeout=180)
    assert captured["timeout"] == 180


def test_page_source_distinguishes_timeout_from_unreachable():
    page = PAGE.read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")
    assert "REGULATION_QUERY_TIMEOUT_SECONDS = 120" in client
    assert 'path == "/regulations/query"' in client
    assert "timeout=180" in page
    assert "except Timeout" in page
    assert "still be initializing" in page
    assert 'st.error("Backend is not reachable.")' in page
    assert "/regulations/query" in page
    assert "Official sources only" in page
    assert "Sources & Citations" in page
    assert "Insufficient evidence" in page


def _signed_in_citizen(monkeypatch, post_impl):
    from streamlit.testing.v1 import AppTest

    import utils.api_client as api_client
    import utils.auth as auth

    store = DictTokenStore({COOKIE_NAME: "jwt-citizen"})
    monkeypatch.setattr(auth, "get_browser_token_store", lambda: store)

    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/auth/me":
            return {
                "id": 1,
                "email": "citizen@example.com",
                "role": "citizen",
                "full_name": "Test Citizen",
                "is_active": True,
            }
        return {}

    monkeypatch.setattr(auth, "get", fake_get)
    monkeypatch.setattr(api_client, "get", fake_get)
    monkeypatch.setattr(api_client, "post", post_impl)
    monkeypatch.setattr(auth, "post", lambda *args, **kwargs: {"access_token": "x"})

    at = AppTest.from_file(str(PAGE), default_timeout=10)
    at.run()
    assert not at.exception
    return at


def _ask(at, question="What documents do I need for an income certificate?"):
    at.text_area[0].set_value(question)
    ask = [button for button in at.button if button.label == "Ask"]
    assert ask
    ask[0].click().run()
    assert not at.exception
    return at


def test_apptest_initial_page_uses_civic_hero(monkeypatch):
    at = _signed_in_citizen(monkeypatch, lambda *args, **kwargs: {})
    body = " ".join(str(item.value) for item in at.markdown)
    assert "Regulation RAG Assistant" in body
    assert "Official sources only" in body
    assert "Ask about a government scheme" in body
    assert not at.error


def test_apptest_successful_regulation_query(monkeypatch):
    def fake_post(path, payload, token=None, timeout=None):
        assert path == "/regulations/query"
        return {
            "answer": "Submit proof of identity and income.",
            "citations": [
                {
                    "scheme_name": "Income Certificate Scheme",
                    "circular_reference": "CIRC/2026/11",
                    "section": "Section 3",
                    "source": "income.txt",
                }
            ],
            "insufficient_evidence": False,
            "evidence_count": 1,
        }

    at = _ask(_signed_in_citizen(monkeypatch, fake_post))
    body = " ".join(str(item.value) for item in at.markdown)
    assert "Submit proof of identity and income." in body or any(
        "Submit proof of identity and income." in str(item.value) for item in at.text
    )
    assert any(item.value == "Sources & Citations" for item in at.subheader)
    assert any(item.value == "Answer" for item in at.subheader)
    assert "Income Certificate Scheme" in body
    assert not at.error


def test_apptest_timeout_is_not_reported_as_unreachable(monkeypatch):
    def fake_post(path, payload, token=None, timeout=None):
        raise requests.Timeout("Read timed out")

    at = _ask(_signed_in_citizen(monkeypatch, fake_post))
    infos = [str(item.value) for item in at.info]
    errors = [str(item.value) for item in at.error]
    assert any("initializing" in message.lower() for message in infos)
    assert not any("not reachable" in message.lower() for message in errors)
    assert not any("initializing" in message.lower() for message in errors)


def test_apptest_connection_error_is_still_unreachable(monkeypatch):
    def fake_post(path, payload, token=None, timeout=None):
        raise requests.ConnectionError("Connection refused")

    at = _ask(_signed_in_citizen(monkeypatch, fake_post))
    errors = [str(item.value) for item in at.error]
    assert any("Backend is not reachable." in message for message in errors)
    assert not any("initializing" in message.lower() for message in errors)


def test_apptest_insufficient_evidence_is_a_warning(monkeypatch):
    def fake_post(path, payload, token=None, timeout=None):
        return {
            "answer": "I could not find sufficient information in the available official regulations to answer this question.",
            "citations": [],
            "insufficient_evidence": True,
            "evidence_count": 0,
        }

    at = _ask(_signed_in_citizen(monkeypatch, fake_post))
    warnings = [str(item.value) for item in at.warning]
    assert any("sufficient information" in message for message in warnings)
    assert any(item.value == "Insufficient evidence" for item in at.subheader)
    assert not any(item.value == "Answer" for item in at.subheader)
