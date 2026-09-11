"""Streamlit entry point for CivicAI.

Start the frontend with:  streamlit run frontend/app.py

Streamlit puts this file's folder (frontend/) on the import path, so the
helpers are imported as "utils.api_client" and not "frontend.utils.api_client".
"""

import streamlit as st

from utils.api_client import check_backend, get
from utils.auth import current_role, sidebar_login

st.set_page_config(page_title="CivicAI", page_icon="🏛️", layout="wide")

st.title("🏛️ CivicAI")
st.caption("An AI-Powered Intelligent Citizen Service Platform for Government Offices")

token = sidebar_login()
role = current_role()

health = check_backend()
if health is None:
    st.error(
        "Backend is not reachable. Start it with: "
        "`uvicorn backend.main:app --reload`"
    )
else:
    st.success(f"Connected to backend: {health['app_name']} v{health['version']}")

if token and role == "citizen":
    try:
        dashboard = get("/citizens/dashboard", token=token)
        st.info(dashboard.get("message", "Citizen services are available."))
    except Exception:
        st.caption("Citizen dashboard could not be loaded.")
elif token and role in ("officer", "administrator"):
    st.info(
        "Open Officer Productivity Dashboard from the sidebar for analytics, "
        "document review and flagged feedback."
    )
else:
    st.caption("Sign in or register from the sidebar to use citizen services.")

st.divider()

st.subheader("Modules")
st.write(
    "Use the sidebar to open a module. Regulation answers, document checks, "
    "queue prediction, eligibility screening, citizen feedback and the officer "
    "productivity dashboard are available."
)

modules = [
    ("1. Regulation RAG Assistant", "Ask questions about government regulations."),
    ("2. Document Verification", "Check uploaded documents with OCR."),
    ("3. Queue Wait-Time Prediction", "Estimate waiting time at an office."),
    ("4. Officer Productivity Dashboard", "Track how officers handle applications."),
    ("5. Proactive Eligibility Nudge", "Suggest schemes a citizen can apply for."),
    ("6. Citizen Feedback Sentiment", "Analyse feedback left by citizens."),
]

for name, description in modules:
    st.markdown(f"**{name}** - {description}")
