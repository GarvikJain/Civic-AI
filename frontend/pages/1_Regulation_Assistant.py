"""Streamlit page for Module 1: Regulation RAG Assistant."""

import streamlit as st

from utils.api_client import get

st.title("Regulation RAG Assistant")
st.write("Ask questions about government regulations and get sourced answers.")

try:
    st.json(get("/regulations/status"))
except Exception as error:  # backend not running yet
    st.warning(f"Could not reach the backend: {error}")
