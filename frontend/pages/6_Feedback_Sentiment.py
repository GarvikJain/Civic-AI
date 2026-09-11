"""Streamlit page for Module 6: Citizen Feedback Sentiment Analysis.

Citizens submit comments for a completed appointment. Sentiment and urgency
are classified on the server. This page does not build the officer dashboard.
"""

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post
from utils.auth import sidebar_login

st.title("Citizen Feedback Sentiment")
st.write(
    "After a completed visit, leave a comment. CivicAI classifies sentiment "
    "and urgency on the server. You cannot choose those labels yourself."
)

token = sidebar_login()


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


if not token:
    st.info("Please sign in from the sidebar to submit feedback.")
else:
    try:
        appointments = get("/queue/appointments", token=token)
        existing = get("/feedback", token=token)["feedbacks"]
    except HTTPError as error:
        if error.response.status_code == 403:
            st.error("Only citizens can submit feedback for their own appointments.")
            st.caption(
                "Officers and administrators can read flagged items from "
                "`GET /api/v1/officers/feedback/flagged`. The productivity "
                "dashboard arrives in a later phase."
            )
        else:
            st.error(describe_error(error))
        appointments = []
        existing = []
    except Exception:
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
        st.success(
            f"Feedback #{last['feedback_id']} saved for appointment "
            f"#{last['appointment_id']}."
        )
        sentiment_col, urgency_col, escalation_col = st.columns(3)
        sentiment_col.metric("Sentiment", last["sentiment"])
        urgency_col.metric("Urgency", last["urgency"])
        escalation_col.metric(
            "Escalation", "Yes" if last["escalation_required"] else "No"
        )
        if last["escalation_required"]:
            st.warning("This feedback was flagged for officer attention.")

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
                    st.error(describe_error(error))
                except Exception:
                    st.error("Backend is not reachable.")
                else:
                    st.session_state["last_feedback"] = result
                    st.rerun()

    if existing:
        st.subheader("Your previous feedback")
        for item in existing:
            with st.expander(
                f"#{item['feedback_id']} · {item.get('service_type') or 'service'} · "
                f"{item['sentiment']} / {item['urgency']}"
            ):
                st.write(item["comments"])
                st.caption(
                    f"Submitted {item['date_submitted']} · "
                    f"escalation_required={item['escalation_required']}"
                )
