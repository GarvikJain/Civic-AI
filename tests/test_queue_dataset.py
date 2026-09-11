"""Tests for the synthetic queue wait-time dataset (Phase 6A).

No model is trained here. These tests only check the generator and its
validation.
"""

from pathlib import Path

import pandas as pd
import pytest

from ai_modules.queue_prediction.constants import (
    DATASET_COLUMNS,
    DEFAULT_N_RECORDS,
    DEFAULT_SEED,
    LEAKAGE_COLUMNS,
    PREDICTION_FEATURES,
    SERVICE_TYPES,
    SERVICE_WEIGHTS,
)
from ai_modules.queue_prediction.dataset_generator import (
    generate_dataset,
    write_dataset,
)
from ai_modules.queue_prediction.validation import (
    DatasetValidationError,
    summarise_dataset,
    validate_dataset,
)


@pytest.fixture(scope="module")
def dataset() -> pd.DataFrame:
    return generate_dataset(n_records=DEFAULT_N_RECORDS, seed=DEFAULT_SEED)


def test_exact_row_count(dataset):
    assert len(dataset) == 15_000
    validate_dataset(dataset, expected_rows=15_000)


def test_generation_is_reproducible():
    first = generate_dataset(n_records=15_000, seed=42)
    second = generate_dataset(n_records=15_000, seed=42)
    pd.testing.assert_frame_equal(first, second)

    different = generate_dataset(n_records=15_000, seed=99)
    assert not first.equals(different)


def test_appointment_ids_are_unique(dataset):
    assert dataset["appointment_id"].nunique() == len(dataset)


def test_service_types_are_exactly_the_six_named_services(dataset):
    assert set(dataset["service_type"]) == set(SERVICE_TYPES)
    assert list(dataset.columns) == list(DATASET_COLUMNS)


def test_there_are_no_missing_values(dataset):
    assert dataset.isna().sum().sum() == 0


def test_numeric_ranges_are_valid(dataset):
    assert (dataset["queue_depth"] >= 0).all()
    assert (dataset["historical_service_time"] > 0).all()
    assert (dataset["actual_wait_time"] >= 0).all()
    assert dataset["hour"].between(8, 17).all()
    assert dataset["queue_depth"].max() <= 80
    assert dataset["historical_service_time"].max() <= 40
    assert dataset["actual_wait_time"].max() <= 240


def test_timestamp_matches_hour_and_weekday(dataset):
    stamps = pd.to_datetime(dataset["timestamp"])
    assert (stamps.dt.hour == dataset["hour"]).all()
    assert (stamps.dt.day_name() == dataset["day_of_week"]).all()
    minutes = stamps.dt.hour * 60 + stamps.dt.minute
    assert (minutes >= 8 * 60 + 30).all()
    assert (minutes <= 17 * 60 + 30).all()
    assert stamps.dt.day_name().isin(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    ).all()


def test_service_distribution_is_uneven_and_income_is_most_common(dataset):
    shares = dataset["service_type"].value_counts(normalize=True)
    assert shares.idxmax() == "Income Certificate"
    assert 0.18 <= shares["Income Certificate"] <= 0.32
    assert 0.15 <= shares["Residence Certificate"] <= 0.26
    assert 0.15 <= shares["Birth Certificate"] <= 0.26
    assert 0.07 <= shares["Caste Certificate"] <= 0.18
    assert 0.08 <= shares["Community Certificate"] <= 0.19
    assert 0.05 <= shares["Welfare Scheme Application"] <= 0.15
    # The intended sampling weights are the six services above.
    assert abs(sum(SERVICE_WEIGHTS.values()) - 1.0) < 1e-9


def test_queue_depth_and_wait_time_move_together(dataset):
    corr = dataset["queue_depth"].corr(dataset["actual_wait_time"])
    assert corr > 0


def test_service_time_and_wait_time_move_together(dataset):
    corr = dataset["historical_service_time"].corr(dataset["actual_wait_time"])
    assert corr > 0


def test_there_are_no_target_leakage_columns(dataset):
    assert "actual_wait_time" in dataset.columns
    for name in LEAKAGE_COLUMNS:
        assert name not in dataset.columns
    for name in PREDICTION_FEATURES:
        assert name in dataset.columns
    # The target is not one of the prediction-time features.
    assert "actual_wait_time" not in PREDICTION_FEATURES


def test_csv_round_trip(tmp_path: Path):
    frame = generate_dataset(n_records=200, seed=7)
    path = write_dataset(frame, tmp_path / "queue.csv")
    loaded = pd.read_csv(path)
    assert path.exists()
    assert len(loaded) == 200
    assert list(loaded.columns) == list(DATASET_COLUMNS)
    validate_dataset(loaded, expected_rows=200)


def test_validation_rejects_a_duplicate_id(dataset):
    broken = dataset.copy()
    broken.loc[1, "appointment_id"] = broken.loc[0, "appointment_id"]
    with pytest.raises(DatasetValidationError, match="not unique"):
        validate_dataset(broken, expected_rows=15_000)


def test_summary_reports_the_expected_fields(dataset):
    summary = summarise_dataset(dataset)
    assert summary["rows"] == 15_000
    assert summary["missing_value_count"] == 0
    assert set(summary["service_distribution"]) == set(SERVICE_TYPES)
    assert summary["corr_queue_depth_wait"] > 0
    assert summary["corr_service_time_wait"] > 0
