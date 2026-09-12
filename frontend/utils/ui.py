"""Shared CivicAI presentation helpers.

Visual styling only. This module does not call the API, touch authentication,
or import the backend package.
"""

from __future__ import annotations

import html
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

import streamlit as st

_FRONTEND = Path(__file__).resolve().parents[1]


def page_path(*parts: str) -> str:
    """Absolute path to a frontend file, so page_link works from any page."""
    return str(_FRONTEND.joinpath(*parts))


def safe_page_link(page: str, label: str) -> None:
    """Link to an existing Streamlit page; show the label if the link cannot resolve.

    AppTest of a single pages/*.py file treats that file as the entrypoint, so
    st.page_link cannot see app.py. The live app started from frontend/app.py
    still gets real navigation links.
    """
    try:
        st.page_link(page, label=label, width="stretch")
    except Exception:
        st.markdown(f"- {_escape(label)}")

NAVY = "#12355B"
CHARCOAL = "#17202A"
CIVIC_BLUE = "#1D70B8"
SURFACE = "#FFFFFF"
MUTED_SURFACE = "#EAF2F8"
LIGHT_BLUE = "#DCEAF4"
BORDER = "#C5D8E8"
TEXT = "#17202A"
MUTED_TEXT = "#4A5A68"
SUCCESS = "#198754"
WARNING = "#8A6D00"
WARNING_BG = "#F6E7A1"
ERROR = "#8B2E2E"
ERROR_BG = "#F4CCCC"
HERO_TEXT = "#F4F8FC"
HERO_MUTED = "#D5E4F0"

CITIZEN_SERVICES = (
    {
        "title": "Regulation Assistant",
        "description": "Ask questions about official government regulations.",
        "page": page_path("pages", "1_Regulation_Assistant.py"),
    },
    {
        "title": "Document Verification",
        "description": "Upload documents and check them automatically.",
        "page": page_path("pages", "2_Document_Verification.py"),
    },
    {
        "title": "Queue Wait Time",
        "description": "Book a visit and view predicted waiting time.",
        "page": page_path("pages", "3_Queue_Wait_Time.py"),
    },
    {
        "title": "Eligibility Nudge",
        "description": "Check eligibility before applying.",
        "page": page_path("pages", "5_Eligibility_Nudge.py"),
    },
    {
        "title": "Citizen Feedback",
        "description": "Share feedback after completing a service.",
        "page": page_path("pages", "6_Feedback_Sentiment.py"),
    },
)

OFFICER_SERVICES = (
    {
        "title": "Officer Dashboard",
        "description": "Review operational metrics, documents and flagged feedback.",
        "page": page_path("pages", "4_Officer_Dashboard.py"),
    },
    {
        "title": "Queue management",
        "description": "See the live office queue and update appointment status.",
        "page": page_path("pages", "3_Queue_Wait_Time.py"),
    },
    {
        "title": "Document review",
        "description": "Open the officer dashboard to review documents that need a decision.",
        "page": page_path("pages", "4_Officer_Dashboard.py"),
    },
)

ADMIN_SERVICES = (
    {
        "title": "Regulation management",
        "description": "Register and update official scheme information.",
        "page": page_path("pages", "1_Regulation_Assistant.py"),
    },
    {
        "title": "Officer Dashboard",
        "description": "Review operational metrics, documents and flagged feedback.",
        "page": page_path("pages", "4_Officer_Dashboard.py"),
    },
    {
        "title": "Queue management",
        "description": "See the live office queue and update appointment status.",
        "page": page_path("pages", "3_Queue_Wait_Time.py"),
    },
)

_THEME_CSS = f"""
<style>
  .stApp {{
    background: {MUTED_SURFACE};
    color: {TEXT};
  }}
  [data-testid="stSidebar"] {{
    background: {SURFACE};
    border-right: 1px solid {BORDER};
  }}
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3 {{
    color: {NAVY};
    letter-spacing: 0.01em;
  }}
  [data-testid="stHeader"] {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
  }}
  .stApp h1, .stApp h2, .stApp h3 {{
    color: {NAVY};
    font-weight: 650;
  }}
  .stApp p, .stApp label, .stApp span {{
    color: {TEXT};
  }}
  .civicai-hero,
  .civicai-hero h1,
  .civicai-hero p,
  .civicai-hero span {{
    color: {HERO_TEXT} !important;
  }}
  div[data-testid="stTextInput"] input,
  div[data-testid="stTextArea"] textarea,
  div[data-testid="stNumberInput"] input,
  div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
  div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
  [data-testid="stDateInputField"],
  [data-testid="stDateInput"] input,
  [data-testid="stTimeInputTimeDisplay"],
  [data-testid="stTimeInput"] input {{
    background: {SURFACE} !important;
    background-color: {SURFACE} !important;
    border-color: {BORDER} !important;
    color: {NAVY} !important;
  }}
  [data-testid="stDateInput"],
  [data-testid="stTimeInput"],
  [data-testid="stSelectbox"] {{
    color: {CHARCOAL};
  }}
  [data-baseweb="popover"],
  [data-baseweb="menu"],
  [data-baseweb="calendar-container"],
  [data-testid="stDateInputCalendar"] {{
    background: {SURFACE} !important;
    color: {CHARCOAL} !important;
  }}
  .stButton > button,
  .stFormSubmitButton > button {{
    border: 1px solid {CIVIC_BLUE};
    background: {CIVIC_BLUE};
    color: {SURFACE};
    border-radius: 4px;
    font-weight: 600;
  }}
  .stButton > button:hover,
  .stFormSubmitButton > button:hover {{
    background: {NAVY};
    border-color: {NAVY};
    color: {SURFACE};
  }}
  [data-testid="stAlert"] {{
    border-radius: 4px;
    border: 1px solid {BORDER};
  }}
  [data-testid="stExpander"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
  }}
  [data-testid="stDataFrame"],
  [data-testid="stTable"] {{
    border: 1px solid {BORDER};
    border-radius: 4px;
  }}
  .civicai-brand {{
    margin: 0 0 0.75rem 0;
  }}
  .civicai-brand-name {{
    margin: 0;
    color: {NAVY};
    font-size: 1.2rem;
    font-weight: 700;
    letter-spacing: 0.02em;
  }}
  .civicai-brand-tag {{
    margin: 0.15rem 0 0 0;
    color: {MUTED_TEXT};
    font-size: 0.82rem;
    line-height: 1.35;
  }}
  .civicai-nav-label {{
    margin: 0.85rem 0 0.35rem 0;
    color: {MUTED_TEXT};
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }}
  .civicai-page-header {{
    margin: 0 0 1.1rem 0;
    padding-bottom: 0.85rem;
    border-bottom: 1px solid {BORDER};
  }}
  .civicai-page-title {{
    margin: 0;
    color: {NAVY};
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: 0.01em;
  }}
  .civicai-page-subtitle {{
    margin: 0.3rem 0 0 0;
    color: {MUTED_TEXT};
    font-size: 1.02rem;
  }}
  .civicai-lede {{
    margin: 0 0 1.25rem 0;
    color: {CHARCOAL};
    font-size: 1.02rem;
    line-height: 1.5;
    max-width: 42rem;
  }}
  .civicai-section {{
    margin: 1.35rem 0 0.7rem 0;
  }}
  .civicai-section-title {{
    margin: 0;
    color: {NAVY};
    font-size: 1.2rem !important;
    line-height: 1.3;
    font-weight: 650;
  }}
  .st-key-civicai-ask .civicai-section-title {{
    margin: 0 0 0.35rem 0;
  }}
  .civicai-section-caption {{
    margin: 0.2rem 0 0 0;
    color: {MUTED_TEXT};
    font-size: 0.9rem;
  }}
  .civicai-card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 0.95rem 1rem 1rem 1rem;
    margin: 0 0 0.75rem 0;
    min-height: 8.5rem;
  }}
  .civicai-card h4 {{
    margin: 0 0 0.4rem 0;
    color: {NAVY};
    font-size: 1.02rem;
    font-weight: 650;
  }}
  .civicai-card p {{
    margin: 0;
    color: {MUTED_TEXT};
    font-size: 0.92rem;
    line-height: 1.45;
  }}
  .civicai-info {{
    background: {LIGHT_BLUE};
    border: 1px solid {BORDER};
    border-left: 3px solid {CIVIC_BLUE};
    border-radius: 4px;
    padding: 0.8rem 1rem;
    margin: 0 0 1rem 0;
    color: {CHARCOAL};
  }}
  .civicai-empty {{
    background: {SURFACE};
    border: 1px dashed {BORDER};
    border-radius: 4px;
    padding: 1rem;
    color: {MUTED_TEXT};
  }}
  .civicai-badge {{
    display: inline-block;
    padding: 0.12rem 0.5rem;
    border-radius: 3px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }}
  .civicai-badge-citizen {{ background: #e8eef5; color: {CIVIC_BLUE}; }}
  .civicai-badge-officer {{ background: #e7f0ea; color: {SUCCESS}; }}
  .civicai-badge-administrator {{ background: #f3eee4; color: {WARNING}; }}
  .civicai-account-label {{
    margin: 0;
    color: {MUTED_TEXT};
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 700;
  }}
  .civicai-account-name {{
    margin: 0.2rem 0 0 0;
    color: {NAVY};
    font-weight: 650;
  }}
  .civicai-account-email {{
    margin: 0.1rem 0 0.35rem 0;
    color: {MUTED_TEXT};
    font-size: 0.88rem;
  }}
  .civicai-hero {{
    background: {NAVY};
    border-radius: 8px;
    padding: 1.35rem 1.45rem 1.25rem 1.45rem;
    margin: 0 0 1.15rem 0;
  }}
  .civicai-hero-title {{
    margin: 0;
    color: {HERO_TEXT};
    font-size: 1.65rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    line-height: 1.25;
  }}
  .civicai-hero-subtitle {{
    margin: 0.4rem 0 0.75rem 0;
    color: {HERO_MUTED} !important;
    font-size: 1.02rem;
    line-height: 1.45;
    max-width: 38rem;
  }}
  .civicai-hero-badge {{
    display: inline-block;
    padding: 0.18rem 0.55rem;
    border: 1px solid #8FB4D6;
    border-radius: 3px;
    color: {HERO_TEXT};
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }}
  .civicai-kicker {{
    margin: 0 0 0.28rem 0;
    color: {CIVIC_BLUE} !important;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }}
  .civicai-result-heading {{
    margin: 0 0 0.55rem 0;
    color: {NAVY} !important;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }}
  .civicai-citation-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    align-items: center;
    padding: 0.55rem 0;
    border-bottom: 1px solid {BORDER};
  }}
  .civicai-citation-row:last-child {{
    border-bottom: 0;
    padding-bottom: 0;
  }}
  .civicai-chip {{
    display: inline-block;
    background: {NAVY};
    color: {HERO_TEXT} !important;
    border-radius: 3px;
    padding: 0.14rem 0.45rem;
    font-size: 0.75rem;
    font-weight: 700;
  }}
  .civicai-chip-muted {{
    display: inline-block;
    background: {SURFACE};
    color: {CHARCOAL} !important;
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 0.14rem 0.45rem;
    font-size: 0.75rem;
  }}
  .st-key-civicai-admin {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 0.85rem 1.1rem 1rem 1.1rem;
    margin: 0 0 1.1rem 0;
  }}
  .st-key-civicai-ask {{
    background: {LIGHT_BLUE};
    border: 1px solid {BORDER};
    border-left: 4px solid {CIVIC_BLUE};
    border-radius: 8px;
    padding: 1.05rem 1.2rem 1rem 1.2rem;
    margin: 0 0 1.1rem 0;
  }}
  .st-key-civicai-ask .stButton > button {{
    background: {CIVIC_BLUE};
    border-color: {CIVIC_BLUE};
    color: {SURFACE};
    min-width: 7.25rem;
    font-weight: 650;
  }}
  .st-key-civicai-answer {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-left: 4px solid {NAVY};
    border-radius: 8px;
    padding: 1rem 1.2rem 0.95rem 1.2rem;
    margin: 0 0 0.9rem 0;
  }}
  .st-key-civicai-answer p {{
    line-height: 1.6;
    max-width: 42rem;
  }}
  .st-key-civicai-answer h3,
  .st-key-civicai-citations h3,
  .st-key-civicai-warning h3 {{
    color: {NAVY};
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    margin: 0 0 0.45rem 0;
  }}
  .st-key-civicai-warning h3 {{
    color: {CHARCOAL};
  }}
  .st-key-civicai-citations {{
    background: {LIGHT_BLUE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 0.95rem 1.15rem 1rem 1.15rem;
    margin: 0 0 0.9rem 0;
  }}
  .st-key-civicai-warning {{
    background: {WARNING_BG};
    border: 1px solid #E0C96A;
    border-radius: 8px;
    padding: 0.95rem 1.15rem 1rem 1.15rem;
    margin: 0 0 0.9rem 0;
  }}
  .st-key-civicai-warning h2,
  .st-key-civicai-warning p {{
    color: {CHARCOAL} !important;
  }}
  .st-key-civicai-timeout {{
    background: {LIGHT_BLUE};
    border: 1px solid {CIVIC_BLUE};
    border-radius: 8px;
    padding: 0.7rem 1.05rem 0.75rem 1.05rem;
    margin: 0 0 0.9rem 0;
  }}
  .st-key-civicai-query-error,
  [class*="st-key-civicai-query-error"] {{
    background: {ERROR_BG};
    border: 1px solid #E2A3A3;
    border-radius: 8px;
    padding: 0.65rem 1rem 0.7rem 1rem;
    margin: 0 0 0.9rem 0;
  }}
  .st-key-civicai-warning [data-testid="stAlert"],
  .st-key-civicai-timeout [data-testid="stAlert"],
  .st-key-civicai-query-error [data-testid="stAlert"] {{
    background: transparent;
    border: 0;
  }}
  [data-testid="stSpinner"] {{
    color: {NAVY};
  }}
  .civicai-workflow {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem 0.45rem;
    margin: 0 0 1.1rem 0;
    color: {MUTED_TEXT};
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }}
  .civicai-workflow-sep {{
    color: {CIVIC_BLUE};
    font-weight: 650;
  }}
  .civicai-info-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem 0.85rem;
    padding: 0.45rem 0;
    border-bottom: 1px solid {BORDER};
  }}
  .civicai-info-row:last-child {{
    border-bottom: 0;
    padding-bottom: 0;
  }}
  .civicai-info-label {{
    min-width: 8.5rem;
    color: {MUTED_TEXT} !important;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }}
  .civicai-info-value {{
    color: {CHARCOAL} !important;
    font-size: 0.95rem;
  }}
  .civicai-status-reason {{
    margin: 0.45rem 0 0 0;
    color: {CHARCOAL} !important;
    font-size: 1.02rem;
    font-weight: 650;
    line-height: 1.45;
  }}
  .st-key-civicai-upload {{
    background: {LIGHT_BLUE};
    border: 1px solid {BORDER};
    border-left: 4px solid {CIVIC_BLUE};
    border-radius: 8px;
    padding: 1.05rem 1.2rem 1rem 1.2rem;
    margin: 0 0 1.1rem 0;
  }}
  .st-key-civicai-upload .stButton > button,
  .st-key-civicai-book .stButton > button {{
    background: {CIVIC_BLUE};
    border-color: {CIVIC_BLUE};
    color: {SURFACE};
    min-width: 9.5rem;
    font-weight: 650;
  }}
  .st-key-civicai-book {{
    background: {LIGHT_BLUE};
    border: 1px solid {BORDER};
    border-left: 4px solid {CIVIC_BLUE};
    border-radius: 8px;
    padding: 1.05rem 1.2rem 1rem 1.2rem;
    margin: 0 0 1.1rem 0;
  }}
  .st-key-civicai-prediction,
  [class*="st-key-civicai-prediction"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-left: 4px solid {CIVIC_BLUE};
    border-radius: 8px;
    padding: 1rem 1.2rem 0.95rem 1.2rem;
    margin: 0 0 1.1rem 0;
  }}
  .st-key-civicai-appointments,
  .st-key-civicai-officer {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 0.85rem 1.1rem 1rem 1.1rem;
    margin: 0 0 1.1rem 0;
  }}
  .st-key-civicai-officer {{
    background: {LIGHT_BLUE};
    border-left: 4px solid {NAVY};
  }}
  .civicai-wait-value {{
    margin: 0.1rem 0 0.35rem 0;
    color: {NAVY} !important;
    font-size: 1.85rem;
    font-weight: 700;
    line-height: 1.2;
  }}
  .civicai-status-chip {{
    display: inline-block;
    padding: 0.14rem 0.5rem;
    border-radius: 3px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }}
  .civicai-status-scheduled {{
    background: {LIGHT_BLUE};
    color: {CIVIC_BLUE} !important;
  }}
  .civicai-status-in_service {{
    background: #E7F3EC;
    color: {SUCCESS} !important;
  }}
  .civicai-status-completed {{
    background: #E7F3EC;
    color: {SUCCESS} !important;
  }}
  .civicai-status-cancelled {{
    background: {ERROR_BG};
    color: {ERROR} !important;
  }}
  .st-key-civicai-upload [data-testid="stFileUploader"] {{
    background: {LIGHT_BLUE};
    border: 0;
    border-radius: 6px;
    padding: 0;
  }}
  .st-key-civicai-upload [data-testid="stFileUploaderDropzone"] {{
    background: {SURFACE} !important;
    border: 1px dashed {CIVIC_BLUE} !important;
    border-radius: 6px !important;
    color: {NAVY} !important;
  }}
  .st-key-civicai-upload [data-testid="stFileUploaderDropzoneInstructions"],
  .st-key-civicai-upload [data-testid="stFileUploaderDropzoneInstructions"] p,
  .st-key-civicai-upload [data-testid="stFileUploaderDropzoneInstructions"] span,
  .st-key-civicai-upload [data-testid="stFileUploaderDropzoneInstructions"] small {{
    color: {NAVY} !important;
  }}
  .st-key-civicai-upload [data-testid="stFileUploaderDropzone"] button {{
    background: {CIVIC_BLUE} !important;
    border: 1px solid {CIVIC_BLUE} !important;
    color: {SURFACE} !important;
  }}
  .st-key-civicai-doc-list {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 0.85rem 1.1rem 1rem 1.1rem;
    margin: 0 0 1.1rem 0;
  }}
  [class*="st-key-civicai-verified"] {{
    background: #E7F3EC;
    border: 1px solid #B7D7C4;
    border-left: 4px solid {SUCCESS};
    border-radius: 8px;
    padding: 0.9rem 1.15rem 0.95rem 1.15rem;
    margin: 0 0 0.75rem 0;
  }}
  [class*="st-key-civicai-rejected"] {{
    background: {ERROR_BG};
    border: 1px solid #E2A3A3;
    border-left: 4px solid {ERROR};
    border-radius: 8px;
    padding: 0.9rem 1.15rem 0.95rem 1.15rem;
    margin: 0 0 0.75rem 0;
  }}
  [class*="st-key-civicai-review"] {{
    background: {WARNING_BG};
    border: 1px solid #E0C96A;
    border-left: 4px solid {WARNING};
    border-radius: 8px;
    padding: 0.9rem 1.15rem 0.95rem 1.15rem;
    margin: 0 0 0.75rem 0;
  }}
  [class*="st-key-civicai-pending"] {{
    background: {LIGHT_BLUE};
    border: 1px solid {BORDER};
    border-left: 4px solid {CIVIC_BLUE};
    border-radius: 8px;
    padding: 0.9rem 1.15rem 0.95rem 1.15rem;
    margin: 0 0 0.75rem 0;
  }}
  [class*="st-key-civicai-doc-info"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 0.85rem 1.1rem 0.9rem 1.1rem;
    margin: 0 0 0.75rem 0;
  }}
  [class*="st-key-civicai-doc-actions"] {{
    background: {LIGHT_BLUE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 0.7rem 1rem 0.8rem 1rem;
    margin: 0 0 0.4rem 0;
  }}
  [class*="st-key-civicai-verified"] h3 {{
    color: {SUCCESS};
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    margin: 0 0 0.4rem 0;
  }}
  [class*="st-key-civicai-rejected"] h3,
  [class*="st-key-civicai-review"] h3,
  [class*="st-key-civicai-pending"] h3,
  [class*="st-key-civicai-doc-info"] h3,
  [class*="st-key-civicai-doc-actions"] h3 {{
    color: {NAVY};
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    margin: 0 0 0.4rem 0;
  }}
  [class*="st-key-civicai-review"] h3 {{
    color: {CHARCOAL};
  }}
  [class*="st-key-civicai-verified"] [data-testid="stAlert"],
  [class*="st-key-civicai-rejected"] [data-testid="stAlert"],
  [class*="st-key-civicai-review"] [data-testid="stAlert"],
  [class*="st-key-civicai-pending"] [data-testid="stAlert"] {{
    background: transparent;
    border: 0;
  }}
</style>
"""


def _escape(value: str) -> str:
    return html.escape(str(value or ""), quote=True)


def apply_theme() -> None:
    """Apply the CivicAI visual system once per script run."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def current_user_name() -> str:
    name = (st.session_state.get("full_name") or "").strip()
    if name:
        return name
    return (st.session_state.get("email") or "").strip()


def status_badge(role: str | None) -> str:
    label = (role or "signed in").strip()
    css = f"civicai-badge civicai-badge-{_escape(label)}"
    return f'<span class="{css}">{_escape(label)}</span>'


def page_header(title: str, subtitle: str | None = None) -> None:
    extra = (
        f'<p class="civicai-page-subtitle">{_escape(subtitle)}</p>'
        if subtitle
        else ""
    )
    st.markdown(
        f'<div class="civicai-page-header">'
        f'<h1 class="civicai-page-title">{_escape(title)}</h1>'
        f"{extra}</div>",
        unsafe_allow_html=True,
    )


def section_header(title: str, caption: str | None = None) -> None:
    extra = (
        f'<p class="civicai-section-caption">{_escape(caption)}</p>'
        if caption
        else ""
    )
    st.markdown(
        f'<div class="civicai-section">'
        f'<h2 class="civicai-section-title">{_escape(title)}</h2>'
        f"{extra}</div>",
        unsafe_allow_html=True,
    )


def info_card(message: str) -> None:
    st.markdown(
        f'<div class="civicai-info">{_escape(message)}</div>',
        unsafe_allow_html=True,
    )


def empty_state(message: str) -> None:
    st.markdown(
        f'<div class="civicai-empty">{_escape(message)}</div>',
        unsafe_allow_html=True,
    )


def service_card(
    title: str,
    description: str,
    page: str | None = None,
    *,
    link_label: str | None = None,
) -> None:
    st.markdown(
        f'<div class="civicai-card"><h4>{_escape(title)}</h4>'
        f"<p>{_escape(description)}</p></div>",
        unsafe_allow_html=True,
    )
    if page:
        safe_page_link(page, link_label or f"Open {title}")


def render_service_cards(
    cards: Sequence[dict],
    *,
    columns: int = 2,
) -> None:
    rows = [list(cards[index : index + columns]) for index in range(0, len(cards), columns)]
    for row in rows:
        cols = st.columns(columns)
        for column, card in zip(cols, row):
            with column:
                service_card(
                    card["title"],
                    card["description"],
                    card.get("page"),
                    link_label=card.get("link_label"),
                )


def render_sidebar_brand() -> None:
    st.markdown(
        '<div class="civicai-brand">'
        '<p class="civicai-brand-name">CivicAI</p>'
        '<p class="civicai-brand-tag">Intelligent Citizen Service Platform</p>'
        "</div>",
        unsafe_allow_html=True,
    )


def render_sidebar_nav() -> None:
    """Grouped links to existing pages. Every role can still open every page."""
    st.markdown('<p class="civicai-nav-label">Navigation</p>', unsafe_allow_html=True)
    safe_page_link(page_path("app.py"), "Home")

    st.markdown('<p class="civicai-nav-label">Citizen services</p>', unsafe_allow_html=True)
    safe_page_link(page_path("pages", "1_Regulation_Assistant.py"), "Regulation Assistant")
    safe_page_link(page_path("pages", "2_Document_Verification.py"), "Document Verification")
    safe_page_link(page_path("pages", "3_Queue_Wait_Time.py"), "Queue Wait Time")
    safe_page_link(page_path("pages", "5_Eligibility_Nudge.py"), "Eligibility Nudge")
    safe_page_link(page_path("pages", "6_Feedback_Sentiment.py"), "Feedback Sentiment")

    st.markdown('<p class="civicai-nav-label">Officer</p>', unsafe_allow_html=True)
    safe_page_link(page_path("pages", "4_Officer_Dashboard.py"), "Officer Dashboard")
    st.caption("Queue Wait Time and document review use the pages listed above.")

    st.markdown('<p class="civicai-nav-label">Administrator</p>', unsafe_allow_html=True)
    st.caption("Regulation management is on Regulation Assistant. Officer tools use the dashboard.")


def render_signed_in_account(email: str, role: str | None, full_name: str | None) -> None:
    display_name = (full_name or "").strip() or email
    st.markdown(
        '<p class="civicai-account-label">Signed in as</p>'
        f'<p class="civicai-account-name">{_escape(display_name)}</p>'
        f'<p class="civicai-account-email">{_escape(email)}</p>'
        f"{status_badge(role)}",
        unsafe_allow_html=True,
    )


def apply_content_width(max_width: str = "48rem") -> None:
    """Keep this page's reading column narrower than the full wide layout."""
    st.markdown(
        f"<style>[data-testid='stMainBlockContainer']{{max-width:{max_width};"
        "padding-top:1.1rem;padding-bottom:2.4rem;}}</style>",
        unsafe_allow_html=True,
    )


def page_hero(title: str, subtitle: str, badge: str | None = None) -> None:
    badge_html = (
        f'<span class="civicai-hero-badge">{_escape(badge)}</span>' if badge else ""
    )
    st.markdown(
        f'<div class="civicai-hero">'
        f'<h1 class="civicai-hero-title">{_escape(title)}</h1>'
        f'<p class="civicai-hero-subtitle">{_escape(subtitle)}</p>'
        f"{badge_html}</div>",
        unsafe_allow_html=True,
    )


def kicker(label: str) -> None:
    st.markdown(
        f'<p class="civicai-kicker">{_escape(label)}</p>',
        unsafe_allow_html=True,
    )


@contextmanager
def surface(key: str) -> Iterator[None]:
    """Style a Streamlit container using the shared CivicAI surface keys."""
    with st.container(key=key):
        yield


def workflow_steps(steps: Sequence[str]) -> None:
    """Restrained workflow label. Steps are existing page stages, not metrics."""
    parts: list[str] = []
    for index, step in enumerate(steps):
        if index:
            parts.append('<span class="civicai-workflow-sep">→</span>')
        parts.append(f'<span class="civicai-workflow-step">{_escape(step)}</span>')
    st.markdown(f'<div class="civicai-workflow">{"".join(parts)}</div>', unsafe_allow_html=True)


_APPOINTMENT_STATUS_LABELS = {
    "scheduled": "Scheduled",
    "in_service": "In service",
    "completed": "Completed",
    "cancelled": "Cancelled",
}


def appointment_status_chip(status: str) -> None:
    """Label an existing appointment status. Unknown values are shown as-is."""
    key = (status or "").strip()
    label = _APPOINTMENT_STATUS_LABELS.get(key, key or "Unknown")
    css = f"civicai-status-chip civicai-status-{_escape(key)}" if key in _APPOINTMENT_STATUS_LABELS else "civicai-status-chip"
    st.markdown(f'<span class="{css}">{_escape(label)}</span>', unsafe_allow_html=True)


def predicted_wait_block(minutes_label: str) -> None:
    """Emphasize the existing predicted wait without inventing a number."""
    st.markdown(
        f'<p class="civicai-kicker">Predicted wait</p>'
        f'<p class="civicai-wait-value">{_escape(minutes_label)} minutes</p>'
        '<p class="civicai-section-caption">This is an estimate, not a guaranteed wait time.</p>',
        unsafe_allow_html=True,
    )


def info_rows(rows: Sequence[tuple[str, object]]) -> None:
    """Compact labelled rows. Empty values are omitted."""
    parts: list[str] = []
    for label, value in rows:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        parts.append(
            '<div class="civicai-info-row">'
            f'<span class="civicai-info-label">{_escape(label)}</span>'
            f'<span class="civicai-info-value">{_escape(text)}</span>'
            "</div>"
        )
    if parts:
        st.markdown("".join(parts), unsafe_allow_html=True)


def render_citations(citations: Sequence[dict]) -> None:
    """Render citation fields that the backend actually returned."""
    rows: list[str] = []
    for citation in citations:
        chips: list[str] = []
        if citation.get("scheme_name"):
            chips.append(
                f'<span class="civicai-chip">{_escape(citation["scheme_name"])}</span>'
            )
        if citation.get("circular_reference"):
            chips.append(
                '<span class="civicai-chip-muted">Circular: '
                f'{_escape(citation["circular_reference"])}</span>'
            )
        if citation.get("section"):
            chips.append(
                f'<span class="civicai-chip-muted">{_escape(citation["section"])}</span>'
            )
        if citation.get("source"):
            chips.append(
                '<span class="civicai-chip-muted">Source: '
                f'{_escape(citation["source"])}</span>'
            )
        if chips:
            rows.append(f'<div class="civicai-citation-row">{"".join(chips)}</div>')
    if rows:
        st.markdown("".join(rows), unsafe_allow_html=True)
