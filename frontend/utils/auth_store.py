"""Browser-side JWT persistence for Streamlit page refresh.

The access token is stored in a first-party cookie via CookieManager from
extra-streamlit-components 0.1.81 (universal-cookie). CookieManager.set() and
delete() only run in a browser iframe after the current script run finishes.
They are therefore queued in session state and flushed on the next run, never
in the same run as st.rerun().

The password is never written. A persisted token is only trusted after
GET /auth/me succeeds.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

COOKIE_NAME = "civicai_access_token"
COOKIE_OP_KEY = "_civicai_cookie_op"
SKIP_RESTORE_KEY = "_civicai_skip_cookie_restore"
SESSION_KEYS = ("token", "email", "role", "full_name")

FetchMe = Callable[[str], dict[str, Any]]


def cookie_max_age_seconds() -> int:
    """Cookie lifetime matches ACCESS_TOKEN_EXPIRE_MINUTES (JWT expiry)."""
    raw = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        minutes = 60
    return max(minutes, 1) * 60


class TokenStore(Protocol):
    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str, *, max_age: int) -> None: ...

    def delete(self, name: str) -> None: ...


class DictTokenStore:
    """In-memory cookie stand-in for tests."""

    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self.cookies = cookies if cookies is not None else {}

    def get(self, name: str) -> str | None:
        value = self.cookies.get(name)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def set(self, name: str, value: str, *, max_age: int) -> None:
        self.cookies[name] = value

    def delete(self, name: str) -> None:
        self.cookies.pop(name, None)


class CookieManagerTokenStore:
    """Persist the JWT with extra-streamlit-components CookieManager."""

    def __init__(self, manager: Any) -> None:
        self._manager = manager

    def get(self, name: str) -> str | None:
        value = self._manager.get(name)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def set(self, name: str, value: str, *, max_age: int) -> None:
        # CookieManager's JS does new Date(expires_at.isoformat()). Python's
        # default isoformat includes microseconds, which Edge rejects as an
        # invalid expiry and then drops the cookie.
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=max_age)
        ).replace(microsecond=0)
        self._manager.set(
            name,
            value,
            key="civicai-set-access-token",
            expires_at=expires_at,
            max_age=max_age,
            same_site="strict",
            path="/",
        )

    def delete(self, name: str) -> None:
        try:
            self._manager.delete(name, key="civicai-del-access-token")
        except KeyError:
            pass
        if hasattr(self._manager, "cookies"):
            self._manager.cookies.pop(name, None)


def get_browser_token_store() -> TokenStore:
    """Return the CookieManager-backed store for the current script run.

    CookieManager.__init__ issues getAll. set()/delete() use a second
    component iframe and must be allowed to finish rendering.
    """
    import extra_streamlit_components as stx

    return CookieManagerTokenStore(stx.CookieManager(key="civicai-auth-cookies"))


def read_http_cookies() -> dict[str, str]:
    """Cookies from the browser request (st.context). Empty before handshake."""
    try:
        import streamlit as st

        cookies = st.context.cookies
        if hasattr(cookies, "to_dict"):
            return dict(cookies.to_dict())
        return dict(cookies)
    except Exception:
        return {}


def apply_identity(session: dict, token: str, identity: dict[str, Any]) -> None:
    session["token"] = token
    session["email"] = identity.get("email") or session.get("email") or ""
    session["role"] = identity.get("role")
    session["full_name"] = identity.get("full_name")


def clear_session(session: dict) -> None:
    for key in SESSION_KEYS:
        session.pop(key, None)


def queue_persist(session: dict, token: str) -> None:
    """Remember a cookie write for the next completed script run."""
    if not token:
        return
    session[COOKIE_OP_KEY] = {"op": "set", "value": token}
    session.pop(SKIP_RESTORE_KEY, None)


def queue_clear(session: dict) -> None:
    """Remember a cookie delete for the next completed script run."""
    session[COOKIE_OP_KEY] = {"op": "delete"}


def pending_cookie_op(session: dict) -> str | None:
    op = session.get(COOKIE_OP_KEY)
    if not isinstance(op, dict):
        return None
    kind = op.get("op")
    return kind if kind in ("set", "delete") else None


def flush_cookie_op(session: dict, store: TokenStore) -> str | None:
    """Apply a queued set/delete. Must not be followed by st.rerun()."""
    op = session.get(COOKIE_OP_KEY)
    if not isinstance(op, dict):
        return None
    kind = op.get("op")
    if kind == "set":
        persist_token(store, str(op.get("value") or ""))
    elif kind == "delete":
        store.delete(COOKIE_NAME)
    else:
        return None
    session.pop(COOKIE_OP_KEY, None)
    return kind


def identity_from_token(token: str, fetch_me: FetchMe) -> dict[str, Any] | None:
    """Return /auth/me payload if the token is usable, otherwise None."""
    if not token or not str(token).strip():
        return None
    try:
        me = fetch_me(str(token).strip())
    except Exception:
        return None
    if not isinstance(me, dict):
        return None
    if not me.get("email") or not me.get("role"):
        return None
    if me.get("is_active") is False:
        return None
    return me


def persist_token(store: TokenStore, token: str) -> None:
    if not token:
        return
    store.set(COOKIE_NAME, token, max_age=cookie_max_age_seconds())


def _token_from_store_or_http(
    store: TokenStore, http_cookies: dict[str, str] | None
) -> str | None:
    token = store.get(COOKIE_NAME)
    if token:
        return token
    if not http_cookies:
        return None
    raw = http_cookies.get(COOKIE_NAME)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def restore_session(
    session: dict,
    store: TokenStore,
    fetch_me: FetchMe,
    *,
    http_cookies: dict[str, str] | None = None,
) -> bool:
    """Restore login from the persisted JWT when Streamlit session_state is empty.

    An empty CookieManager read is not treated as proof the cookie is missing:
    the getAll iframe may still be returning its default {}. HTTP cookies from
    st.context are checked as well. A token is deleted only after /auth/me
    rejects it.
    """
    if session.get("token"):
        return True
    if session.get(SKIP_RESTORE_KEY):
        return False
    if pending_cookie_op(session) == "delete":
        return False
    token = _token_from_store_or_http(store, http_cookies)
    if not token:
        return False
    identity = identity_from_token(token, fetch_me)
    if identity is None:
        store.delete(COOKIE_NAME)
        return False
    apply_identity(session, token, identity)
    return True


def logout(session: dict, store: TokenStore | None = None) -> None:
    """Queue cookie removal and clear Streamlit session keys.

    If store is provided (tests), the delete is applied immediately. The live
    Streamlit UI must omit store and let the next script run flush the delete
    so CookieManager's iframe can finish.
    """
    queue_clear(session)
    clear_session(session)
    session[SKIP_RESTORE_KEY] = True
    if store is not None:
        flush_cookie_op(session, store)
