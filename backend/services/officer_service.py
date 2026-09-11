"""Business logic for the Officer Productivity Dashboard.

Analytics are SQL aggregations over live CivicAI tables. This module does not
call Groq, retrain the queue model, or read the synthetic queue CSV.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import true

from ai_modules.document_verification.states import VerificationStatus
from ai_modules.feedback_sentiment.sentiment import (
    SENTIMENT_NEGATIVE,
    SENTIMENT_NEUTRAL,
    SENTIMENT_POSITIVE,
)
from ai_modules.feedback_sentiment.urgency import (
    URGENCY_HIGH,
    URGENCY_LOW,
    URGENCY_MEDIUM,
)
from ai_modules.queue_prediction.constants import SERVICE_TYPES
from backend.core.config import settings
from backend.models.appointment import Appointment
from backend.models.citizen_query import CitizenQuery
from backend.models.feedback import Feedback
from backend.models.government_document import GovernmentDocument
from backend.models.queue_prediction_record import QueuePredictionRecord
from backend.models.regulation import Regulation
from backend.schemas.common import MessageResponse
from backend.schemas.officer import (
    CountItem,
    DashboardOverview,
    DashboardSummary,
    DocumentAnalytics,
    FeedbackAnalytics,
    FeedbackServiceBreakdown,
    FlaggedFeedbackItem,
    QueryAnalytics,
    QueueAnalytics,
    RecentQuery,
    ServiceCount,
    WaitTrendPoint,
)
from backend.services import feedback_service, queue_service

REJECTION_REASON_LIMIT = 5
RECENT_QUERY_LIMIT = 8
FLAGGED_LIMIT = 50
QUERY_PREVIEW_LENGTH = 160

DASHBOARD_NOTES = [
    "CitizenQuery has no topic field; query frequency is grouped by regulation/scheme.",
    "Prediction error uses only queue_prediction_records with a non-null actual_wait_time. Missing actual wait is never treated as zero.",
    "Synthetic queue training CSV is not used. Figures come from live database rows.",
    "Appointment.officer_id is not assigned by the live queue API, so per-officer handling totals are not available.",
    "The service_type filter applies to appointments, wait records, feedback, and documents whose document_type matches. Regulation queries are not service-typed.",
]


class InvalidDashboardFilterError(ValueError):
    """period or service_type is not a supported dashboard filter."""


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Officer Productivity Dashboard",
        status="available",
        message=(
            "Officer analytics are aggregated from live CivicAI records. "
            "They do not use Groq or the synthetic queue training dataset."
        ),
    )


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _date_label(value: datetime) -> str:
    return _as_utc(value).astimezone(queue_service.office_tz()).date().isoformat()


def normalize_period(period: str) -> str:
    name = (period or "all").strip().lower().replace(" ", "_")
    if name == "all_time":
        return "all"
    if name not in ("today", "last_7_days", "last_30_days", "all"):
        raise InvalidDashboardFilterError(
            "period must be one of: today, last_7_days, last_30_days, all"
        )
    return name


def normalize_service_type(service_type: str | None) -> str | None:
    if service_type is None:
        return None
    value = service_type.strip()
    if not value:
        return None
    if value not in SERVICE_TYPES:
        raise InvalidDashboardFilterError(
            "service_type must be one of: " + ", ".join(SERVICE_TYPES)
        )
    return value


def period_bounds(
    period: str, now: datetime | None = None
) -> tuple[datetime | None, datetime | None]:
    """UTC start (inclusive) and end (exclusive) for an office-local period."""
    normalized = normalize_period(period)
    if normalized == "all":
        return None, None
    moment = _as_utc(now or queue_service.utcnow())
    zone = queue_service.office_tz()
    local = moment.astimezone(zone)
    start_today = datetime(local.year, local.month, local.day, tzinfo=zone)
    end = start_today + timedelta(days=1)
    span = {"today": 1, "last_7_days": 7, "last_30_days": 30}[normalized]
    start = start_today - timedelta(days=span - 1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _time_clauses(column, start: datetime | None, end: datetime | None) -> list:
    clauses = []
    if start is not None:
        clauses.append(column >= start)
    if end is not None:
        clauses.append(column < end)
    return clauses


def _where(query, clauses):
    if clauses:
        return query.where(*clauses)
    return query


def _count_by(db: Session, column, *clauses) -> dict[str | None, int]:
    query = select(column, func.count())
    query = _where(query, clauses).group_by(column)
    return {key: int(total) for key, total in db.execute(query)}


def _document_analytics(
    db: Session,
    start: datetime | None,
    end: datetime | None,
    service_type: str | None,
) -> DocumentAnalytics:
    clauses = _time_clauses(GovernmentDocument.upload_date, start, end)
    applied = False
    if service_type is not None:
        clauses.append(GovernmentDocument.document_type == service_type)
        applied = True
    counts = _count_by(db, GovernmentDocument.verification_status, *clauses)
    reasons = db.execute(
        select(GovernmentDocument.rejection_reason, func.count())
        .where(
            *clauses,
            GovernmentDocument.verification_status == VerificationStatus.REJECTED.value,
            GovernmentDocument.rejection_reason.is_not(None),
            GovernmentDocument.rejection_reason != "",
        )
        .group_by(GovernmentDocument.rejection_reason)
        .order_by(func.count().desc(), GovernmentDocument.rejection_reason)
        .limit(REJECTION_REASON_LIMIT)
    ).all()
    return DocumentAnalytics(
        total=sum(counts.values()),
        verified=counts.get(VerificationStatus.VERIFIED.value, 0),
        rejected=counts.get(VerificationStatus.REJECTED.value, 0),
        needs_review=counts.get(VerificationStatus.NEEDS_REVIEW.value, 0),
        pending=counts.get(VerificationStatus.PENDING.value, 0),
        processing=counts.get(VerificationStatus.PROCESSING.value, 0),
        top_rejection_reasons=[
            CountItem(label=reason, count=int(total)) for reason, total in reasons
        ],
        service_filter_applied=applied,
    )


def _queue_analytics(
    db: Session,
    start: datetime | None,
    end: datetime | None,
    service_type: str | None,
    today_start: datetime,
    today_end: datetime,
) -> QueueAnalytics:
    appointment_clauses = _time_clauses(Appointment.appointment_date, start, end)
    if service_type is not None:
        appointment_clauses.append(Appointment.service_type == service_type)

    total = int(
        db.scalar(
            _where(select(func.count()).select_from(Appointment), appointment_clauses)
        )
        or 0
    )
    today_clauses = _time_clauses(Appointment.appointment_date, today_start, today_end)
    if service_type is not None:
        today_clauses.append(Appointment.service_type == service_type)
    today_count = int(
        db.scalar(
            _where(select(func.count()).select_from(Appointment), today_clauses)
        )
        or 0
    )
    predicted_clauses = [
        *appointment_clauses,
        Appointment.predicted_wait_time.is_not(None),
    ]
    average_predicted = _round(
        db.scalar(
            _where(select(func.avg(Appointment.predicted_wait_time)), predicted_clauses)
        )
    )

    actual_clauses = [
        QueuePredictionRecord.actual_wait_time.is_not(None),
        *_time_clauses(Appointment.appointment_date, start, end),
    ]
    if service_type is not None:
        actual_clauses.append(Appointment.service_type == service_type)
    actual_row = db.execute(
        select(
            func.avg(QueuePredictionRecord.actual_wait_time),
            func.avg(
                func.abs(
                    QueuePredictionRecord.actual_wait_time
                    - QueuePredictionRecord.predicted_wait_time
                )
            ),
            func.count(),
        )
        .select_from(QueuePredictionRecord)
        .join(
            Appointment,
            QueuePredictionRecord.appointment_id == Appointment.appointment_id,
        )
        .where(*actual_clauses)
    ).one()
    average_actual = _round(actual_row[0])
    average_error = _round(actual_row[1])
    actual_count = int(actual_row[2] or 0)

    service_rows = db.execute(
        _where(
            select(
                Appointment.service_type,
                func.count(),
                func.avg(Appointment.predicted_wait_time),
            ),
            appointment_clauses,
        )
        .group_by(Appointment.service_type)
        .order_by(Appointment.service_type)
    ).all()
    by_service = [
        ServiceCount(
            service_type=name,
            count=int(count),
            average_predicted_wait=_round(avg_wait),
        )
        for name, count, avg_wait in service_rows
    ]

    appointment_rows = db.execute(
        _where(
            select(
                Appointment.appointment_id,
                Appointment.appointment_date,
                Appointment.predicted_wait_time,
            ),
            appointment_clauses,
        )
    ).all()
    actual_by_appointment = {
        appointment_id: actual
        for appointment_id, actual in db.execute(
            select(
                QueuePredictionRecord.appointment_id,
                func.avg(QueuePredictionRecord.actual_wait_time),
            )
            .join(
                Appointment,
                QueuePredictionRecord.appointment_id == Appointment.appointment_id,
            )
            .where(*actual_clauses)
            .group_by(QueuePredictionRecord.appointment_id)
        )
    }

    day_counts: dict[str, int] = {}
    day_predicted: dict[str, list[float]] = {}
    day_actual: dict[str, list[float]] = {}
    for appointment_id, when, predicted in appointment_rows:
        day = _date_label(when)
        day_counts[day] = day_counts.get(day, 0) + 1
        if predicted is not None:
            day_predicted.setdefault(day, []).append(float(predicted))
        actual = actual_by_appointment.get(appointment_id)
        if actual is not None:
            day_actual.setdefault(day, []).append(float(actual))

    trend = [
        WaitTrendPoint(
            date=day,
            appointments=day_counts[day],
            average_predicted_wait=_round(
                sum(day_predicted[day]) / len(day_predicted[day])
            )
            if day_predicted.get(day)
            else None,
            average_actual_wait=_round(sum(day_actual[day]) / len(day_actual[day]))
            if day_actual.get(day)
            else None,
        )
        for day in sorted(day_counts)
    ]

    return QueueAnalytics(
        total_appointments=total,
        today_appointments=today_count,
        average_predicted_wait=average_predicted,
        average_actual_wait=average_actual,
        average_absolute_error=average_error,
        records_with_actual_wait=actual_count,
        by_service_type=by_service,
        wait_time_trend=trend,
    )


def _query_analytics(
    db: Session, start: datetime | None, end: datetime | None
) -> QueryAnalytics:
    clauses = _time_clauses(CitizenQuery.query_time, start, end)
    total = int(
        db.scalar(_where(select(func.count()).select_from(CitizenQuery), clauses)) or 0
    )
    scheme_rows = db.execute(
        _where(
            select(Regulation.scheme_name, func.count())
            .select_from(CitizenQuery)
            .outerjoin(
                Regulation, CitizenQuery.regulation_id == Regulation.regulation_id
            ),
            clauses,
        )
        .group_by(Regulation.scheme_name)
        .order_by(func.count().desc(), Regulation.scheme_name)
    ).all()
    by_scheme = [
        CountItem(label=name or "Unspecified", count=int(count))
        for name, count in scheme_rows
    ]
    recent_rows = db.execute(
        _where(
            select(
                CitizenQuery.query_id,
                CitizenQuery.regulation_id,
                Regulation.scheme_name,
                CitizenQuery.query_text,
                CitizenQuery.query_time,
            )
            .select_from(CitizenQuery)
            .outerjoin(
                Regulation, CitizenQuery.regulation_id == Regulation.regulation_id
            ),
            clauses,
        )
        .order_by(CitizenQuery.query_time.desc(), CitizenQuery.query_id.desc())
        .limit(RECENT_QUERY_LIMIT)
    ).all()
    recent = []
    for query_id, regulation_id, scheme_name, text, when in recent_rows:
        preview = " ".join((text or "").split())
        if len(preview) > QUERY_PREVIEW_LENGTH:
            preview = preview[: QUERY_PREVIEW_LENGTH - 1].rstrip() + "…"
        recent.append(
            RecentQuery(
                query_id=query_id,
                regulation_id=regulation_id,
                scheme_name=scheme_name,
                query_preview=preview,
                query_time=when,
            )
        )
    return QueryAnalytics(
        total=total,
        by_scheme=by_scheme,
        recent=recent,
        service_filter_applied=False,
    )


def _feedback_analytics(
    db: Session,
    start: datetime | None,
    end: datetime | None,
    service_type: str | None,
) -> FeedbackAnalytics:
    clauses = _time_clauses(Feedback.date_submitted, start, end)
    if service_type is not None:
        clauses.append(Appointment.service_type == service_type)

    count_query = select(func.count()).select_from(Feedback)
    sentiment_query = select(Feedback.sentiment, func.count()).select_from(Feedback)
    urgency_query = select(Feedback.urgency, func.count()).select_from(Feedback)
    escalated_query = select(func.count()).select_from(Feedback)
    if service_type is not None:
        join = Appointment, Feedback.appointment_id == Appointment.appointment_id
        count_query = count_query.join(*join)
        sentiment_query = sentiment_query.join(*join)
        urgency_query = urgency_query.join(*join)
        escalated_query = escalated_query.join(*join)

    total = int(db.scalar(_where(count_query, clauses)) or 0)
    sentiments = {
        key: int(value)
        for key, value in db.execute(
            _where(sentiment_query, clauses).group_by(Feedback.sentiment)
        )
    }
    urgencies = {
        key: int(value)
        for key, value in db.execute(
            _where(urgency_query, clauses).group_by(Feedback.urgency)
        )
    }
    escalated = int(
        db.scalar(
            _where(
                escalated_query,
                [
                    *clauses,
                    Feedback.sentiment == SENTIMENT_NEGATIVE,
                    Feedback.urgency == URGENCY_HIGH,
                ],
            )
        )
        or 0
    )

    service_filter = (
        Appointment.service_type == service_type if service_type is not None else true()
    )
    service_rows = db.execute(
        select(
            Appointment.service_type,
            func.count(),
            func.sum(case((Feedback.sentiment == SENTIMENT_POSITIVE, 1), else_=0)),
            func.sum(case((Feedback.sentiment == SENTIMENT_NEUTRAL, 1), else_=0)),
            func.sum(case((Feedback.sentiment == SENTIMENT_NEGATIVE, 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(
                            Feedback.sentiment == SENTIMENT_NEGATIVE,
                            Feedback.urgency == URGENCY_HIGH,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
        )
        .select_from(Feedback)
        .join(Appointment, Feedback.appointment_id == Appointment.appointment_id)
        .where(*_time_clauses(Feedback.date_submitted, start, end), service_filter)
        .group_by(Appointment.service_type)
        .order_by(Appointment.service_type)
    ).all()
    by_service = [
        FeedbackServiceBreakdown(
            service_type=name,
            total=int(count or 0),
            positive=int(positive or 0),
            neutral=int(neutral or 0),
            negative=int(negative or 0),
            escalated=int(flagged or 0),
        )
        for name, count, positive, neutral, negative, flagged in service_rows
    ]
    return FeedbackAnalytics(
        total=total,
        positive=sentiments.get(SENTIMENT_POSITIVE, 0),
        neutral=sentiments.get(SENTIMENT_NEUTRAL, 0),
        negative=sentiments.get(SENTIMENT_NEGATIVE, 0),
        urgency_low=urgencies.get(URGENCY_LOW, 0),
        urgency_medium=urgencies.get(URGENCY_MEDIUM, 0),
        urgency_high=urgencies.get(URGENCY_HIGH, 0),
        escalated=escalated,
        by_service_type=by_service,
    )


def _flagged_items(
    db: Session,
    start: datetime | None,
    end: datetime | None,
    service_type: str | None,
) -> list[FlaggedFeedbackItem]:
    rows = feedback_service.list_flagged_feedback(
        db,
        since=start,
        until=end,
        service_type=service_type,
        limit=FLAGGED_LIMIT,
    )
    items = []
    for row in rows:
        service = row.appointment.service_type if row.appointment is not None else None
        items.append(
            FlaggedFeedbackItem(
                feedback_id=row.feedback_id,
                appointment_id=row.appointment_id,
                service_type=service,
                sentiment=row.sentiment or "",
                urgency=row.urgency or "",
                comments=row.comments or "",
                date_submitted=row.date_submitted,
            )
        )
    return items


def build_dashboard_summary(
    db: Session,
    *,
    period: str = "all",
    service_type: str | None = None,
) -> DashboardSummary:
    """Aggregate live records for the officer/admin dashboard."""
    normalized_period = normalize_period(period)
    normalized_service = normalize_service_type(service_type)
    now = queue_service.utcnow()
    start, end = period_bounds(normalized_period, now)
    today_start, today_end = period_bounds("today", now)

    documents = _document_analytics(db, start, end, normalized_service)
    queue = _queue_analytics(
        db, start, end, normalized_service, today_start, today_end
    )
    queries = _query_analytics(db, start, end)
    feedback = _feedback_analytics(db, start, end, normalized_service)
    flagged = _flagged_items(db, start, end, normalized_service)

    return DashboardSummary(
        module="Officer Productivity Dashboard",
        period=normalized_period,
        service_type=normalized_service,
        office_timezone=settings.office_timezone or "UTC",
        generated_at=now,
        overview=DashboardOverview(
            total_appointments=queue.total_appointments,
            average_predicted_wait=queue.average_predicted_wait,
            average_actual_wait=queue.average_actual_wait,
            documents_processed=documents.total,
            total_feedback=feedback.total,
            escalated_feedback=feedback.escalated,
        ),
        documents=documents,
        queue=queue,
        queries=queries,
        feedback=feedback,
        flagged_feedback=flagged,
        notes=list(DASHBOARD_NOTES),
    )
