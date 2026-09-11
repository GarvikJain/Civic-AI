"""Streamlit page for Module 4: Officer Productivity Dashboard.

Analytics come from GET /officers/dashboard/summary. The backend enforces
officer/administrator access. Citizens who open this page do not see metrics.
The document review queue from Phase 5 stays at the bottom.
"""

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post
from utils.auth import sidebar_login

SERVICE_TYPES = [
    "Income Certificate",
    "Residence Certificate",
    "Birth Certificate",
    "Caste Certificate",
    "Community Certificate",
    "Welfare Scheme Application",
]
PERIODS = {
    "Today": "today",
    "Last 7 days": "last_7_days",
    "Last 30 days": "last_30_days",
    "All time": "all",
}

st.title("Officer Productivity Dashboard")
st.write(
    "Operational metrics from live CivicAI records. This page does not call "
    "Groq and does not use the synthetic queue training dataset."
)

token = sidebar_login()


def describe_error(error: HTTPError) -> str:
    """The backend's message for a failed request."""
    try:
        return error.response.json().get("detail", error.response.text)
    except ValueError:
        return error.response.text


def minutes_label(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} min"


if not token:
    st.info("Please sign in as an officer or administrator from the sidebar.")
else:
    access_denied = False
    summary = None
    period_label = st.selectbox("Period", list(PERIODS.keys()), index=3)
    service_label = st.selectbox("Service", ["All services", *SERVICE_TYPES])
    params = {"period": PERIODS[period_label]}
    if service_label != "All services":
        params["service_type"] = service_label

    try:
        summary = get("/officers/dashboard/summary", token=token, params=params)
    except HTTPError as error:
        if error.response.status_code == 403:
            st.error("This dashboard is only available to officers and administrators.")
            access_denied = True
        elif error.response.status_code == 401:
            st.error("Please sign in again.")
            access_denied = True
        else:
            st.error(describe_error(error))
    except Exception:
        st.error("Backend is not reachable.")

    if summary is not None:
        overview = summary["overview"]
        documents = summary["documents"]
        queue = summary["queue"]
        queries = summary["queries"]
        feedback = summary["feedback"]

        st.caption(
            f"Timezone: {summary['office_timezone']} · period: {summary['period']}"
            + (
                f" · service: {summary['service_type']}"
                if summary.get("service_type")
                else ""
            )
        )

        st.subheader("Overview")
        one, two, three, four, five = st.columns(5)
        one.metric("Total appointments", overview["total_appointments"])
        two.metric("Avg predicted wait", minutes_label(overview["average_predicted_wait"]))
        three.metric("Avg actual wait", minutes_label(overview["average_actual_wait"]))
        four.metric("Documents processed", overview["documents_processed"])
        five.metric("Total feedback", overview["total_feedback"])

        st.subheader("Document verification")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Verified", documents["verified"])
        d2.metric("Rejected", documents["rejected"])
        d3.metric("Needs review", documents["needs_review"])
        d4.metric("Pending / processing", documents["pending"] + documents["processing"])
        reasons = documents.get("top_rejection_reasons") or []
        if reasons:
            st.markdown("**Top rejection reasons**")
            st.dataframe(
                [{"Reason": item["label"], "Count": item["count"]} for item in reasons],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("No rejection reasons in this period.")

        st.subheader("Queue performance")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Appointments", queue["total_appointments"])
        q2.metric("Today", queue["today_appointments"])
        q3.metric("Avg absolute error", minutes_label(queue["average_absolute_error"]))
        q4.metric("With actual wait", queue["records_with_actual_wait"])
        by_service = queue.get("by_service_type") or []
        if by_service:
            st.markdown("**Appointments by service**")
            st.bar_chart(
                {row["service_type"]: row["count"] for row in by_service}
            )
        trend = queue.get("wait_time_trend") or []
        if trend:
            st.markdown("**Wait-time trend**")
            st.dataframe(
                [
                    {
                        "Date": row["date"],
                        "Appointments": row["appointments"],
                        "Avg predicted": row["average_predicted_wait"],
                        "Avg actual": row["average_actual_wait"],
                    }
                    for row in trend
                ],
                hide_index=True,
                use_container_width=True,
            )
        st.caption(
            "Average actual wait and prediction error ignore visits that still "
            "have a null actual_wait_time."
        )

        st.subheader("Citizen queries")
        st.metric("Query volume", queries["total"])
        st.caption(queries["topic_limitation"])
        schemes = queries.get("by_scheme") or []
        if schemes:
            st.markdown("**Queries by regulation / scheme**")
            st.bar_chart({item["label"]: item["count"] for item in schemes})
        recent = queries.get("recent") or []
        if recent:
            st.markdown("**Recent queries**")
            st.dataframe(
                [
                    {
                        "When": item["query_time"],
                        "Scheme": item["scheme_name"] or "Unspecified",
                        "Preview": item["query_preview"],
                    }
                    for item in recent
                ],
                hide_index=True,
                use_container_width=True,
            )

        st.subheader("Citizen feedback")
        f1, f2, f3, f4, f5 = st.columns(5)
        f1.metric("Positive", feedback["positive"])
        f2.metric("Neutral", feedback["neutral"])
        f3.metric("Negative", feedback["negative"])
        f4.metric("High urgency", feedback["urgency_high"])
        f5.metric("Escalated", feedback["escalated"])
        by_feedback_service = feedback.get("by_service_type") or []
        if by_feedback_service:
            st.markdown("**Feedback by service**")
            st.dataframe(
                [
                    {
                        "Service": row["service_type"],
                        "Total": row["total"],
                        "Positive": row["positive"],
                        "Neutral": row["neutral"],
                        "Negative": row["negative"],
                        "Escalated": row["escalated"],
                    }
                    for row in by_feedback_service
                ],
                hide_index=True,
                use_container_width=True,
            )

        st.subheader("Flagged feedback")
        flagged = summary.get("flagged_feedback") or []
        if not flagged:
            st.success("No negative + high-urgency feedback in this view.")
        for item in flagged:
            with st.expander(
                f"#{item['feedback_id']} · {item.get('service_type') or 'service'} · "
                f"appointment {item['appointment_id']}"
            ):
                st.write(item["comments"])
                st.caption(
                    f"{item['sentiment']} / {item['urgency']} · {item['date_submitted']}"
                )

        with st.expander("Analytics notes"):
            for note in summary.get("notes") or []:
                st.markdown(f"- {note}")

    if not access_denied:
        st.divider()
        st.subheader("Documents needing review")

        try:
            review_docs = get("/officers/documents/review", token=token)["documents"]
        except HTTPError as error:
            if error.response.status_code == 403:
                review_docs = []
            else:
                st.error(describe_error(error))
                review_docs = []
        except Exception:
            review_docs = []

        if not review_docs:
            st.caption("Nothing is waiting for review.")
        for document in review_docs:
            with st.expander(
                f"#{document['document_id']} {document['document_type']} "
                f"(citizen {document['citizen_id']})"
            ):
                st.caption(f"OCR status: {document['ocr_status']}")
                if document.get("rejection_reason"):
                    st.markdown(
                        f"**Why it needs review:** {document['rejection_reason']}"
                    )
                fields = document.get("extracted_fields") or {}
                if fields:
                    for name, value in fields.items():
                        st.markdown(f"- {name.replace('_', ' ').title()}: {value}")
                document_id = document["document_id"]
                reason = st.text_input(
                    "Rejection reason", key=f"reason-{document_id}", max_chars=500
                )
                approve, reject = st.columns(2)
                if approve.button("Approve", key=f"approve-{document_id}"):
                    try:
                        post(
                            f"/officers/documents/{document_id}/approve",
                            {},
                            token=token,
                        )
                        st.rerun()
                    except HTTPError as error:
                        st.error(describe_error(error))
                if reject.button("Reject", key=f"reject-{document_id}"):
                    if len(reason.strip()) < 3:
                        st.warning(
                            "Please type the reason for rejecting the document."
                        )
                    else:
                        try:
                            post(
                                f"/officers/documents/{document_id}/reject",
                                {"reason": reason.strip()},
                                token=token,
                            )
                            st.rerun()
                        except HTTPError as error:
                            st.error(describe_error(error))
