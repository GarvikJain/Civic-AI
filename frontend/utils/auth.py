"""Shared sign-in box for the Streamlit pages.

The token is kept in st.session_state, so a page can call the authenticated
endpoints of the backend.
"""

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post


def _store_session(token: str, email: str) -> None:
    st.session_state["token"] = token
    st.session_state["email"] = email
    try:
        me = get("/auth/me", token=token)
    except Exception:
        st.session_state["role"] = None
        st.session_state["full_name"] = None
        return
    st.session_state["role"] = me.get("role")
    st.session_state["full_name"] = me.get("full_name")


def current_role() -> str | None:
    return st.session_state.get("role")


def sidebar_login() -> str | None:
    """Show a sign-in box in the sidebar and return the JWT, if signed in."""
    with st.sidebar:
        st.subheader("Account")

        if st.session_state.get("token"):
            if not st.session_state.get("role"):
                _store_session(
                    st.session_state["token"], st.session_state.get("email", "")
                )
            st.success(
                f"Signed in as {st.session_state.get('email', '')}"
                + (
                    f" ({st.session_state['role']})"
                    if st.session_state.get("role")
                    else ""
                )
            )
            if st.button("Sign out"):
                for key in ("token", "email", "role", "full_name"):
                    st.session_state.pop(key, None)
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
