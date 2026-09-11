"""Streamlit page for Module 4: Officer Productivity Dashboard."""

import streamlit as st

from utils.api_client import get

st.title("Officer Productivity Dashboard")
st.write("Track how applications are handled across officers.")

try:
    st.json(get("/officers/status"))
except Exception as error:
    st.warning(f"Could not reach the backend: {error}")
