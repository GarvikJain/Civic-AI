"""Streamlit page for Module 6: Citizen Feedback Sentiment Analysis."""

import streamlit as st

from utils.api_client import get

st.title("Citizen Feedback Sentiment")
st.write("Understand what citizens say about government services.")

try:
    st.json(get("/feedback/status"))
except Exception as error:
    st.warning(f"Could not reach the backend: {error}")
