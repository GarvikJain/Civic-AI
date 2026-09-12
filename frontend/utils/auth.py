"""Shared sign-in box for the Streamlit pages.

The JWT is kept in st.session_state for the current Streamlit session and
written to a first-party browser cookie so a normal page refresh can restore
the login. CookieManager writes are queued and flushed on a later run that
is allowed to finish (set/delete must not share a run with st.rerun()).
The password is never stored.
"""

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post
from utils.ui import (
    apply_theme,
    render_sidebar_brand,
    render_sidebar_nav,
    render_signed_in_account,
)
from utils.auth_store import (
    COOKIE_NAME,
    SKIP_RESTORE_KEY,
    apply_identity,
    flush_cookie_op,
    get_browser_token_store,
    identity_from_token,
    logout,
    pending_cookie_op,
    persist_token,
    queue_persist,
    read_http_cookies,
    restore_session,
)


def _fetch_me(token: str) -> dict:
    return get("/auth/me", token=token)


def _store_session(token: str, email: str) -> None:
    queue_persist(st.session_state, token)
    st.session_state["token"] = token
    st.session_state["email"] = email
    identity = identity_from_token(token, _fetch_me)
    if identity is None:
        st.session_state["role"] = None
        st.session_state["full_name"] = None
        return
    apply_identity(st.session_state, token, identity)


def current_role() -> str | None:
    return st.session_state.get("role")


def sidebar_login() -> str | None:
    """Show a sign-in box in the sidebar and return the JWT, if signed in."""
    store = get_browser_token_store()
    flushed = flush_cookie_op(st.session_state, store)
    restore_session(
        st.session_state,
        store,
        _fetch_me,
        http_cookies=read_http_cookies(),
    )
    # Keep the matching CookieManager iframe mounted. A one-shot set/delete is
    # torn down before the browser JS writes document.cookie.
    if st.session_state.get(SKIP_RESTORE_KEY):
        if flushed != "delete":
            store.delete(COOKIE_NAME)
    elif (
        st.session_state.get("token")
        and pending_cookie_op(st.session_state) != "delete"
        and flushed != "set"
    ):
        persist_token(store, st.session_state["token"])

    apply_theme()

    with st.sidebar:
        render_sidebar_brand()
        render_sidebar_nav()
        st.markdown('<p class="civicai-nav-label">Account</p>', unsafe_allow_html=True)

        if st.session_state.get("token"):
            if not st.session_state.get("role"):
                _store_session(
                    st.session_state["token"],
                    st.session_state.get("email", ""),
                )
            render_signed_in_account(
                st.session_state.get("email", ""),
                st.session_state.get("role"),
                st.session_state.get("full_name"),
            )
            if st.button("Sign out", width="stretch"):
                logout(st.session_state)
                st.rerun()
            return st.session_state["token"]

        sign_in, register = st.tabs(["Sign in", "Register"])

        with sign_in:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            if st.button("Sign in"):
                try:
                    response = post(
                        "/auth/login", {"email": email, "password": password}
                    )
                except HTTPError:
                    st.error("Sign in failed. Check your email and password.")
                    return None
                except Exception:
                    st.error("Backend is not reachable.")
                    return None
                _store_session(response["access_token"], email)
                st.rerun()

        with register:
            st.caption("Creates a citizen account. Officers are created by an administrator.")
            full_name = st.text_input("Full name", key="register_name")
            register_email = st.text_input("Email", key="register_email")
            register_password = st.text_input(
                "Password", type="password", key="register_password"
            )
            if st.button("Create citizen account"):
                if not full_name.strip() or not register_email.strip() or not register_password:
                    st.warning("Name, email and password are required.")
                else:
                    try:
                        post(
                            "/auth/register",
                            {
                                "full_name": full_name.strip(),
                                "email": register_email.strip(),
                                "password": register_password,
                            },
                        )
                        response = post(
                            "/auth/login",
                            {
                                "email": register_email.strip(),
                                "password": register_password,
                            },
                        )
                    except HTTPError as error:
                        detail = "Registration failed."
                        try:
                            detail = error.response.json().get("detail", detail)
                        except ValueError:
                            pass
                        st.error(detail)
                    except Exception:
                        st.error("Backend is not reachable.")
                    else:
                        _store_session(response["access_token"], register_email.strip())
                        st.rerun()
    return None
