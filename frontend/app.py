"""Streamlit entry point for CivicAI.

Start the frontend with:  streamlit run frontend/app.py

Streamlit puts this file's folder (frontend/) on the import path, so the
helpers are imported as "utils.api_client" and not "frontend.utils.api_client".
"""

import streamlit as st

from utils.api_client import check_backend, get
from utils.auth import current_role, sidebar_login
from utils.ui import (
    ADMIN_SERVICES,
    CITIZEN_SERVICES,
    OFFICER_SERVICES,
    current_user_name,
    empty_state,
    info_card,
    page_header,
    render_service_cards,
    section_header,
)

st.set_page_config(page_title="CivicAI", page_icon="🏛️", layout="wide")

token = sidebar_login()
role = current_role()

page_header("CivicAI", "Intelligent Citizen Service Platform")
st.markdown(
    '<p class="civicai-lede">AI-powered assistance for faster, clearer '
    "and more accountable government services.</p>",
    unsafe_allow_html=True,
)

health = check_backend()
if health is None:
    st.error(
        "Backend is not reachable. Start it with: "
        "`uvicorn backend.main:app --reload`"
    )
else:
    st.caption(f"Connected to {health['app_name']} {health['version']}")

if token and role == "citizen":
    section_header(f"Welcome back, {current_user_name()}")
    try:
        dashboard = get("/citizens/dashboard", token=token)
        info_card(dashboard.get("message", "Citizen services are available."))
    except Exception:
        st.caption("Citizen dashboard could not be loaded.")
    section_header("Citizen services", "Open a service from a card or the sidebar.")
    render_service_cards(CITIZEN_SERVICES)
elif token and role in ("officer", "administrator"):
    section_header(f"Welcome back, {current_user_name()}")
    info_card(
        "Use the operational pages for queue management, document review "
        "and flagged feedback."
    )
    section_header("Operations", "Tools for officers and administrators.")
    cards = list(OFFICER_SERVICES)
    if role == "administrator":
        cards = list(ADMIN_SERVICES)
    render_service_cards(cards)
    section_header("Citizen services", "The public services remain available.")
    render_service_cards(CITIZEN_SERVICES)
else:
    section_header("Welcome")
    empty_state("Sign in or register from the sidebar to use CivicAI services.")
    section_header("Available services")
    render_service_cards(CITIZEN_SERVICES)
