"""Pydantic schemas for the Officer Productivity Dashboard.

These models are read-only analytics. They do not include passwords, JWTs,
filesystem paths, OCR text, or stored filenames.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CountItem(BaseModel):
    """A labelled total, used for rejection reasons and scheme frequency."""

    label: str
    count: int


class ServiceCount(BaseModel):
    service_type: str
    count: int
    average_predicted_wait: float | None = None


class WaitTrendPoint(BaseModel):
    date: str
    appointments: int
    average_predicted_wait: float | None = None
    average_actual_wait: float | None = None


class DocumentAnalytics(BaseModel):
    total: int = 0
    verified: int = 0
    rejected: int = 0
    needs_review: int = 0
    pending: int = 0
    processing: int = 0
    top_rejection_reasons: list[CountItem] = Field(default_factory=list)
    service_filter_applied: bool = False


class QueueAnalytics(BaseModel):
    total_appointments: int = 0
    today_appointments: int = 0
    average_predicted_wait: float | None = None
    average_actual_wait: float | None = None
    average_absolute_error: float | None = None
    records_with_actual_wait: int = 0
    by_service_type: list[ServiceCount] = Field(default_factory=list)
    wait_time_trend: list[WaitTrendPoint] = Field(default_factory=list)


class RecentQuery(BaseModel):
    query_id: int
    regulation_id: int | None = None
    scheme_name: str | None = None
    query_preview: str
    query_time: datetime


class QueryAnalytics(BaseModel):
    total: int = 0
    by_scheme: list[CountItem] = Field(default_factory=list)
    recent: list[RecentQuery] = Field(default_factory=list)
    service_filter_applied: bool = False
    topic_limitation: str = (
        "CitizenQuery has no topic/category column. Frequency is grouped by "
        "regulation/scheme name, not by free-text topic classification."
    )


class FeedbackServiceBreakdown(BaseModel):
    service_type: str
    total: int = 0
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    escalated: int = 0


class FeedbackAnalytics(BaseModel):
    total: int = 0
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    urgency_low: int = 0
    urgency_medium: int = 0
    urgency_high: int = 0
    escalated: int = 0
    by_service_type: list[FeedbackServiceBreakdown] = Field(default_factory=list)


class FlaggedFeedbackItem(BaseModel):
    """Negative + high-urgency feedback an officer can act on."""

    model_config = ConfigDict(from_attributes=True)

    feedback_id: int
    appointment_id: int
    service_type: str | None = None
    sentiment: str
    urgency: str
    comments: str
    date_submitted: datetime


class DashboardOverview(BaseModel):
    total_appointments: int = 0
    average_predicted_wait: float | None = None
    average_actual_wait: float | None = None
    documents_processed: int = 0
    total_feedback: int = 0
    escalated_feedback: int = 0


class DashboardSummary(BaseModel):
    """Aggregated officer/admin analytics for one period and optional service."""

    module: str = "Officer Productivity Dashboard"
    period: str
    service_type: str | None = None
    office_timezone: str
    generated_at: datetime
    overview: DashboardOverview
    documents: DocumentAnalytics
    queue: QueueAnalytics
    queries: QueryAnalytics
    feedback: FeedbackAnalytics
    flagged_feedback: list[FlaggedFeedbackItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
