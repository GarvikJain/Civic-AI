"""Streamlit page for Module 2: Document Verification."""

import streamlit as st

from utils.api_client import get

st.title("Document Verification")
st.write("Upload a document and let CivicAI check it automatically.")

try:
    st.json(get("/documents/status"))
except Exception as error:
    st.warning(f"Could not reach the backend: {error}")
