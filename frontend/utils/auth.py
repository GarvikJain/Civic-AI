"""Shared sign-in box for the Streamlit pages.

The token is kept in st.session_state, so a page can call the authenticated
endpoints of the backend.
"""

import streamlit as st
from requests import HTTPError

from utils.api_client import post


def sidebar_login() -> str | None:
    """Show a sign-in box in the sidebar and return the JWT, if signed in."""
    with st.sidebar:
        st.subheader("Sign in")

        if st.session_state.get("token"):
            st.success(f"Signed in as {st.session_state.get('email', '')}")
            if st.button("Sign out"):
                st.session_state.pop("token", None)
                st.session_state.pop("email", None)
                st.rerun()
            return st.session_state["token"]

        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        if st.button("Sign in"):
            try:
                response = post("/auth/login", {"email": email, "password": password})
            except HTTPError:
                st.error("Sign in failed. Check your email and password.")
                return None
            except Exception:
                st.error("Backend is not reachable.")
                return None

            st.session_state["token"] = response["access_token"]
            st.session_state["email"] = email
            st.rerun()

        st.caption("No account yet? Register with POST /api/v1/auth/register.")
    return None
