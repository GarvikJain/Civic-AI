"""Streamlit page for Module 5: Proactive Eligibility Nudge."""

import streamlit as st

from utils.api_client import get

st.title("Proactive Eligibility Nudge")
st.write("Find government schemes you are likely eligible for.")

try:
    st.json(get("/eligibility/status"))
except Exception as error:
    st.warning(f"Could not reach the backend: {error}")
