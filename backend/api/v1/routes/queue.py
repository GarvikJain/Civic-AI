"""Module 3: Queue Wait-Time Prediction.

Citizens book a counter visit. The server assigns a queue number, counts the
live CivicAI queue, and predicts waiting time with the cached queue-v1 model.
The client cannot submit predicted_wait_time, queue_number, citizen_id or
model_version.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from ai_modules.queue_prediction.model_registry import ModelNotTrainedError
from ai_modules.queue_prediction.prediction_service import PredictionError
from backend.api.deps import require_role
from backend.core.roles import Role
from backend.db.session import get_db
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.queue import (
    AppointmentCreate,
    AppointmentRead,
    QueuePredictionRead,
    QueuePredictionRecordRead,
    QueueStatusResponse,
)
from backend.services import queue_service
from backend.services.citizen_service import CitizenProfileMissingError
from backend.services.queue_service import (
    InvalidAppointmentDateError,
    InvalidQueueTransitionError,
    QueueAppointmentNotFoundError,
)

router = APIRouter(prefix="/queue", tags=["queue-prediction"])

CitizenUser = Depends(require_role(Role.CITIZEN))
StaffUser = Depends(require_role(Role.OFFICER, Role.ADMINISTRATOR))
SignedInUser = Depends(
    require_role(Role.CITIZEN, Role.OFFICER, Role.ADMINISTRATOR)
)


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="The wait-time model is not available. No predicted wait was stored.",
    )


@router.get("/module", response_model=MessageResponse)
def module_status() -> MessageResponse:
    """Report that live queue prediction is available. Unauthenticated."""
    return queue_service.get_status()


@router.post(
    "/appointments",
    response_model=AppointmentRead,
    status_code=http_status.HTTP_201_CREATED,
)
def create_appointment(
    payload: AppointmentCreate,
    current_user: User = CitizenUser,
    db: Session = Depends(get_db),
) -> AppointmentRead:
    """Book a visit. Queue number and predicted wait are server-controlled."""
    try:
        return queue_service.create_appointment(db, current_user, payload)
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
    except InvalidAppointmentDateError as error:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(error)
        )
    except ModelNotTrainedError:
        db.rollback()
        raise _unavailable()
    except PredictionError:
        db.rollback()
        raise _unavailable()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the appointment.",
        )


@router.get("/appointments", response_model=list[AppointmentRead])
def list_appointments(
    current_user: User = CitizenUser, db: Session = Depends(get_db)
) -> list[AppointmentRead]:
    """The signed-in citizen's appointments."""
    try:
        rows = queue_service.list_own_appointments(db, current_user)
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
    return [queue_service.to_read_model(db, row) for row in rows]


@router.get("/appointments/{appointment_id}", response_model=AppointmentRead)
def get_appointment(
    appointment_id: int,
    current_user: User = SignedInUser,
    db: Session = Depends(get_db),
) -> AppointmentRead:
    """One appointment the caller is allowed to see."""
    try:
        appointment = queue_service.get_visible_appointment(
            db, current_user, appointment_id
        )
    except QueueAppointmentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
    return queue_service.to_read_model(db, appointment)


@router.get(
    "/appointments/{appointment_id}/history",
    response_model=list[QueuePredictionRecordRead],
)
def appointment_prediction_history(
    appointment_id: int,
    current_user: User = SignedInUser,
    db: Session = Depends(get_db),
) -> list[QueuePredictionRecordRead]:
    """Stored predicted vs actual waits for one appointment."""
    try:
        records = queue_service.list_prediction_records(
            db, current_user, appointment_id
        )
    except QueueAppointmentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    return [QueuePredictionRecordRead.model_validate(row) for row in records]


@router.get("/predict/{appointment_id}", response_model=QueuePredictionRead)
def predict_wait(
    appointment_id: int,
    current_user: User = SignedInUser,
    db: Session = Depends(get_db),
) -> QueuePredictionRead:
    """Current wait estimate. Recalculates when stale or the queue changed."""
    try:
        return queue_service.predict_for_appointment(db, current_user, appointment_id)
    except QueueAppointmentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except ModelNotTrainedError:
        db.rollback()
        raise _unavailable()
    except PredictionError:
        db.rollback()
        raise _unavailable()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update the prediction.",
        )


@router.get("/status", response_model=QueueStatusResponse)
def queue_status(
    appointment_id: int | None = Query(default=None),
    current_user: User = SignedInUser,
    db: Session = Depends(get_db),
) -> QueueStatusResponse:
    """Queue information for the signed-in user. No other citizen's private data."""
    try:
        return queue_service.queue_status(db, current_user, appointment_id)
    except QueueAppointmentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except CitizenProfileMissingError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )


@router.post("/appointments/{appointment_id}/start", response_model=AppointmentRead)
def start_service(
    appointment_id: int,
    current_user: User = StaffUser,
    db: Session = Depends(get_db),
) -> AppointmentRead:
    """Record that the counter has started serving this citizen."""
    try:
        return queue_service.start_service(db, current_user, appointment_id)
    except QueueAppointmentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except InvalidQueueTransitionError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )


@router.post("/appointments/{appointment_id}/complete", response_model=AppointmentRead)
def complete_appointment(
    appointment_id: int,
    current_user: User = StaffUser,
    db: Session = Depends(get_db),
) -> AppointmentRead:
    """Mark the visit finished. Actual wait is not invented here."""
    try:
        return queue_service.complete_appointment(db, current_user, appointment_id)
    except QueueAppointmentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except InvalidQueueTransitionError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentRead)
def cancel_appointment(
    appointment_id: int,
    current_user: User = SignedInUser,
    db: Session = Depends(get_db),
) -> AppointmentRead:
    """Withdraw an appointment that has not finished."""
    try:
        return queue_service.cancel_appointment(db, current_user, appointment_id)
    except QueueAppointmentNotFoundError as error:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    except InvalidQueueTransitionError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(error)
        )
