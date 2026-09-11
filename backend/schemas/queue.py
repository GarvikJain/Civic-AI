"""Pydantic schemas for live queue appointments and wait-time predictions.

Request and response models are separate. Extra client fields such as
queue_number or predicted_wait_time are rejected. Internal artifact paths are
never included.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_modules.queue_prediction.constants import SERVICE_TYPES


class AppointmentCreate(BaseModel):
    """Citizen-controlled fields for booking a counter visit."""

    model_config = ConfigDict(extra="forbid")

    service_type: str = Field(min_length=3, max_length=120)
    appointment_date: datetime

    @field_validator("service_type")
    @classmethod
    def service_type_must_be_supported(cls, value: str) -> str:
        if value not in SERVICE_TYPES:
            raise ValueError(
                "service_type must be one of: " + ", ".join(SERVICE_TYPES)
            )
        return value

    @field_validator("appointment_date")
    @classmethod
    def appointment_date_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            from datetime import timezone

            return value.replace(tzinfo=timezone.utc)
        return value


class AppointmentRead(BaseModel):
    """An appointment as returned to the caller who is allowed to see it."""

    model_config = ConfigDict(from_attributes=True)

    appointment_id: int
    citizen_id: int
    service_type: str
    appointment_date: datetime
    queue_number: int | None
    predicted_wait_time: float | None
    status: str
    model_version: str | None = None
    current_queue_depth: int | None = None
    updated_at: datetime | None = None
    queue_joined_at: datetime | None = None
    service_started_at: datetime | None = None
    service_completed_at: datetime | None = None
    officer_id: int | None = None


class QueuePredictionRead(BaseModel):
    """Live wait-time prediction for one appointment."""

    appointment_id: int
    service_type: str
    queue_number: int | None
    current_queue_depth: int
    predicted_wait_time: float
    model_version: str
    updated_at: datetime
    status: str
    refreshed: bool = False


class QueueStatusItem(BaseModel):
    """One appointment's queue information, without other citizens' data."""

    appointment_id: int
    service_type: str
    queue_number: int | None
    current_queue_depth: int
    predicted_wait_time: float | None
    status: str
    updated_at: datetime | None = None
    model_version: str | None = None
    appointment_date: datetime


class ServiceQueueDepth(BaseModel):
    """Office-wide depth for one service on one calendar day. No citizen PII."""

    service_type: str
    appointment_date: str
    current_queue_depth: int


class QueueStatusResponse(BaseModel):
    """Current queue information for the authenticated caller."""

    module: str = "Queue Wait-Time Prediction"
    status: str = "available"
    model_version: str | None = None
    appointments: list[QueueStatusItem] = Field(default_factory=list)
    queues: list[ServiceQueueDepth] = Field(default_factory=list)


class QueuePredictionRecordRead(BaseModel):
    """One stored prediction, including actual wait when it is known."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    appointment_id: int
    predicted_wait_time: float
    actual_wait_time: float | None
    predicted_at: datetime
    actual_recorded_at: datetime | None
    model_version: str
