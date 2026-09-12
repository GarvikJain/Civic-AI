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
from utils.ui import (
    apply_content_width,
    appointment_status_chip,
    empty_state,
    info_rows,
    kicker,
    page_hero,
    predicted_wait_block,
    surface,
    workflow_steps,
)

SERVICE_TYPES = [
    "Income Certificate",
    "Residence Certificate",
    "Birth Certificate",
    "Caste Certificate",
    "Community Certificate",
    "Welfare Scheme Application",
]

token = sidebar_login()
role = current_role()
apply_content_width()

page_hero(
    "Queue Wait Time",
    "Book a counter visit and view the predicted waiting time. Predictions are estimates, not a guaranteed wait.",
    badge="Live queue prediction",
)
workflow_steps(("Book a visit", "Predicted wait", "Your appointments"))


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


def show_prediction_panel(row: dict, *, slot: str) -> None:
    """Visual emphasis for values the backend already returned."""
    with surface(f"civicai-prediction-{slot}"):
        appointment_status_chip(row.get("status") or "")
        predicted_wait_block(format_predicted_wait(row.get("predicted_wait_time")))
        info_rows(
            (
                ("Service", row.get("service_type")),
                ("Queue number", row.get("queue_number")),
                ("Queue depth", row.get("current_queue_depth")),
                ("Status", row.get("status")),
            )
        )


if not token:
    st.info("Please sign in from the sidebar to use the queue.")
elif role == "citizen":
    with surface("civicai-book"):
        kicker("Appointment")
        st.subheader("Book a visit")
        st.caption(
            "Choose a service and visit time. CivicAI creates the appointment "
            "and returns a live predicted wait."
        )
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
                with surface("civicai-query-error-book"):
                    st.error(describe_error(error))
            except Exception:
                with surface("civicai-query-error-book"):
                    st.error("Backend is not reachable.")
            else:
                st.success(
                    f"Appointment #{created['appointment_id']} booked. Queue "
                    f"number {created.get('queue_number')}. Predicted wait: "
                    f"{created.get('predicted_wait_time')} minutes."
                )
                show_prediction_panel(created, slot="created")

    with surface("civicai-appointments"):
        kicker("Your records")
        st.subheader("Your appointments")
        try:
            appointments = get("/queue/appointments", token=token)
        except HTTPError as error:
            with surface("civicai-query-error-list"):
                st.error(describe_error(error))
            appointments = []
        except Exception:
            with surface("civicai-query-error-list"):
                st.error("Backend is not reachable.")
            appointments = []

        appointments = sort_citizen_appointments(appointments or [])
        if not appointments:
            empty_state("You have no appointments yet.")
        for row in appointments:
            with st.expander(
                f"#{row['appointment_id']} {row['service_type']} ({row['status']})"
            ):
                show_prediction_panel(row, slot=f"citizen-{row['appointment_id']}")
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
    with surface("civicai-officer"):
        kicker("Operations")
        st.subheader("Live office queue")
        st.caption("Any authorized officer may start a scheduled visit.")
        try:
            status = get("/queue/status", token=token)
        except HTTPError as error:
            with surface("civicai-query-error-officer"):
                st.error(describe_error(error))
            status = {"appointments": [], "queues": []}
        except Exception:
            with surface("civicai-query-error-officer"):
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
            empty_state("No scheduled or in-service appointments.")
        for row in live:
            with st.expander(
                f"#{row['appointment_id']} {row['service_type']} ({row['status']})"
            ):
                show_prediction_panel(row, slot=f"officer-{row['appointment_id']}")
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
