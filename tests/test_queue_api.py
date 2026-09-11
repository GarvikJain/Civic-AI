"""API and live-queue tests for Phase 6C.

Queue depth is counted from Appointment rows. The synthetic training CSV is
never used as the live queue. Exact ML floating-point values are not asserted.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from sqlalchemy import func, select

from ai_modules.queue_prediction.constants import (
    MIN_COMPLETED_SERVICE_OBSERVATIONS,
    MODEL_VERSION,
    PREDICTION_FRESHNESS_SECONDS,
)
from ai_modules.queue_prediction.model_registry import ModelNotTrainedError
from ai_modules.queue_prediction.prediction_service import PredictionError
from backend.core.roles import Role
from backend.models.appointment import Appointment
from backend.models.citizen import Citizen
from backend.models.queue_prediction_record import QueuePredictionRecord
from backend.models.user import User
from backend.services import queue_service
from tests.factories import add_user, auth_header, citizen_header, role_header

CREATE_URL = "/api/v1/queue/appointments"


def booking_slot(days_ahead: int = 3, hour: int = 10) -> datetime:
    """A weekday slot far enough in the future to pass date validation."""
    when = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    while when.weekday() >= 5:
        when += timedelta(days=1)
    return when.replace(hour=hour, minute=0, second=0, microsecond=0)


def create_payload(service_type="Income Certificate", extra=None, **overrides):
    body = {
        "service_type": service_type,
        "appointment_date": booking_slot().isoformat(),
    }
    body.update(overrides)
    if extra:
        body.update(extra)
    return body


def create_appointment(client, headers, **overrides):
    return client.post(CREATE_URL, json=create_payload(**overrides), headers=headers)


def stored_appointments(session_factory) -> list[Appointment]:
    db = session_factory()
    try:
        return list(db.scalars(select(Appointment)).all())
    finally:
        db.close()


def stored_records(session_factory) -> list[QueuePredictionRecord]:
    db = session_factory()
    try:
        return list(db.scalars(select(QueuePredictionRecord)).all())
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _reset_prediction_cache():
    queue_service.reset_prediction_cache()
    yield
    queue_service.reset_prediction_cache()


# --- appointment creation ---------------------------------------------------


def test_citizen_can_create_appointment(client, session_factory):
    headers = citizen_header(client)
    response = create_appointment(client, headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["queue_number"] == 1
    assert body["predicted_wait_time"] is not None
    assert body["predicted_wait_time"] >= 0
    assert body["model_version"] == MODEL_VERSION
    assert body["status"] == "scheduled"
    rows = stored_appointments(session_factory)
    assert len(rows) == 1
    assert rows[0].predicted_wait_time == pytest.approx(body["predicted_wait_time"])
    assert rows[0].citizen_id == body["citizen_id"]


def test_unauthenticated_create_is_rejected(client):
    response = client.post(CREATE_URL, json=create_payload())
    assert response.status_code == 401


def test_officer_cannot_create_appointment(client, session_factory):
    headers = role_header(client, session_factory, Role.OFFICER)
    response = create_appointment(client, headers)
    assert response.status_code == 403


def test_invalid_service_is_rejected(client):
    headers = citizen_header(client)
    response = create_appointment(client, headers, service_type="Passport")
    assert response.status_code == 422


def test_client_cannot_set_server_controlled_fields(client, session_factory):
    headers = citizen_header(client)
    for extra in (
        {"queue_number": 99},
        {"predicted_wait_time": 3.0},
        {"citizen_id": 1},
        {"officer_id": 1},
        {"actual_wait_time": 12.0},
        {"model_version": "queue-v9"},
    ):
        response = client.post(
            CREATE_URL, json=create_payload(extra=extra), headers=headers
        )
        assert response.status_code == 422, extra
    assert stored_appointments(session_factory) == []


def test_server_assigns_sequential_queue_numbers(client):
    headers = citizen_header(client)
    first = create_appointment(client, headers)
    second = create_appointment(client, headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["queue_number"] == 1
    assert second.json()["queue_number"] == 2


def test_weekend_appointment_is_rejected(client):
    headers = citizen_header(client)
    saturday = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    response = create_appointment(
        client, headers, appointment_date=saturday.isoformat()
    )
    assert response.status_code == 400


def test_malformed_date_is_rejected(client):
    headers = citizen_header(client)
    response = client.post(
        CREATE_URL,
        json={"service_type": "Income Certificate", "appointment_date": "not-a-date"},
        headers=headers,
    )
    assert response.status_code == 422


# --- queue depth ------------------------------------------------------------


def test_active_appointments_count_and_terminal_statuses_are_excluded(
    client, session_factory
):
    citizen = citizen_header(client, "depth@example.com")
    officer = role_header(client, session_factory, Role.OFFICER)
    slot = booking_slot().isoformat()
    first = create_appointment(client, citizen, appointment_date=slot)
    second = create_appointment(client, citizen, appointment_date=slot)
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["current_queue_depth"] == 2

    start = client.post(
        f"/api/v1/queue/appointments/{first.json()['appointment_id']}/start",
        headers=officer,
    )
    assert start.status_code == 200
    complete = client.post(
        f"/api/v1/queue/appointments/{first.json()['appointment_id']}/complete",
        headers=officer,
    )
    assert complete.status_code == 200

    third = create_appointment(client, citizen, appointment_date=slot)
    # first is completed; second is still scheduled; third is the new arrival.
    assert third.json()["current_queue_depth"] == 2

    cancel = client.post(
        f"/api/v1/queue/appointments/{second.json()['appointment_id']}/cancel",
        headers=citizen,
    )
    assert cancel.status_code == 200
    fourth = create_appointment(client, citizen, appointment_date=slot)
    assert fourth.json()["current_queue_depth"] == 2


def test_live_queue_depth_does_not_read_synthetic_csv(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("synthetic CSV must not be read for live queue depth")

    monkeypatch.setattr(pd, "read_csv", boom)
    headers = citizen_header(client)
    response = create_appointment(client, headers)
    assert response.status_code == 201


def test_queue_depth_is_scoped_by_service_and_date(client):
    headers = citizen_header(client)
    slot = booking_slot()
    other_day = booking_slot(days_ahead=10)
    create_appointment(
        client, headers, appointment_date=slot.isoformat(), service_type="Income Certificate"
    )
    other_service = create_appointment(
        client,
        headers,
        appointment_date=slot.isoformat(),
        service_type="Birth Certificate",
    )
    other_date = create_appointment(
        client,
        headers,
        appointment_date=other_day.isoformat(),
        service_type="Income Certificate",
    )
    assert other_service.json()["queue_number"] == 1
    assert other_date.json()["queue_number"] == 1
    assert other_service.json()["current_queue_depth"] == 1


# --- historical service time ------------------------------------------------


def test_historical_service_time_uses_baseline_then_completed_history(
    client, session_factory
):
    db = session_factory()
    try:
        minutes, source = queue_service.historical_service_time_for(
            db, "Income Certificate"
        )
        assert source == queue_service.HISTORICAL_SOURCE_BASELINE
        assert minutes == 8.0
    finally:
        db.close()

    citizen = citizen_header(client, "history-src@example.com")
    officer = role_header(client, session_factory, Role.OFFICER)
    slot = booking_slot()
    created_ids = []
    for offset in range(MIN_COMPLETED_SERVICE_OBSERVATIONS):
        when = (slot + timedelta(minutes=offset)).isoformat()
        created = create_appointment(client, citizen, appointment_date=when)
        created_ids.append(created.json()["appointment_id"])

    db = session_factory()
    try:
        for index, appointment_id in enumerate(created_ids):
            appointment = db.get(Appointment, appointment_id)
            started = appointment.queue_joined_at
            appointment.status = queue_service.STATUS_COMPLETED
            appointment.service_started_at = started
            appointment.service_completed_at = started + timedelta(minutes=12 + index)
        db.commit()
        minutes, source = queue_service.historical_service_time_for(
            db, "Income Certificate"
        )
        assert source == queue_service.HISTORICAL_SOURCE_COMPLETED
        assert minutes == pytest.approx(14.0)
        excluded, _ = queue_service.historical_service_time_for(
            db, "Income Certificate", exclude_appointment_id=created_ids[0]
        )
        assert excluded != 12 + 0  # current visit duration is not used as the only value
    finally:
        db.close()


# --- ownership / RBAC -------------------------------------------------------


def test_citizen_can_view_own_appointment_not_anothers(client):
    first = citizen_header(client, "owner@example.com")
    second = citizen_header(client, "other@example.com")
    created = create_appointment(client, first)
    appointment_id = created.json()["appointment_id"]
    own = client.get(f"/api/v1/queue/appointments/{appointment_id}", headers=first)
    assert own.status_code == 200
    other = client.get(f"/api/v1/queue/appointments/{appointment_id}", headers=second)
    assert other.status_code == 404
    other_predict = client.get(
        f"/api/v1/queue/predict/{appointment_id}", headers=second
    )
    assert other_predict.status_code == 404
    other_status = client.get(
        f"/api/v1/queue/status?appointment_id={appointment_id}", headers=second
    )
    assert other_status.status_code == 404


def test_officer_and_admin_can_view_prediction(client, session_factory):
    citizen = citizen_header(client, "staff-view@example.com")
    created = create_appointment(client, citizen)
    appointment_id = created.json()["appointment_id"]
    officer = role_header(client, session_factory, Role.OFFICER)
    admin = role_header(client, session_factory, Role.ADMINISTRATOR)
    for headers in (officer, admin):
        response = client.get(
            f"/api/v1/queue/predict/{appointment_id}", headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["model_version"] == MODEL_VERSION
        assert "updated_at" in response.json()


# --- prediction API / refresh ----------------------------------------------


def test_prediction_endpoint_uses_current_queue_and_freshness(client, monkeypatch):
    headers = citizen_header(client, "refresh@example.com")
    first = create_appointment(client, headers)
    appointment_id = first.json()["appointment_id"]

    clock = {"now": datetime.now(timezone.utc)}
    monkeypatch.setattr(queue_service, "utcnow", lambda: clock["now"])

    warm = client.get(f"/api/v1/queue/predict/{appointment_id}", headers=headers)
    assert warm.status_code == 200
    assert warm.json()["current_queue_depth"] >= 1
    assert warm.json()["model_version"] == MODEL_VERSION

    reused = client.get(f"/api/v1/queue/predict/{appointment_id}", headers=headers)
    assert reused.status_code == 200
    assert reused.json()["refreshed"] is False

    create_appointment(client, headers)
    changed = client.get(f"/api/v1/queue/predict/{appointment_id}", headers=headers)
    assert changed.status_code == 200
    assert changed.json()["refreshed"] is True
    assert changed.json()["current_queue_depth"] >= 2

    clock["now"] = clock["now"] + timedelta(seconds=PREDICTION_FRESHNESS_SECONDS + 1)
    stale = client.get(f"/api/v1/queue/predict/{appointment_id}", headers=headers)
    assert stale.status_code == 200
    assert stale.json()["refreshed"] is True


def test_prediction_refresh_does_not_reload_model(client, monkeypatch):
    import ai_modules.queue_prediction.prediction_service as ps

    headers = citizen_header(client, "cache-model@example.com")
    created = create_appointment(client, headers)
    appointment_id = created.json()["appointment_id"]
    loads_before = ps.model_load_count()
    client.get(f"/api/v1/queue/predict/{appointment_id}", headers=headers)
    client.get(f"/api/v1/queue/predict/{appointment_id}", headers=headers)
    assert ps.model_load_count() == loads_before


# --- history / actual wait --------------------------------------------------


def test_prediction_history_starts_with_null_actual_wait(client, session_factory):
    headers = citizen_header(client, "hist@example.com")
    created = create_appointment(client, headers)
    appointment_id = created.json()["appointment_id"]
    records = stored_records(session_factory)
    assert len(records) == 1
    assert records[0].appointment_id == appointment_id
    assert records[0].predicted_wait_time == pytest.approx(
        created.json()["predicted_wait_time"]
    )
    assert records[0].actual_wait_time is None
    assert records[0].actual_recorded_at is None
    assert records[0].model_version == MODEL_VERSION

    history = client.get(
        f"/api/v1/queue/appointments/{appointment_id}/history", headers=headers
    )
    assert history.status_code == 200
    assert history.json()[0]["actual_wait_time"] is None


def test_actual_wait_is_recorded_only_on_service_start(client, session_factory, monkeypatch):
    citizen = citizen_header(client, "actual@example.com")
    officer = role_header(client, session_factory, Role.OFFICER)
    joined = datetime.now(timezone.utc)
    started = joined + timedelta(minutes=10)
    clock = {"now": joined}
    monkeypatch.setattr(queue_service, "utcnow", lambda: clock["now"])

    created = create_appointment(client, citizen)
    appointment_id = created.json()["appointment_id"]
    predicted = created.json()["predicted_wait_time"]

    clock["now"] = started
    response = client.post(
        f"/api/v1/queue/appointments/{appointment_id}/start", headers=officer
    )
    assert response.status_code == 200
    records = stored_records(session_factory)
    assert records[0].actual_wait_time == pytest.approx(10.0)
    assert records[0].actual_wait_time != pytest.approx(predicted)
    assert records[0].actual_recorded_at is not None
    assert records[0].predicted_wait_time == pytest.approx(predicted)


def test_queue_status_for_citizen_and_staff(client, session_factory):
    citizen = citizen_header(client, "status-user@example.com")
    created = create_appointment(client, citizen)
    status = client.get("/api/v1/queue/status", headers=citizen)
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "available"
    assert body["appointments"][0]["appointment_id"] == created.json()["appointment_id"]
    assert body["appointments"][0]["model_version"] == MODEL_VERSION

    unauth = client.get("/api/v1/queue/status")
    assert unauth.status_code == 401

    officer = role_header(client, session_factory, Role.OFFICER)
    office = client.get("/api/v1/queue/status", headers=officer)
    assert office.status_code == 200
    assert office.json()["queues"]
    assert "citizen_id" not in office.json()["queues"][0]


# --- errors -----------------------------------------------------------------


def test_missing_model_returns_controlled_error_without_creating_appointment(
    client, session_factory, monkeypatch
):
    def boom(*_args, **_kwargs):
        raise ModelNotTrainedError("missing")

    monkeypatch.setattr(queue_service, "_run_model_prediction", boom)
    headers = citizen_header(client, "nomodel@example.com")
    response = create_appointment(client, headers)
    assert response.status_code == 503
    assert "model" in response.json()["detail"].lower()
    assert "data/queue_prediction" not in response.json()["detail"]
    assert stored_appointments(session_factory) == []
    assert stored_records(session_factory) == []


def test_prediction_failure_does_not_fabricate_a_wait(
    client, session_factory, monkeypatch
):
    def boom(*_args, **_kwargs):
        raise PredictionError("failed")

    monkeypatch.setattr(queue_service, "_run_model_prediction", boom)
    headers = citizen_header(client, "failpred@example.com")
    response = create_appointment(client, headers)
    assert response.status_code == 503
    assert stored_appointments(session_factory) == []


def test_failure_after_flush_rolls_back(client, session_factory, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(queue_service, "_add_prediction_record", boom)
    headers = citizen_header(client, "rollback@example.com")
    response = create_appointment(client, headers)
    assert response.status_code == 500
    assert response.json()["detail"] == "Could not save the appointment."
    assert stored_appointments(session_factory) == []


def test_unknown_appointment_is_404(client):
    headers = citizen_header(client, "missing@example.com")
    response = client.get("/api/v1/queue/predict/99999", headers=headers)
    assert response.status_code == 404


def test_module_status_is_available(client):
    response = client.get("/api/v1/queue/module")
    assert response.status_code == 200
    assert response.json()["status"] == "available"


def test_e2e_queue_flow(client, session_factory):
    """Backend walkthrough of the Phase 6C citizen/officer flow."""
    first = citizen_header(client, "e2e-one@example.com")
    second = citizen_header(client, "e2e-two@example.com")
    officer = role_header(client, session_factory, Role.OFFICER)

    created = create_appointment(
        client, first, service_type="Income Certificate"
    )
    assert created.status_code == 201
    body = created.json()
    appointment_id = body["appointment_id"]
    assert body["queue_number"] >= 1
    assert body["predicted_wait_time"] >= 0
    assert body["model_version"] == MODEL_VERSION

    fetched = client.get(
        f"/api/v1/queue/appointments/{appointment_id}", headers=first
    )
    assert fetched.json()["predicted_wait_time"] == pytest.approx(body["predicted_wait_time"])

    status = client.get("/api/v1/queue/status", headers=first)
    assert status.json()["appointments"][0]["current_queue_depth"] >= 1

    predict = client.get(f"/api/v1/queue/predict/{appointment_id}", headers=first)
    assert predict.json()["model_version"] == MODEL_VERSION

    create_appointment(client, first, service_type="Income Certificate")
    again = client.get(f"/api/v1/queue/predict/{appointment_id}", headers=first)
    assert again.json()["current_queue_depth"] >= 2

    history = client.get(
        f"/api/v1/queue/appointments/{appointment_id}/history", headers=first
    )
    assert history.json()[0]["actual_wait_time"] is None

    start = client.post(
        f"/api/v1/queue/appointments/{appointment_id}/start", headers=officer
    )
    assert start.status_code == 200
    after_start = client.get(
        f"/api/v1/queue/appointments/{appointment_id}/history", headers=first
    )
    assert after_start.json()[0]["actual_wait_time"] is not None

    denied = client.get(f"/api/v1/queue/appointments/{appointment_id}", headers=second)
    assert denied.status_code == 404

    override = client.post(
        CREATE_URL,
        json=create_payload(extra={"predicted_wait_time": 1.0}),
        headers=first,
    )
    assert override.status_code == 422

    complete = client.post(
        f"/api/v1/queue/appointments/{appointment_id}/complete", headers=officer
    )
    assert complete.status_code == 200
    db = session_factory()
    try:
        active = db.scalar(
            select(func.count()).select_from(Appointment).where(
                Appointment.status.in_(queue_service.ACTIVE_STATUSES)
            )
        )
        completed = db.scalar(
            select(func.count()).select_from(Appointment).where(
                Appointment.status == queue_service.STATUS_COMPLETED
            )
        )
        assert completed >= 1
        assert active >= 1
    finally:
        db.close()


# --- office-local calendar day ----------------------------------------------

IST = timezone(timedelta(hours=5, minutes=30))


def _seed_boundary_appointments(session_factory) -> None:
    add_user(session_factory, "tz-boundary@example.com", Role.CITIZEN)
    db = session_factory()
    try:
        citizen = db.scalar(
            select(Citizen).join(User).where(User.email == "tz-boundary@example.com")
        )
        db.add_all(
            [
                Appointment(
                    citizen_id=citizen.citizen_id,
                    service_type="Income Certificate",
                    # Sunday 20:00 UTC = Monday 01:30 in UTC+05:30
                    appointment_date=datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc),
                    queue_number=1,
                    status=queue_service.STATUS_SCHEDULED,
                ),
                Appointment(
                    citizen_id=citizen.citizen_id,
                    service_type="Income Certificate",
                    # Monday 10:00 UTC = Monday 15:30 in UTC+05:30
                    appointment_date=datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc),
                    queue_number=2,
                    status=queue_service.STATUS_SCHEDULED,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_default_utc_office_timezone_keeps_utc_calendar_days(session_factory):
    _seed_boundary_appointments(session_factory)
    db = session_factory()
    try:
        sunday = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)
        monday = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
        assert queue_service.get_current_queue_depth(db, "Income Certificate", sunday) == 1
        assert queue_service.get_current_queue_depth(db, "Income Certificate", monday) == 1
        assert queue_service.next_queue_number(db, "Income Certificate", sunday) == 2
        assert queue_service.next_queue_number(db, "Income Certificate", monday) == 3
        assert queue_service._hour(monday) == 10
        assert queue_service._day_of_week(monday) == "Monday"
        assert queue_service._day_of_week(sunday) == "Sunday"
    finally:
        db.close()


def test_office_timezone_groups_queue_across_utc_midnight(session_factory, monkeypatch):
    monkeypatch.setattr(queue_service, "office_tz", lambda: IST)
    _seed_boundary_appointments(session_factory)
    db = session_factory()
    try:
        sunday_utc = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)
        monday_utc = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
        monday_local = datetime(2026, 9, 14, 10, 0, tzinfo=IST)
        assert queue_service.get_current_queue_depth(
            db, "Income Certificate", sunday_utc
        ) == 2
        assert queue_service.get_current_queue_depth(
            db, "Income Certificate", monday_utc
        ) == 2
        assert queue_service.get_current_queue_depth(
            db, "Income Certificate", monday_local
        ) == 2
        assert queue_service.next_queue_number(db, "Income Certificate", monday_local) == 3
        assert queue_service._hour(datetime(2026, 9, 14, 4, 30, tzinfo=timezone.utc)) == 10
        assert queue_service._day_of_week(sunday_utc) == "Monday"
        assert queue_service._hour(sunday_utc) == 1
    finally:
        db.close()
