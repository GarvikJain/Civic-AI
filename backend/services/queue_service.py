"""Live queue appointments, wait-time prediction, and prediction history.

Queue depth is counted from CivicAI Appointment rows only. The synthetic
training CSV is never read here.

Ownership is always:

    JWT -> User.id -> Citizen.user_id -> Citizen.citizen_id -> Appointment.citizen_id

Email is never used to decide who owns an appointment. The client cannot choose
citizen_id, queue_number, predicted_wait_time, actual_wait_time or model_version.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_modules.queue_prediction.constants import (
    MIN_COMPLETED_SERVICE_OBSERVATIONS,
    MODEL_VERSION,
    OPEN_WEEKDAYS,
    PREDICTION_FRESHNESS_SECONDS,
    SERVICE_TYPES,
    WEEKDAYS,
)
from ai_modules.queue_prediction.model_registry import ModelNotTrainedError
from ai_modules.queue_prediction.prediction_service import (
    PredictionError,
    WaitTimePrediction,
    baseline_historical_service_time,
    predict_wait_time,
)
from backend.core.config import settings
from backend.core.roles import Role
from backend.models.appointment import Appointment
from backend.models.queue_prediction_record import QueuePredictionRecord
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.queue import (
    AppointmentCreate,
    AppointmentRead,
    QueuePredictionRead,
    QueueStatusItem,
    QueueStatusResponse,
    ServiceQueueDepth,
)
from backend.services import citizen_service

STATUS_SCHEDULED = "scheduled"
STATUS_IN_SERVICE = "in_service"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

# Live queue depth counts these. Completed and cancelled are excluded.
ACTIVE_STATUSES = (STATUS_SCHEDULED, STATUS_IN_SERVICE)
TERMINAL_STATUSES = (STATUS_COMPLETED, STATUS_CANCELLED)

HISTORICAL_SOURCE_COMPLETED = "completed_history"
HISTORICAL_SOURCE_BASELINE = "configured_baseline"

# Historical service time uses completed CivicAI service history when
# available; otherwise the configured service baseline is used.


class QueueAppointmentNotFoundError(Exception):
    """The appointment does not exist, or this caller may not see it."""


class InvalidAppointmentDateError(ValueError):
    """The appointment date is malformed, in the past, or not a weekday."""


class InvalidQueueTransitionError(ValueError):
    """The requested status change is not allowed from the current status."""


@dataclass
class _CachedAppointmentPrediction:
    predicted_wait_time: float
    queue_depth: int
    model_version: str
    predicted_at: datetime
    historical_service_time: float


_prediction_lock = threading.Lock()
_prediction_cache: dict[int, _CachedAppointmentPrediction] = {}


def reset_prediction_cache() -> None:
    """Drop per-appointment prediction freshness entries. Tests only."""
    with _prediction_lock:
        _prediction_cache.clear()


def utcnow() -> datetime:
    """Clock hook so tests can advance the 60-second freshness window."""
    return datetime.now(timezone.utc)


def office_tz() -> tzinfo:
    """Timezone of the physical office's business day.

    CivicAI stores instants in UTC, which is the project-wide convention.
    Queue depth, queue numbers, and prediction hour/weekday are interpreted in
    this zone so a local office day is not split by UTC midnight. The default
    is UTC, matching existing timestamps and tests.
    """
    name = (settings.office_timezone or "UTC").strip()
    if name.upper() == "UTC":
        return timezone.utc
    return ZoneInfo(name)


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Queue Wait-Time Prediction",
        status="available",
        message=(
            "Live queue predictions use the cached queue-v1 model. "
            "Estimates are not a guarantee of waiting time."
        ),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _in_office_tz(value: datetime) -> datetime:
    return _as_utc(value).astimezone(office_tz())


def _day_bounds(when: datetime) -> tuple[datetime, datetime]:
    """UTC instants covering the office-local calendar day that contains `when`."""
    local = _in_office_tz(when)
    zone = office_tz()
    start_local = datetime(local.year, local.month, local.day, tzinfo=zone)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _calendar_date_label(when: datetime) -> str:
    return _in_office_tz(when).date().isoformat()


def _day_of_week(when: datetime) -> str:
    return WEEKDAYS[_in_office_tz(when).weekday()]


def _hour(when: datetime) -> int:
    return int(_in_office_tz(when).hour)


def _feature_when(appointment: Appointment, now: datetime) -> datetime:
    """Day/hour for a live prediction.

    Same office-local calendar day uses the current clock so the hour can move
    during a visit. Future slots keep the booked appointment time.
    """
    booked = _as_utc(appointment.appointment_date)
    current = _as_utc(now)
    if _in_office_tz(booked).date() == _in_office_tz(current).date():
        return current
    return booked


def validate_appointment_date(when: datetime, *, now: datetime | None = None) -> datetime:
    """Reject malformed, too-old, too-far, or weekend appointment times."""
    moment = _as_utc(when)
    clock = _as_utc(now or utcnow())
    if moment.year < 2000 or moment.year > clock.year + 2:
        raise InvalidAppointmentDateError("appointment_date is not a plausible date.")
    # Allow a small clock-skew window so "now" from the client is accepted.
    if moment < clock - timedelta(hours=1):
        raise InvalidAppointmentDateError("appointment_date cannot be in the past.")
    if _day_of_week(moment) not in OPEN_WEEKDAYS:
        raise InvalidAppointmentDateError(
            "Appointments are only available on weekdays (Monday to Friday)."
        )
    return moment


def get_current_queue_depth(
    db: Session,
    service_type: str,
    when: datetime,
    *,
    exclude_appointment_id: int | None = None,
) -> int:
    """Count active CivicAI appointments for this service on this office-local day.

    The day is the calendar date in OFFICE_TIMEZONE (UTC by default). Active
    means status is scheduled or in_service. completed and cancelled rows are
    excluded. The synthetic training CSV is not read.
    """
    start, end = _day_bounds(when)
    query = (
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.service_type == service_type,
            Appointment.appointment_date >= start,
            Appointment.appointment_date < end,
            Appointment.status.in_(ACTIVE_STATUSES),
        )
    )
    if exclude_appointment_id is not None:
        query = query.where(Appointment.appointment_id != exclude_appointment_id)
    return int(db.scalar(query) or 0)


def next_queue_number(db: Session, service_type: str, when: datetime) -> int:
    """Next server-assigned number for this service and office-local calendar day.

    Numbers are not reused after cancellation. The client cannot choose one.
    """
    start, end = _day_bounds(when)
    current_max = db.scalar(
        select(func.max(Appointment.queue_number)).where(
            Appointment.service_type == service_type,
            Appointment.appointment_date >= start,
            Appointment.appointment_date < end,
        )
    )
    return int(current_max or 0) + 1


def historical_service_time_for(
    db: Session,
    service_type: str,
    *,
    exclude_appointment_id: int | None = None,
) -> tuple[float, str]:
    """Minutes the counter typically takes for this service.

    Preferred source: mean (service_completed_at - service_started_at) from
    completed CivicAI appointments, excluding the current visit. At least
    MIN_COMPLETED_SERVICE_OBSERVATIONS observations are required.

    Fallback: the configured Phase 6A per-service baseline (the training
    historical_service_time mean). This fallback is a feature default, not a
    fabricated live wait observation and not this visit's duration.
    """
    query = select(Appointment.service_started_at, Appointment.service_completed_at).where(
        Appointment.service_type == service_type,
        Appointment.status == STATUS_COMPLETED,
        Appointment.service_started_at.is_not(None),
        Appointment.service_completed_at.is_not(None),
    )
    if exclude_appointment_id is not None:
        query = query.where(Appointment.appointment_id != exclude_appointment_id)

    durations: list[float] = []
    for started, completed in db.execute(query):
        elapsed = (_as_utc(completed) - _as_utc(started)).total_seconds() / 60.0
        if elapsed > 0 and elapsed < 24 * 60:
            durations.append(elapsed)

    if len(durations) >= MIN_COMPLETED_SERVICE_OBSERVATIONS:
        return float(sum(durations) / len(durations)), HISTORICAL_SOURCE_COMPLETED
    return baseline_historical_service_time(service_type), HISTORICAL_SOURCE_BASELINE


def _cache_get(appointment_id: int) -> _CachedAppointmentPrediction | None:
    with _prediction_lock:
        return _prediction_cache.get(appointment_id)


def _cache_put(appointment_id: int, entry: _CachedAppointmentPrediction) -> None:
    with _prediction_lock:
        _prediction_cache[appointment_id] = entry


def _cache_drop(appointment_id: int) -> None:
    with _prediction_lock:
        _prediction_cache.pop(appointment_id, None)


def prediction_is_fresh(
    entry: _CachedAppointmentPrediction | None,
    *,
    queue_depth: int,
    now: datetime,
) -> bool:
    """Reuse a prediction while it is younger than 60s and the queue is unchanged."""
    if entry is None:
        return False
    if int(entry.queue_depth) != int(queue_depth):
        return False
    age = (_as_utc(now) - _as_utc(entry.predicted_at)).total_seconds()
    return age < PREDICTION_FRESHNESS_SECONDS


def _run_model_prediction(
    *,
    service_type: str,
    when: datetime,
    queue_depth: int,
    historical_service_time: float,
) -> WaitTimePrediction:
    return predict_wait_time(
        service_type=service_type,
        day_of_week=_day_of_week(when),
        hour=_hour(when),
        queue_depth=queue_depth,
        historical_service_time=historical_service_time,
    )


def _add_prediction_record(
    db: Session,
    appointment: Appointment,
    prediction: WaitTimePrediction,
    *,
    predicted_at: datetime,
) -> QueuePredictionRecord:
    record = QueuePredictionRecord(
        appointment_id=appointment.appointment_id,
        predicted_wait_time=prediction.predicted_wait_time,
        actual_wait_time=None,
        predicted_at=predicted_at,
        actual_recorded_at=None,
        model_version=prediction.model_version,
    )
    db.add(record)
    return record


def _latest_prediction_record(
    db: Session, appointment_id: int
) -> QueuePredictionRecord | None:
    return db.scalar(
        select(QueuePredictionRecord)
        .where(QueuePredictionRecord.appointment_id == appointment_id)
        .order_by(QueuePredictionRecord.predicted_at.desc(), QueuePredictionRecord.id.desc())
        .limit(1)
    )


def create_appointment(
    db: Session, user: User, payload: AppointmentCreate
) -> AppointmentRead:
    """Create an appointment, predict wait server-side, and store history."""
    citizen = citizen_service.get_citizen_for_user(db, user.id)
    booked = validate_appointment_date(payload.appointment_date)
    if payload.service_type not in SERVICE_TYPES:
        raise PredictionError(
            "service_type must be one of: " + ", ".join(SERVICE_TYPES)
        )

    now = utcnow()
    # People already waiting: this appointment is not in the table yet.
    depth = get_current_queue_depth(db, payload.service_type, booked)
    history_minutes, _source = historical_service_time_for(db, payload.service_type)
    prediction = _run_model_prediction(
        service_type=payload.service_type,
        when=booked,
        queue_depth=depth,
        historical_service_time=history_minutes,
    )
    queue_number = next_queue_number(db, payload.service_type, booked)

    appointment = Appointment(
        citizen_id=citizen.citizen_id,
        officer_id=None,
        service_type=payload.service_type,
        appointment_date=booked,
        queue_number=queue_number,
        predicted_wait_time=prediction.predicted_wait_time,
        status=STATUS_SCHEDULED,
        queue_joined_at=now,
        service_started_at=None,
        service_completed_at=None,
    )
    db.add(appointment)
    try:
        db.flush()
        _add_prediction_record(db, appointment, prediction, predicted_at=now)
        db.commit()
        db.refresh(appointment)
    except Exception:
        db.rollback()
        raise

    _cache_put(
        appointment.appointment_id,
        _CachedAppointmentPrediction(
            predicted_wait_time=prediction.predicted_wait_time,
            queue_depth=depth,
            model_version=prediction.model_version,
            predicted_at=now,
            historical_service_time=history_minutes,
        ),
    )
    return to_read_model(db, appointment, model_version=prediction.model_version)


def _load_appointment(db: Session, appointment_id: int) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise QueueAppointmentNotFoundError("Appointment not found.")
    return appointment


def _citizen_owns(db: Session, user: User, appointment: Appointment) -> bool:
    citizen = citizen_service.find_citizen_for_user(db, user.id)
    if citizen is None:
        return False
    return appointment.citizen_id == citizen.citizen_id


def get_visible_appointment(
    db: Session, user: User, appointment_id: int
) -> Appointment:
    """Return an appointment this user is allowed to see.

    Citizens who do not own the row get the same not-found error as a missing
    id, so existence is not leaked. Officers and administrators may view any
    appointment.
    """
    try:
        appointment = _load_appointment(db, appointment_id)
    except QueueAppointmentNotFoundError:
        raise

    if user.role in (Role.OFFICER.value, Role.ADMINISTRATOR.value):
        return appointment
    if user.role == Role.CITIZEN.value and _citizen_owns(db, user, appointment):
        return appointment
    raise QueueAppointmentNotFoundError("Appointment not found.")


def list_own_appointments(db: Session, user: User) -> list[Appointment]:
    citizen = citizen_service.get_citizen_for_user(db, user.id)
    return list(
        db.scalars(
            select(Appointment)
            .where(Appointment.citizen_id == citizen.citizen_id)
            .order_by(Appointment.appointment_date.desc(), Appointment.appointment_id.desc())
        ).all()
    )


def predict_for_appointment(
    db: Session, user: User, appointment_id: int
) -> QueuePredictionRead:
    """Return a wait prediction, recomputing when stale or the queue changed."""
    appointment = get_visible_appointment(db, user, appointment_id)
    now = utcnow()
    when = _feature_when(appointment, now)
    depth = get_current_queue_depth(db, appointment.service_type, appointment.appointment_date)
    cached = _cache_get(appointment.appointment_id)
    if prediction_is_fresh(cached, queue_depth=depth, now=now) and cached is not None:
        return QueuePredictionRead(
            appointment_id=appointment.appointment_id,
            service_type=appointment.service_type,
            queue_number=appointment.queue_number,
            current_queue_depth=depth,
            predicted_wait_time=cached.predicted_wait_time,
            model_version=cached.model_version,
            updated_at=cached.predicted_at,
            status=appointment.status,
            refreshed=False,
        )

    history_minutes, _source = historical_service_time_for(
        db,
        appointment.service_type,
        exclude_appointment_id=appointment.appointment_id,
    )
    prediction = _run_model_prediction(
        service_type=appointment.service_type,
        when=when,
        queue_depth=depth,
        historical_service_time=history_minutes,
    )
    appointment.predicted_wait_time = prediction.predicted_wait_time
    try:
        _add_prediction_record(db, appointment, prediction, predicted_at=now)
        db.commit()
        db.refresh(appointment)
    except Exception:
        db.rollback()
        raise

    _cache_put(
        appointment.appointment_id,
        _CachedAppointmentPrediction(
            predicted_wait_time=prediction.predicted_wait_time,
            queue_depth=depth,
            model_version=prediction.model_version,
            predicted_at=now,
            historical_service_time=history_minutes,
        ),
    )
    return QueuePredictionRead(
        appointment_id=appointment.appointment_id,
        service_type=appointment.service_type,
        queue_number=appointment.queue_number,
        current_queue_depth=depth,
        predicted_wait_time=prediction.predicted_wait_time,
        model_version=prediction.model_version,
        updated_at=now,
        status=appointment.status,
        refreshed=True,
    )


def _record_actual_wait(db: Session, appointment: Appointment, now: datetime) -> None:
    if appointment.queue_joined_at is None or appointment.service_started_at is None:
        return
    elapsed = (
        _as_utc(appointment.service_started_at) - _as_utc(appointment.queue_joined_at)
    ).total_seconds() / 60.0
    if elapsed < 0:
        elapsed = 0.0
    records = list(
        db.scalars(
            select(QueuePredictionRecord).where(
                QueuePredictionRecord.appointment_id == appointment.appointment_id,
                QueuePredictionRecord.actual_wait_time.is_(None),
            )
        ).all()
    )
    for record in records:
        record.actual_wait_time = elapsed
        record.actual_recorded_at = now


def start_service(db: Session, user: User, appointment_id: int) -> AppointmentRead:
    """Officer/admin marks the counter as serving this citizen."""
    appointment = get_visible_appointment(db, user, appointment_id)
    if appointment.status != STATUS_SCHEDULED:
        raise InvalidQueueTransitionError(
            "Service can only be started for a scheduled appointment."
        )
    now = utcnow()
    appointment.status = STATUS_IN_SERVICE
    appointment.service_started_at = now
    _record_actual_wait(db, appointment, now)
    db.commit()
    db.refresh(appointment)
    _cache_drop(appointment.appointment_id)
    return to_read_model(db, appointment)


def complete_appointment(db: Session, user: User, appointment_id: int) -> AppointmentRead:
    """Officer/admin marks the visit finished. Does not invent actual wait."""
    appointment = get_visible_appointment(db, user, appointment_id)
    if appointment.status != STATUS_IN_SERVICE:
        raise InvalidQueueTransitionError(
            "An appointment must be in service before it can be completed."
        )
    now = utcnow()
    appointment.status = STATUS_COMPLETED
    appointment.service_completed_at = now
    db.commit()
    db.refresh(appointment)
    _cache_drop(appointment.appointment_id)
    return to_read_model(db, appointment)


def cancel_appointment(db: Session, user: User, appointment_id: int) -> AppointmentRead:
    """Citizen (own) or staff withdraw an appointment that has not finished."""
    appointment = get_visible_appointment(db, user, appointment_id)
    if appointment.status in TERMINAL_STATUSES:
        raise InvalidQueueTransitionError("This appointment is already closed.")
    if appointment.status == STATUS_IN_SERVICE and user.role == Role.CITIZEN.value:
        raise InvalidQueueTransitionError(
            "A visit that has already started cannot be cancelled by the citizen."
        )
    appointment.status = STATUS_CANCELLED
    db.commit()
    db.refresh(appointment)
    _cache_drop(appointment.appointment_id)
    return to_read_model(db, appointment)


def queue_status(
    db: Session, user: User, appointment_id: int | None = None
) -> QueueStatusResponse:
    """Queue information visible to this user. No other citizen's private data."""
    version = MODEL_VERSION
    if user.role == Role.CITIZEN.value:
        if appointment_id is not None:
            appointment = get_visible_appointment(db, user, appointment_id)
            item = _status_item(db, appointment)
            return QueueStatusResponse(
                model_version=item.model_version or version,
                appointments=[item],
            )
        items = [_status_item(db, row) for row in list_own_appointments(db, user)]
        return QueueStatusResponse(
            model_version=version if not items else items[0].model_version,
            appointments=items,
        )

    if appointment_id is not None:
        appointment = get_visible_appointment(db, user, appointment_id)
        item = _status_item(db, appointment)
        return QueueStatusResponse(
            model_version=item.model_version or version,
            appointments=[item],
        )

    today = utcnow()
    queues = [
        ServiceQueueDepth(
            service_type=service,
            appointment_date=_calendar_date_label(today),
            current_queue_depth=get_current_queue_depth(db, service, today),
        )
        for service in SERVICE_TYPES
    ]
    return QueueStatusResponse(model_version=version, queues=queues)


def _status_item(db: Session, appointment: Appointment) -> QueueStatusItem:
    depth = get_current_queue_depth(
        db, appointment.service_type, appointment.appointment_date
    )
    latest = _latest_prediction_record(db, appointment.appointment_id)
    return QueueStatusItem(
        appointment_id=appointment.appointment_id,
        service_type=appointment.service_type,
        queue_number=appointment.queue_number,
        current_queue_depth=depth,
        predicted_wait_time=appointment.predicted_wait_time,
        status=appointment.status,
        updated_at=latest.predicted_at if latest else appointment.queue_joined_at,
        model_version=latest.model_version if latest else None,
        appointment_date=appointment.appointment_date,
    )


def to_read_model(
    db: Session, appointment: Appointment, *, model_version: str | None = None
) -> AppointmentRead:
    latest = _latest_prediction_record(db, appointment.appointment_id)
    depth = get_current_queue_depth(
        db, appointment.service_type, appointment.appointment_date
    )
    return AppointmentRead(
        appointment_id=appointment.appointment_id,
        citizen_id=appointment.citizen_id,
        service_type=appointment.service_type,
        appointment_date=appointment.appointment_date,
        queue_number=appointment.queue_number,
        predicted_wait_time=appointment.predicted_wait_time,
        status=appointment.status,
        model_version=model_version or (latest.model_version if latest else None),
        current_queue_depth=depth,
        updated_at=latest.predicted_at if latest else appointment.queue_joined_at,
        queue_joined_at=appointment.queue_joined_at,
        service_started_at=appointment.service_started_at,
        service_completed_at=appointment.service_completed_at,
    )


def list_prediction_records(
    db: Session, user: User, appointment_id: int
) -> list[QueuePredictionRecord]:
    get_visible_appointment(db, user, appointment_id)
    return list(
        db.scalars(
            select(QueuePredictionRecord)
            .where(QueuePredictionRecord.appointment_id == appointment_id)
            .order_by(QueuePredictionRecord.predicted_at.asc(), QueuePredictionRecord.id.asc())
        ).all()
    )
