"""Streamlit page for Module 6: Citizen Feedback Sentiment Analysis.

Citizens submit comments for a completed appointment. Sentiment and urgency
are classified on the server. This page does not build the officer dashboard.
"""

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post
from utils.auth import sidebar_login
from utils.ui import (
    apply_content_width,
    feedback_analysis_rows,
    info_rows,
    kicker,
    page_hero,
    surface,
    workflow_steps,
)

SENTIMENT_LABELS = {
    "positive": "Positive",
    "neutral": "Neutral",
    "negative": "Negative",
}
URGENCY_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}

token = sidebar_login()
apply_content_width()

page_hero(
    "Feedback Sentiment",
    "Share your experience and help improve citizen services.",
    badge="Citizen feedback",
)
workflow_steps(
    ("Submit feedback", "Feedback analysis", "Sentiment and urgency", "Escalation if required")
)


def describe_error(error: HTTPError) -> str:
    """The backend's message for a failed request."""
    try:
        return error.response.json().get("detail", error.response.text)
    except ValueError:
        return error.response.text


def label_appointment(appointment: dict) -> str:
    when = appointment.get("appointment_date", "")
    return (
        f"#{appointment['appointment_id']} · {appointment['service_type']} · "
        f"{appointment['status']} · {when}"
    )


def _as_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 19 and text[4:5] == "-" and "T" in text:
        return text.replace("T", " ", 1).split(".")[0]
    return text


def show_feedback_result(item: dict, *, slot: str, saved: bool = False) -> None:
    """Present backend analysis once. Does not recalculate sentiment or urgency."""
    with surface(f"civicai-feedback-result-{slot}"):
        kicker("Feedback analysis")
        if saved:
            st.success(
                f"Feedback #{item['feedback_id']} saved for appointment "
                f"#{item['appointment_id']}."
            )
        feedback_analysis_rows(item["sentiment"], item["urgency"])
        info_rows(
            (
                ("Service", item.get("service_type")),
                ("Submitted", _as_text(item.get("date_submitted"))),
            )
        )
        if item.get("comments"):
            st.markdown("**Your comments**")
            st.write(item["comments"])
        if item.get("escalation_required"):
            st.markdown("**Flagged for officer attention**")
            st.warning("This feedback was flagged for officer attention.")


if not token:
    st.info("Please sign in from the sidebar to submit feedback.")
else:
    try:
        appointments = get("/queue/appointments", token=token)
        existing = get("/feedback", token=token)["feedbacks"]
    except HTTPError as error:
        if error.response.status_code == 403:
            with surface("civicai-query-error-forbidden"):
                st.error("Only citizens can submit feedback for their own appointments.")
                st.caption(
                    "Officers and administrators can read flagged items from "
                    "`GET /api/v1/officers/feedback/flagged` and the Officer "
                    "Productivity Dashboard."
                )
        else:
            with surface("civicai-query-error-feedback"):
                st.error(describe_error(error))
        appointments = []
        existing = []
    except Exception:
        with surface("civicai-query-error-feedback"):
            st.error("Backend is not reachable.")
        appointments = []
        existing = []

    already_reviewed = {item["appointment_id"] for item in existing}
    completed = [
        row
        for row in appointments
        if row.get("status") == "completed"
        and row["appointment_id"] not in already_reviewed
    ]

    last = st.session_state.get("last_feedback")
    if last:
        show_feedback_result(last, slot="latest", saved=True)

    with surface("civicai-feedback"):
        kicker("Feedback")
        st.subheader("Submit feedback")
        if not completed:
            st.info(
                "Feedback can be submitted only for a completed appointment that "
                "does not already have comments."
            )
        else:
            chosen = st.selectbox(
                "Completed appointment",
                completed,
                format_func=label_appointment,
            )
            comments = st.text_area(
                "Comments",
                max_chars=2000,
                height=160,
                help="Required. Maximum 2000 characters. The server will classify sentiment and urgency.",
            )
            if st.button("Submit feedback", type="primary"):
                if not comments.strip():
                    st.warning("Please enter a comment before submitting.")
                else:
                    try:
                        result = post(
                            "/feedback",
                            {
                                "appointment_id": chosen["appointment_id"],
                                "comments": comments.strip(),
                            },
                            token=token,
                        )
                    except HTTPError as error:
                        with surface("civicai-query-error-submit"):
                            st.error(describe_error(error))
                    except Exception:
                        with surface("civicai-query-error-submit"):
                            st.error("Backend is not reachable.")
                    else:
                        st.session_state["last_feedback"] = result
                        st.rerun()

    if existing:
        with surface("civicai-history"):
            kicker("History")
            st.subheader("Your previous feedback")
            for item in existing:
                sentiment = SENTIMENT_LABELS.get(item["sentiment"], item["sentiment"])
                urgency = URGENCY_LABELS.get(item["urgency"], item["urgency"])
                with st.expander(
                    f"#{item['feedback_id']} · {item.get('service_type') or 'service'} · "
                    f"{sentiment} / {urgency}"
                ):
                    show_feedback_result(item, slot=f"history-{item['feedback_id']}")
