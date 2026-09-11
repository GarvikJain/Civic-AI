"""Validation for the synthetic queue dataset.

Invalid data is reported, not silently repaired.
"""

import pandas as pd

from ai_modules.queue_prediction.constants import (
    DATASET_COLUMNS,
    LEAKAGE_COLUMNS,
    OPEN_WEEKDAYS,
    SERVICE_TYPES,
    WEEKDAYS,
)


class DatasetValidationError(ValueError):
    """The generated dataset failed a sanity check."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetValidationError(message)


def validate_dataset(frame: pd.DataFrame, expected_rows: int | None = 15_000) -> None:
    """Raise DatasetValidationError if the frame is not a valid queue dataset."""
    missing_columns = [name for name in DATASET_COLUMNS if name not in frame.columns]
    _require(not missing_columns, f"Missing columns: {missing_columns}")

    extra_leakage = [name for name in LEAKAGE_COLUMNS if name in frame.columns]
    _require(not extra_leakage, f"Target-leaking columns are present: {extra_leakage}")

    if expected_rows is not None:
        _require(
            len(frame) == expected_rows,
            f"Expected {expected_rows} rows, found {len(frame)}.",
        )

    _require(frame[list(DATASET_COLUMNS)].notna().all().all(), "The dataset has missing values.")

    _require(
        frame["appointment_id"].nunique() == len(frame),
        "appointment_id is not unique.",
    )

    unknown_services = sorted(set(frame["service_type"].unique()) - set(SERVICE_TYPES))
    _require(not unknown_services, f"Unknown service_type values: {unknown_services}")
    _require(
        set(frame["service_type"].unique()) == set(SERVICE_TYPES),
        "The dataset does not contain all six service types.",
    )

    unknown_days = sorted(set(frame["day_of_week"].unique()) - set(WEEKDAYS))
    _require(not unknown_days, f"Unknown day_of_week values: {unknown_days}")

    _require((frame["queue_depth"] >= 0).all(), "queue_depth contains negative values.")
    _require(
        (frame["historical_service_time"] > 0).all(),
        "historical_service_time must be strictly positive.",
    )
    _require((frame["actual_wait_time"] >= 0).all(), "actual_wait_time contains negative values.")
    _require(frame["hour"].between(0, 23).all(), "hour is outside 0–23.")
    _require((frame["queue_depth"] <= 80).all(), "queue_depth is unrealistically high (> 80).")
    _require(
        (frame["historical_service_time"] <= 40).all(),
        "historical_service_time is unrealistically high (> 40 minutes).",
    )
    _require(
        (frame["actual_wait_time"] <= 240).all(),
        "actual_wait_time is unrealistically high (> 240 minutes).",
    )

    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    _require(timestamps.notna().all(), "timestamp contains values that are not datetimes.")
    _require(
        (timestamps.dt.hour == frame["hour"]).all(),
        "hour does not match timestamp.",
    )
    _require(
        (timestamps.dt.day_name() == frame["day_of_week"]).all(),
        "day_of_week does not match timestamp.",
    )

    # The simulated office is closed at night and on weekends.
    _require(
        timestamps.dt.hour.between(8, 17).all(),
        "Timestamps fall outside simulated office hours (08:30–17:30).",
    )
    minutes_past_midnight = timestamps.dt.hour * 60 + timestamps.dt.minute
    _require(
        (minutes_past_midnight >= 8 * 60 + 30).all()
        and (minutes_past_midnight <= 17 * 60 + 30).all(),
        "Timestamps fall outside 08:30–17:30.",
    )
    _require(
        frame["day_of_week"].isin(OPEN_WEEKDAYS).all(),
        "Weekend timestamps were generated even though the simulated office is closed.",
    )


def summarise_dataset(frame: pd.DataFrame) -> dict:
    """Counts and correlations used to inspect a generated dataset."""
    numeric = frame[["queue_depth", "historical_service_time", "actual_wait_time"]]
    return {
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "service_distribution": frame["service_type"].value_counts().to_dict(),
        "mean_queue_depth": float(frame["queue_depth"].mean()),
        "max_queue_depth": int(frame["queue_depth"].max()),
        "mean_historical_service_time": float(frame["historical_service_time"].mean()),
        "mean_actual_wait_time": float(frame["actual_wait_time"].mean()),
        "min_actual_wait_time": float(frame["actual_wait_time"].min()),
        "max_actual_wait_time": float(frame["actual_wait_time"].max()),
        "missing_value_count": int(frame.isna().sum().sum()),
        "corr_queue_depth_wait": float(
            numeric["queue_depth"].corr(numeric["actual_wait_time"])
        ),
        "corr_service_time_wait": float(
            numeric["historical_service_time"].corr(numeric["actual_wait_time"])
        ),
    }


def format_summary(summary: dict) -> str:
    """A printable report of summarise_dataset()."""
    distribution_lines = "\n".join(
        f"  {name}: {count}"
        for name, count in sorted(
            summary["service_distribution"].items(), key=lambda item: (-item[1], item[0])
        )
    )
    return (
        "Synthetic queue dataset (development data only; not real office statistics)\n"
        f"rows: {summary['rows']}\n"
        f"columns: {', '.join(summary['columns'])}\n"
        f"service distribution:\n{distribution_lines}\n"
        f"mean queue depth: {summary['mean_queue_depth']:.2f}\n"
        f"max queue depth: {summary['max_queue_depth']}\n"
        f"mean historical service time: {summary['mean_historical_service_time']:.2f} min\n"
        f"mean actual wait time: {summary['mean_actual_wait_time']:.2f} min\n"
        f"min/max actual wait time: {summary['min_actual_wait_time']:.2f} / "
        f"{summary['max_actual_wait_time']:.2f} min\n"
        f"missing values: {summary['missing_value_count']}\n"
        f"corr(queue_depth, actual_wait_time): {summary['corr_queue_depth_wait']:.3f}\n"
        f"corr(historical_service_time, actual_wait_time): "
        f"{summary['corr_service_time_wait']:.3f}"
    )
