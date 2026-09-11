"""Serve wait-time predictions from the selected queue-v1 model.

This module does not train models and does not talk to FastAPI. The joblib
artifact (preprocessing + estimator) is loaded lazily and reused for the life
of the process. Negative model outputs are clamped to 0 at serving time; the
trained artifact is not modified.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ai_modules.queue_prediction.constants import (
    MODEL_VERSION,
    PREDICTION_FEATURES,
    SERVICE_TIME_PARAMS,
    SERVICE_TYPES,
    WEEKDAYS,
)
from ai_modules.queue_prediction.model_registry import (
    ModelNotTrainedError,
    load_selected_model,
    model_version,
)

_cache_lock = threading.Lock()
_cached_model = None
_cached_version: str | None = None
_model_load_count = 0


class PredictionError(ValueError):
    """The model could not produce a usable wait-time value."""


@dataclass(frozen=True)
class WaitTimePrediction:
    """A single wait-time estimate in minutes."""

    predicted_wait_time: float
    model_version: str
    clamped_from_negative: bool = False


def reset_model_cache() -> None:
    """Drop the process-local model. Used by tests, not by API requests."""
    global _cached_model, _cached_version, _model_load_count
    with _cache_lock:
        _cached_model = None
        _cached_version = None
        _model_load_count = 0


def model_load_count() -> int:
    """How many times the joblib artifact has been loaded in this process."""
    with _cache_lock:
        return _model_load_count


def get_cached_model():
    """Return the selected sklearn Pipeline, loading it at most once."""
    global _cached_model, _cached_version, _model_load_count
    with _cache_lock:
        if _cached_model is None:
            loaded = load_selected_model()
            version = model_version()
            _cached_model = loaded
            _cached_version = version
            _model_load_count += 1
        return _cached_model, _cached_version or MODEL_VERSION


def baseline_historical_service_time(service_type: str) -> float:
    """Configured typical counter duration (minutes) for this service.

    This is the Phase 6A/6B training baseline: the mean historical service
    time for the counter, not a live wait observation and not this visit's
    duration.
    """
    if service_type not in SERVICE_TIME_PARAMS:
        raise PredictionError(f"Unsupported service_type: {service_type}")
    return float(SERVICE_TIME_PARAMS[service_type][0])


def build_feature_frame(
    *,
    service_type: str,
    day_of_week: str,
    hour: int,
    queue_depth: int,
    historical_service_time: float,
) -> pd.DataFrame:
    """One-row frame with the exact training column order."""
    _validate_features(
        service_type=service_type,
        day_of_week=day_of_week,
        hour=hour,
        queue_depth=queue_depth,
        historical_service_time=historical_service_time,
    )
    row = {
        "service_type": service_type,
        "day_of_week": day_of_week,
        "hour": int(hour),
        "queue_depth": int(queue_depth),
        "historical_service_time": float(historical_service_time),
    }
    frame = pd.DataFrame([row], columns=list(PREDICTION_FEATURES))
    if list(frame.columns) != list(PREDICTION_FEATURES):
        raise PredictionError("Feature schema does not match training.")
    return frame


def _validate_features(
    *,
    service_type: str,
    day_of_week: str,
    hour: int,
    queue_depth: int,
    historical_service_time: float,
) -> None:
    if service_type not in SERVICE_TYPES:
        raise PredictionError(
            "service_type must be one of: " + ", ".join(SERVICE_TYPES)
        )
    if day_of_week not in WEEKDAYS:
        raise PredictionError("day_of_week must be a full weekday name.")
    try:
        hour_value = int(hour)
    except (TypeError, ValueError) as error:
        raise PredictionError("hour must be an integer 0-23.") from error
    if hour_value < 0 or hour_value > 23:
        raise PredictionError("hour must be an integer 0-23.")
    try:
        depth = int(queue_depth)
    except (TypeError, ValueError) as error:
        raise PredictionError("queue_depth must be a non-negative integer.") from error
    if depth < 0:
        raise PredictionError("queue_depth must be a non-negative integer.")
    try:
        service_time = float(historical_service_time)
    except (TypeError, ValueError) as error:
        raise PredictionError("historical_service_time must be a positive number.") from error
    if not np.isfinite(service_time) or service_time <= 0:
        raise PredictionError("historical_service_time must be a positive number.")


def predict_wait_time(
    service_type: str,
    day_of_week: str,
    hour: int,
    queue_depth: int,
    historical_service_time: float,
) -> WaitTimePrediction:
    """Predict waiting time in minutes using the cached queue-v1 model."""
    frame = build_feature_frame(
        service_type=service_type,
        day_of_week=day_of_week,
        hour=hour,
        queue_depth=queue_depth,
        historical_service_time=historical_service_time,
    )
    try:
        model, version = get_cached_model()
        raw = model.predict(frame)
    except ModelNotTrainedError:
        raise
    except PredictionError:
        raise
    except Exception as error:
        raise PredictionError("The wait-time model could not produce a prediction.") from error

    values = np.asarray(raw, dtype=float).reshape(-1)
    if values.size != 1:
        raise PredictionError("The wait-time model returned an unexpected shape.")
    value = float(values[0])
    if not np.isfinite(value):
        raise PredictionError("The wait-time model returned a non-finite value.")

    clamped = value < 0
    if clamped:
        value = 0.0
    return WaitTimePrediction(
        predicted_wait_time=value,
        model_version=str(version),
        clamped_from_negative=clamped,
    )
