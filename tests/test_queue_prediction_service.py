"""Tests for the cached queue-v1 wait-time prediction service (Phase 6C).

These tests use the trained artifact when it is present. They do not retrain
and they do not depend on exact floating-point metric values.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ai_modules.queue_prediction.constants import (
    MODEL_VERSION,
    PREDICTION_FEATURES,
    SERVICE_TYPES,
)
from ai_modules.queue_prediction.model_registry import (
    PROJECT_ROOT,
    selected_feature_schema,
)
from ai_modules.queue_prediction.prediction_service import (
    PredictionError,
    baseline_historical_service_time,
    build_feature_frame,
    get_cached_model,
    model_load_count,
    predict_wait_time,
    reset_model_cache,
)

ARTIFACT = PROJECT_ROOT / "data" / "queue_prediction" / "models" / "mlp.joblib"
requires_model = pytest.mark.skipif(
    not ARTIFACT.is_file(), reason="queue-v1 mlp.joblib is not present"
)


@requires_model
def test_selected_model_loads_and_is_cached():
    reset_model_cache()
    assert model_load_count() == 0
    model_a, version_a = get_cached_model()
    model_b, version_b = get_cached_model()
    assert version_a == MODEL_VERSION
    assert version_b == MODEL_VERSION
    assert model_a is model_b
    assert model_load_count() == 1
    assert "preprocess" in model_a.named_steps


@requires_model
def test_repeated_prediction_does_not_reload_artifact(monkeypatch):
    reset_model_cache()
    calls = {"n": 0}
    import ai_modules.queue_prediction.prediction_service as ps

    real = ps.load_selected_model

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(ps, "load_selected_model", wrapped)
    kwargs = dict(
        service_type="Income Certificate",
        day_of_week="Wednesday",
        hour=10,
        queue_depth=5,
        historical_service_time=8.0,
    )
    first = predict_wait_time(**kwargs)
    second = predict_wait_time(**kwargs)
    assert calls["n"] == 1
    assert model_load_count() == 1
    assert first.model_version == MODEL_VERSION
    assert second.model_version == MODEL_VERSION


@requires_model
def test_prediction_is_numeric_finite_and_non_negative():
    result = predict_wait_time(
        service_type="Income Certificate",
        day_of_week="Wednesday",
        hour=10,
        queue_depth=5,
        historical_service_time=8.0,
    )
    assert isinstance(result.predicted_wait_time, float)
    assert np.isfinite(result.predicted_wait_time)
    assert result.predicted_wait_time >= 0
    assert result.model_version == MODEL_VERSION


def test_feature_schema_matches_training():
    frame = build_feature_frame(
        service_type="Income Certificate",
        day_of_week="Monday",
        hour=11,
        queue_depth=3,
        historical_service_time=8.0,
    )
    assert list(frame.columns) == list(PREDICTION_FEATURES)
    if ARTIFACT.is_file():
        assert selected_feature_schema() == list(PREDICTION_FEATURES)


@requires_model
def test_service_specific_prediction_and_queue_depth_direction():
    low = predict_wait_time(
        service_type="Income Certificate",
        day_of_week="Wednesday",
        hour=10,
        queue_depth=5,
        historical_service_time=8.0,
    )
    high = predict_wait_time(
        service_type="Income Certificate",
        day_of_week="Wednesday",
        hour=10,
        queue_depth=20,
        historical_service_time=8.0,
    )
    assert high.predicted_wait_time > low.predicted_wait_time


@requires_model
def test_longer_historical_service_time_generally_increases_wait():
    shorter = predict_wait_time(
        service_type="Income Certificate",
        day_of_week="Wednesday",
        hour=11,
        queue_depth=10,
        historical_service_time=5.0,
    )
    longer = predict_wait_time(
        service_type="Income Certificate",
        day_of_week="Wednesday",
        hour=11,
        queue_depth=10,
        historical_service_time=20.0,
    )
    assert longer.predicted_wait_time > shorter.predicted_wait_time


def test_invalid_features_are_rejected():
    with pytest.raises(PredictionError):
        build_feature_frame(
            service_type="Passport",
            day_of_week="Monday",
            hour=10,
            queue_depth=1,
            historical_service_time=8.0,
        )
    with pytest.raises(PredictionError):
        predict_wait_time(
            service_type="Income Certificate",
            day_of_week="Funday",
            hour=10,
            queue_depth=1,
            historical_service_time=8.0,
        )
    with pytest.raises(PredictionError):
        predict_wait_time(
            service_type="Income Certificate",
            day_of_week="Monday",
            hour=10,
            queue_depth=-1,
            historical_service_time=8.0,
        )


def test_negative_model_output_is_clamped(monkeypatch):
    class Stub:
        def predict(self, frame):
            assert list(frame.columns) == list(PREDICTION_FEATURES)
            return np.array([-4.2])

    monkeypatch.setattr(
        "ai_modules.queue_prediction.prediction_service.get_cached_model",
        lambda: (Stub(), MODEL_VERSION),
    )
    result = predict_wait_time(
        service_type="Income Certificate",
        day_of_week="Monday",
        hour=10,
        queue_depth=1,
        historical_service_time=8.0,
    )
    assert result.predicted_wait_time == 0.0
    assert result.clamped_from_negative is True


def test_non_finite_model_output_is_an_error(monkeypatch):
    class Stub:
        def predict(self, frame):
            return np.array([np.nan])

    monkeypatch.setattr(
        "ai_modules.queue_prediction.prediction_service.get_cached_model",
        lambda: (Stub(), MODEL_VERSION),
    )
    with pytest.raises(PredictionError):
        predict_wait_time(
            service_type="Income Certificate",
            day_of_week="Monday",
            hour=10,
            queue_depth=1,
            historical_service_time=8.0,
        )


def test_baseline_historical_service_time_uses_configured_means():
    assert baseline_historical_service_time("Income Certificate") == 8.0
    assert baseline_historical_service_time("Welfare Scheme Application") == 15.0
    assert set(SERVICE_TYPES)


def test_synthetic_csv_is_not_imported_by_prediction_service():
    source = Path(
        "ai_modules/queue_prediction/prediction_service.py"
    ).read_text(encoding="utf-8")
    assert "synthetic_queue_data" not in source
    assert "read_csv" not in source
