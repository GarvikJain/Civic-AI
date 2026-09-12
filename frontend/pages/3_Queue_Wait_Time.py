"""Streamlit page for Module 3: Queue Wait-Time Prediction.

Citizens book their own visits. Officers start and complete service, which
records actual wait and attributes the appointment to that officer.
"""

from datetime import datetime, time, timedelta, timezone

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post
from utils.auth import current_role, sidebar_login
from utils.queue_display import (
    format_appointment_date,
    format_predicted_wait,
    sort_citizen_appointments,
    sort_officer_appointments,
)

SERVICE_TYPES = [
    "Income Certificate",
    "Residence Certificate",
    "Birth Certificate",
    "Caste Certificate",
    "Community Certificate",
    "Welfare Scheme Application",
]

st.title("Queue Wait-Time Prediction")
st.write(
    "Book a counter visit to see a live predicted wait. Officers can start "
    "and complete service from this page."
)

token = sidebar_login()
role = current_role()


def describe_error(error: HTTPError) -> str:
    try:
        return error.response.json().get("detail", error.response.text)
    except ValueError:
        return error.response.text


def default_slot() -> datetime:
    when = datetime.now(timezone.utc) + timedelta(days=1)
    while when.weekday() >= 5:
        when += timedelta(days=1)
    return when.replace(hour=10, minute=0, second=0, microsecond=0)


if not token:
    st.info("Please sign in from the sidebar to use the queue.")
elif role == "citizen":
    st.subheader("Book a visit")
    service_type = st.selectbox("Service", SERVICE_TYPES)
    default = default_slot()
    visit_date = st.date_input("Visit date", value=default.date())
    visit_time = st.time_input("Visit time", value=time(10, 0))
    if st.button("Create appointment", type="primary"):
        when = datetime.combine(visit_date, visit_time).replace(tzinfo=timezone.utc)
        try:
            created = post(
                "/queue/appointments",
                {
                    "service_type": service_type,
                    "appointment_date": when.isoformat(),
                },
                token=token,
            )
        except HTTPError as error:
            st.error(describe_error(error))
        except Exception:
            st.error("Backend is not reachable.")
        else:
            st.success(
                f"Appointment #{created['appointment_id']} booked. Queue "
                f"number {created.get('queue_number')}. Predicted wait: "
                f"{created.get('predicted_wait_time')} minutes."
            )

    st.subheader("Your appointments")
    try:
        appointments = get("/queue/appointments", token=token)
    except HTTPError as error:
        st.error(describe_error(error))
        appointments = []
    except Exception:
        st.error("Backend is not reachable.")
        appointments = []

    appointments = sort_citizen_appointments(appointments or [])
    if not appointments:
        st.caption("You have no appointments yet.")
    for row in appointments:
        with st.expander(
            f"#{row['appointment_id']} {row['service_type']} ({row['status']})"
        ):
            st.write(f"Appointment date: {format_appointment_date(row.get('appointment_date'))}")
            st.write(f"Queue number: {row.get('queue_number')}")
            st.write(
                f"Predicted wait: {format_predicted_wait(row.get('predicted_wait_time'))} minutes"
            )
            st.write(f"Current queue depth: {row.get('current_queue_depth')}")
            if row.get("officer_id"):
                st.caption(f"Handled by officer #{row['officer_id']}")
            if row["status"] in ("scheduled",):
                if st.button("Cancel", key=f"cancel-{row['appointment_id']}"):
                    try:
                        post(
                            f"/queue/appointments/{row['appointment_id']}/cancel",
                            {},
                            token=token,
                        )
                        st.rerun()
                    except HTTPError as error:
                        st.error(describe_error(error))
elif role in ("officer", "administrator"):
    st.subheader("Live office queue")
    st.caption("Any authorized officer may start a scheduled visit.")
    try:
        status = get("/queue/status", token=token)
    except HTTPError as error:
        st.error(describe_error(error))
        status = {"appointments": [], "queues": []}
    except Exception:
        st.error("Backend is not reachable.")
        status = {"appointments": [], "queues": []}

    queues = status.get("queues") or []
    if queues:
        st.dataframe(
            [
                {
                    "Service": row["service_type"],
                    "Date": row["appointment_date"],
                    "Queue depth": row["current_queue_depth"],
                }
                for row in queues
            ],
            hide_index=True,
            use_container_width=True,
        )

    live = sort_officer_appointments(status.get("appointments") or [])
    if not live:
        st.caption("No scheduled or in-service appointments.")
    for row in live:
        with st.expander(
            f"#{row['appointment_id']} {row['service_type']} ({row['status']})"
        ):
            st.write(f"Appointment date: {format_appointment_date(row.get('appointment_date'))}")
            st.write(f"Queue number: {row.get('queue_number')}")
            st.write(
                f"Predicted wait: {format_predicted_wait(row.get('predicted_wait_time'))} minutes"
            )
            st.write(f"Queue depth: {row.get('current_queue_depth')}")
            appointment_id = row["appointment_id"]
            start, complete = st.columns(2)
            if start.button("Start service", key=f"start-{appointment_id}"):
                try:
                    result = post(
                        f"/queue/appointments/{appointment_id}/start",
                        {},
                        token=token,
                    )
                    st.success(
                        f"Service started. Officer id {result.get('officer_id')}."
                    )
                    st.rerun()
                except HTTPError as error:
                    st.error(describe_error(error))
            if complete.button("Complete service", key=f"complete-{appointment_id}"):
                try:
                    post(
                        f"/queue/appointments/{appointment_id}/complete",
                        {},
                        token=token,
                    )
                    st.rerun()
                except HTTPError as error:
                    st.error(describe_error(error))
else:
    st.info("Sign in as a citizen to book, or as an officer to handle the queue.")
