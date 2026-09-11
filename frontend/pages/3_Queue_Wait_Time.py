"""Streamlit page for Module 3: Queue Wait-Time Prediction."""

import streamlit as st

from utils.api_client import get

st.title("Queue Wait-Time Prediction")
st.write("See how long you are likely to wait at a government office.")

try:
    st.json(get("/queue/module"))
except Exception as error:
    st.warning(f"Could not reach the backend: {error}")
