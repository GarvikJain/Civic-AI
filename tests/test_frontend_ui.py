"""Phase 11A home page and shared design-system checks."""

import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

from utils.auth_store import COOKIE_NAME, DictTokenStore


def _sidebar_markdown(at) -> str:
    return " ".join(str(item.value) for item in at.sidebar.markdown)


def _main_markdown(at) -> str:
    return " ".join(str(item.value) for item in at.markdown)


def test_ui_module_does_not_import_the_backend_package():
    text = (FRONTEND / "utils" / "ui.py").read_text(encoding="utf-8")
    assert "from backend" not in text
    assert "import backend" not in text
    assert "apply_theme" in text
    assert "page_header" in text
    assert "page_hero" in text
    assert "info_rows" in text
    assert "workflow_steps" in text
    assert "appointment_status_chip" in text
    assert "predicted_wait_block" in text
    assert "eligibility_result_chip" in text
    assert "service_card" in text
    assert "render_sidebar_nav" in text
    assert "#12355B" in text
    assert "#1D70B8" in text
    assert "#EAF2F8" in text


def test_auth_login_register_contract_is_unchanged():
    auth = (FRONTEND / "utils" / "auth.py").read_text(encoding="utf-8")
    store = (FRONTEND / "utils" / "auth_store.py").read_text(encoding="utf-8")
    assert "/auth/register" in auth
    assert 'st.tabs(["Sign in", "Register"])' in auth
    assert "queue_persist" in auth
    assert "CookieManager" in store
    assert "query_params" not in auth
    assert "query_params" not in store


def test_home_page_renders_when_logged_out(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import utils.api_client as api_client
    import utils.auth as auth

    monkeypatch.setattr(auth, "get_browser_token_store", lambda: DictTokenStore())
    monkeypatch.setattr(
        api_client,
        "check_backend",
        lambda: {"app_name": "CivicAI", "version": "0.1.0"},
    )

    at = AppTest.from_file(str(FRONTEND / "app.py"), default_timeout=10)
    at.run()
    assert not at.exception
    body = _main_markdown(at)
    sidebar = _sidebar_markdown(at)
    assert "CivicAI" in body
    assert "Intelligent Citizen Service Platform" in body
    assert "Sign in or register from the sidebar" in body
    assert "Regulation Assistant" in body
    assert "CivicAI" in sidebar
    assert "Citizen services" in sidebar
    assert "Officer" in sidebar
    assert "Administrator" in sidebar
    assert any(button.label == "Sign in" for button in at.sidebar.button)


def test_home_page_renders_for_a_signed_in_citizen(monkeypatch):
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
        if path == "/citizens/dashboard":
            return {"message": "Citizen services are available."}
        if path == "/health":
            return {"app_name": "CivicAI", "version": "0.1.0"}
        return {}

    monkeypatch.setattr(auth, "get", fake_get)
    monkeypatch.setattr(api_client, "get", fake_get)
    monkeypatch.setattr(
        api_client,
        "check_backend",
        lambda: {"app_name": "CivicAI", "version": "0.1.0"},
    )

    at = AppTest.from_file(str(FRONTEND / "app.py"), default_timeout=10)
    at.run()
    assert not at.exception
    body = _main_markdown(at)
    sidebar = _sidebar_markdown(at)
    assert "Welcome back, Test Citizen" in body
    assert "Citizen services are available." in body
    assert "Document Verification" in body
    assert "citizen@example.com" in sidebar
    assert "Signed in as" in sidebar
    assert any(button.label == "Sign out" for button in at.sidebar.button)


def test_home_page_renders_operational_cards_for_an_officer(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import utils.api_client as api_client
    import utils.auth as auth

    store = DictTokenStore({COOKIE_NAME: "jwt-officer"})
    monkeypatch.setattr(auth, "get_browser_token_store", lambda: store)

    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/auth/me":
            return {
                "id": 2,
                "email": "officer@example.com",
                "role": "officer",
                "full_name": "Test Officer",
                "is_active": True,
            }
        if path == "/health":
            return {"app_name": "CivicAI", "version": "0.1.0"}
        return {}

    monkeypatch.setattr(auth, "get", fake_get)
    monkeypatch.setattr(api_client, "get", fake_get)
    monkeypatch.setattr(
        api_client,
        "check_backend",
        lambda: {"app_name": "CivicAI", "version": "0.1.0"},
    )

    at = AppTest.from_file(str(FRONTEND / "app.py"), default_timeout=10)
    at.run()
    assert not at.exception
    body = _main_markdown(at)
    assert "Welcome back, Test Officer" in body
    assert "Officer Dashboard" in body
    assert "Queue management" in body
    assert at.session_state["role"] == "officer"


def test_home_page_renders_regulation_management_for_an_administrator(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import utils.api_client as api_client
    import utils.auth as auth

    store = DictTokenStore({COOKIE_NAME: "jwt-admin"})
    monkeypatch.setattr(auth, "get_browser_token_store", lambda: store)

    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/auth/me":
            return {
                "id": 3,
                "email": "admin@example.com",
                "role": "administrator",
                "full_name": "Test Administrator",
                "is_active": True,
            }
        if path == "/health":
            return {"app_name": "CivicAI", "version": "0.1.0"}
        return {}

    monkeypatch.setattr(auth, "get", fake_get)
    monkeypatch.setattr(api_client, "get", fake_get)
    monkeypatch.setattr(
        api_client,
        "check_backend",
        lambda: {"app_name": "CivicAI", "version": "0.1.0"},
    )

    at = AppTest.from_file(str(FRONTEND / "app.py"), default_timeout=10)
    at.run()
    assert not at.exception
    body = _main_markdown(at)
    assert "Welcome back, Test Administrator" in body
    assert "Regulation management" in body
    assert at.session_state["role"] == "administrator"
