"""Frontend JWT persistence across a Streamlit page refresh.

These tests exercise the cookie-backed restore/logout helpers. They do not
change backend JWT generation, validation, hashing, or RBAC.
"""

import sys
from pathlib import Path

import pytest
from requests import HTTPError

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

from utils.auth_store import (
    COOKIE_NAME,
    COOKIE_OP_KEY,
    SKIP_RESTORE_KEY,
    DictTokenStore,
    apply_identity,
    cookie_max_age_seconds,
    flush_cookie_op,
    identity_from_token,
    logout,
    persist_token,
    queue_clear,
    queue_persist,
    restore_session,
)

AUTH_PY = FRONTEND / "utils" / "auth.py"
AUTH_STORE_PY = FRONTEND / "utils" / "auth_store.py"


def _identity(role: str, email: str | None = None) -> dict:
    return {
        "id": 1,
        "email": email or f"{role}@example.com",
        "role": role,
        "full_name": f"Test {role.title()}",
        "is_active": True,
    }


def _fetch_me_for(role: str):
    def fetch_me(token: str) -> dict:
        assert token
        return _identity(role)

    return fetch_me


def test_login_then_refresh_restores_the_same_session():
    store = DictTokenStore()
    persist_token(store, "jwt-citizen")
    apply_identity({}, "jwt-citizen", _identity("citizen"))

    refreshed: dict = {}
    assert restore_session(refreshed, store, _fetch_me_for("citizen")) is True
    assert refreshed["token"] == "jwt-citizen"
    assert refreshed["email"] == "citizen@example.com"
    assert refreshed["role"] == "citizen"
    assert refreshed["full_name"] == "Test Citizen"
    assert store.get(COOKIE_NAME) == "jwt-citizen"
    assert "password" not in store.cookies


def test_logout_then_refresh_requires_login():
    session = {
        "token": "jwt-citizen",
        "email": "citizen@example.com",
        "role": "citizen",
        "full_name": "Test Citizen",
    }
    store = DictTokenStore({COOKIE_NAME: "jwt-citizen"})

    logout(session, store)
    assert COOKIE_NAME not in store.cookies
    assert "token" not in session
    assert "role" not in session
    assert session.get(SKIP_RESTORE_KEY) is True

    # st.context.cookies can still carry the JWT after logout until refresh.
    assert (
        restore_session(
            session,
            store,
            _fetch_me_for("citizen"),
            http_cookies={COOKIE_NAME: "jwt-citizen"},
        )
        is False
    )
    assert "token" not in session

    refreshed = {SKIP_RESTORE_KEY: True}
    assert restore_session(refreshed, store, _fetch_me_for("citizen")) is False
    assert "token" not in refreshed


def test_login_after_logout_clears_skip_restore_flag():
    session = {SKIP_RESTORE_KEY: True}
    queue_persist(session, "jwt-citizen")
    assert SKIP_RESTORE_KEY not in session


@pytest.mark.parametrize("bad_token", ["expired-jwt", "not-a-real-token", ""])
def test_expired_or_invalid_token_requires_login(bad_token):
    store = DictTokenStore({COOKIE_NAME: bad_token} if bad_token else {})

    def fetch_me(token: str) -> dict:
        raise HTTPError("401 Invalid or expired token")

    session: dict = {}
    assert restore_session(session, store, fetch_me) is False
    assert session == {}
    assert store.get(COOKIE_NAME) is None


def test_inactive_user_token_is_cleared():
    store = DictTokenStore({COOKIE_NAME: "jwt-inactive"})

    def fetch_me(token: str) -> dict:
        return {
            "email": "later-disabled@example.com",
            "role": "officer",
            "full_name": "Disabled",
            "is_active": False,
        }

    session: dict = {}
    assert restore_session(session, store, fetch_me) is False
    assert session == {}
    assert store.get(COOKIE_NAME) is None


@pytest.mark.parametrize("role", ["citizen", "officer", "administrator"])
def test_role_is_preserved_after_refresh(role):
    store = DictTokenStore({COOKIE_NAME: f"jwt-{role}"})
    session: dict = {}
    assert restore_session(session, store, _fetch_me_for(role)) is True
    assert session["role"] == role
    assert session["email"] == f"{role}@example.com"
    assert session["token"] == f"jwt-{role}"


def test_existing_session_token_is_not_replaced_from_cookie():
    store = DictTokenStore({COOKIE_NAME: "cookie-jwt"})
    session = {"token": "session-jwt", "role": "officer"}
    assert restore_session(session, store, _fetch_me_for("citizen")) is True
    assert session["token"] == "session-jwt"
    assert session["role"] == "officer"


def test_identity_from_token_rejects_empty_and_malformed_payloads():
    assert identity_from_token("", _fetch_me_for("citizen")) is None
    assert identity_from_token("  ", _fetch_me_for("citizen")) is None
    assert identity_from_token("jwt", lambda token: "not-a-dict") is None
    assert identity_from_token("jwt", lambda token: {"email": "a@b.c"}) is None


def test_cookiemanager_expiry_has_no_microseconds():
    captured = {}

    class FakeManager:
        cookies = {}

        def get(self, name):
            return self.cookies.get(name)

        def set(self, cookie, val, **kwargs):
            captured.update(kwargs)
            captured["cookie"] = cookie
            captured["val"] = val
            self.cookies[cookie] = val

        def delete(self, cookie, key="delete"):
            self.cookies.pop(cookie, None)

    from utils.auth_store import CookieManagerTokenStore

    CookieManagerTokenStore(FakeManager()).set(COOKIE_NAME, "jwt", max_age=3600)
    expires_at = captured["expires_at"]
    assert expires_at.microsecond == 0
    assert captured["max_age"] == 3600
    assert captured["same_site"] == "strict"
    assert captured["path"] == "/"


def test_cookie_max_age_follows_jwt_expiry_minutes(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "90")
    assert cookie_max_age_seconds() == 90 * 60
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "not-a-number")
    assert cookie_max_age_seconds() == 60 * 60


def test_cookie_write_is_queued_until_flush():
    session: dict = {}
    store = DictTokenStore()
    queue_persist(session, "jwt-citizen")
    assert store.get(COOKIE_NAME) is None
    assert session[COOKIE_OP_KEY]["op"] == "set"
    assert flush_cookie_op(session, store) == "set"
    assert store.get(COOKIE_NAME) == "jwt-citizen"
    assert COOKIE_OP_KEY not in session


def test_pending_delete_blocks_restore_until_flush():
    session = {COOKIE_OP_KEY: {"op": "delete"}}
    store = DictTokenStore({COOKIE_NAME: "jwt-citizen"})
    assert restore_session(session, store, _fetch_me_for("citizen")) is False
    assert "token" not in session
    assert store.get(COOKIE_NAME) == "jwt-citizen"
    assert flush_cookie_op(session, store) == "delete"
    assert store.get(COOKIE_NAME) is None


def test_empty_cookiemanager_read_does_not_mean_cookie_is_missing():
    store = DictTokenStore()
    session: dict = {}
    assert (
        restore_session(
            session,
            store,
            _fetch_me_for("citizen"),
            http_cookies={COOKIE_NAME: "jwt-citizen"},
        )
        is True
    )
    assert session["token"] == "jwt-citizen"
    assert session["role"] == "citizen"
    assert store.get(COOKIE_NAME) is None


def test_empty_read_does_not_delete_a_cookie():
    store = DictTokenStore()
    session: dict = {}

    def fetch_me(token: str) -> dict:
        raise HTTPError("should not be called")

    assert restore_session(session, store, fetch_me) is False
    assert store.cookies == {}
    assert session == {}


def test_queue_clear_without_immediate_store_keeps_cookie_until_flush():
    session = {
        "token": "jwt-citizen",
        "email": "citizen@example.com",
        "role": "citizen",
        "full_name": "Test Citizen",
    }
    store = DictTokenStore({COOKIE_NAME: "jwt-citizen"})
    queue_clear(session)
    session.pop("token", None)
    session.pop("email", None)
    session.pop("role", None)
    session.pop("full_name", None)
    assert store.get(COOKIE_NAME) == "jwt-citizen"
    flush_cookie_op(session, store)
    assert store.get(COOKIE_NAME) is None


def test_persistence_does_not_use_query_params_or_store_passwords():
    auth_text = AUTH_PY.read_text(encoding="utf-8")
    store_text = AUTH_STORE_PY.read_text(encoding="utf-8")
    combined = auth_text + store_text
    assert "query_params" not in combined
    assert "experimental_set_query_params" not in combined
    assert "CookieManager" in store_text
    assert "extra_streamlit_components" in store_text
    assert COOKIE_NAME in store_text
    assert "queue_persist" in auth_text
    assert "flush_cookie_op" in auth_text
    assert "password" not in persist_token.__code__.co_varnames
    assert "/auth/me" in store_text or "/auth/me" in auth_text
    assert "/auth/register" in auth_text
    assert 'st.tabs(["Sign in", "Register"])' in auth_text


def test_home_page_apptest_login_writes_cookie_after_rerun(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import utils.api_client as api_client
    import utils.auth as auth

    store = DictTokenStore()
    monkeypatch.setattr(auth, "get_browser_token_store", lambda: store)

    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/auth/me":
            assert token == "real-jwt-from-api"
            return _identity("citizen", "citizen@example.com")
        if path == "/health":
            return {"app_name": "CivicAI", "version": "0.1.0"}
        if path == "/citizens/dashboard":
            return {"message": "Citizen services are available."}
        return {}

    def fake_post(path, payload, token=None, timeout=None):
        if path == "/auth/login":
            assert payload["email"] == "citizen@example.com"
            assert payload["password"] == "civicai-password"
            return {"access_token": "real-jwt-from-api", "token_type": "bearer"}
        raise AssertionError(path)

    monkeypatch.setattr(auth, "get", fake_get)
    monkeypatch.setattr(auth, "post", fake_post)
    monkeypatch.setattr(api_client, "get", fake_get)
    monkeypatch.setattr(api_client, "post", fake_post)
    monkeypatch.setattr(
        api_client,
        "check_backend",
        lambda: {"app_name": "CivicAI", "version": "0.1.0"},
    )

    at = AppTest.from_file(str(FRONTEND / "app.py"), default_timeout=10)
    at.run()
    assert not at.exception
    assert store.get(COOKIE_NAME) is None

    at.sidebar.text_input(key="login_email").set_value("citizen@example.com")
    at.sidebar.text_input(key="login_password").set_value("civicai-password")
    sign_in = [button for button in at.sidebar.button if button.label == "Sign in"]
    assert sign_in
    sign_in[0].click().run()
    assert not at.exception
    assert store.get(COOKIE_NAME) == "real-jwt-from-api"
    assert at.session_state["role"] == "citizen"


def test_home_page_apptest_restores_login_and_logout(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import utils.auth as auth
    import utils.api_client as api_client

    store = DictTokenStore({COOKIE_NAME: "jwt-citizen"})
    monkeypatch.setattr(auth, "get_browser_token_store", lambda: store)

    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/auth/me":
            assert token == "jwt-citizen"
            return _identity("citizen", "citizen@example.com")
        if path == "/health":
            return {"app_name": "CivicAI", "version": "0.1.0"}
        if path == "/citizens/dashboard":
            return {"message": "Citizen services are available."}
        raise AssertionError(path)

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
    signed_in = [item.value for item in at.sidebar.success]
    assert any("citizen@example.com" in str(value) for value in signed_in)
    assert any("citizen" in str(value) for value in signed_in)
    assert at.session_state["role"] == "citizen"

    sign_out = [button for button in at.sidebar.button if button.label == "Sign out"]
    assert sign_out
    sign_out[0].click().run()
    assert not at.exception
    assert store.get(COOKIE_NAME) is None
    assert "token" not in at.session_state

    for key in ("token", "email", "role", "full_name"):
        if key in at.session_state:
            del at.session_state[key]
    at.run()
    assert not at.exception
    assert "token" not in at.session_state
    assert any(button.label == "Sign in" for button in at.sidebar.button)


def test_home_page_apptest_invalid_cookie_requires_login(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import utils.api_client as api_client
    import utils.auth as auth

    store = DictTokenStore({COOKIE_NAME: "expired-jwt"})
    monkeypatch.setattr(auth, "get_browser_token_store", lambda: store)

    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/auth/me":
            raise HTTPError("401 Token has expired")
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
    assert store.get(COOKIE_NAME) is None
    assert "token" not in at.session_state
    assert any(button.label == "Sign in" for button in at.sidebar.button)


def test_apptest_other_page_refresh_stays_logged_in(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import utils.api_client as api_client
    import utils.auth as auth

    store = DictTokenStore({COOKIE_NAME: "jwt-citizen"})
    monkeypatch.setattr(auth, "get_browser_token_store", lambda: store)

    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/auth/me":
            return _identity("citizen", "citizen@example.com")
        if path == "/health":
            return {"app_name": "CivicAI", "version": "0.1.0"}
        if path == "/citizens/dashboard":
            return {"message": "Citizen services are available."}
        return {}

    monkeypatch.setattr(auth, "get", fake_get)
    monkeypatch.setattr(api_client, "get", fake_get)
    monkeypatch.setattr(
        api_client,
        "check_backend",
        lambda: {"app_name": "CivicAI", "version": "0.1.0"},
    )

    home = AppTest.from_file(str(FRONTEND / "app.py"), default_timeout=10)
    home.run()
    assert not home.exception
    assert home.session_state["role"] == "citizen"

    other = AppTest.from_file(
        str(FRONTEND / "pages" / "1_Regulation_Assistant.py"),
        default_timeout=10,
    )
    other.run()
    assert not other.exception
    assert other.session_state["role"] == "citizen"

    for key in ("token", "email", "role", "full_name"):
        if key in other.session_state:
            del other.session_state[key]
    other.run()
    assert not other.exception
    assert other.session_state["token"] == "jwt-citizen"
    assert other.session_state["role"] == "citizen"
    assert other.session_state["email"] == "citizen@example.com"


def test_home_page_apptest_preserves_officer_role_after_refresh(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import utils.auth as auth
    import utils.api_client as api_client

    store = DictTokenStore({COOKIE_NAME: "jwt-officer"})
    monkeypatch.setattr(auth, "get_browser_token_store", lambda: store)

    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/auth/me":
            return _identity("officer", "officer@example.com")
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
    assert at.session_state["role"] == "officer"

    for key in ("token", "email", "role", "full_name"):
        if key in at.session_state:
            del at.session_state[key]
    at.run()
    assert not at.exception
    assert at.session_state["role"] == "officer"
    assert at.session_state["email"] == "officer@example.com"
