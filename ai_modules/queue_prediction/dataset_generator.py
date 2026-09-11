"""Synthetic historical dataset for queue wait-time model development.

This is simulated development data. It is not taken from a real government
office and must not be quoted as evidence of real waiting times.

Each row is one visit observed at the counter. The features are values that
would be known when the citizen joins the queue. The target is the wait that
was later recorded. Nothing is derived from the target.

Run:
    python -m ai_modules.queue_prediction.dataset_generator
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ai_modules.queue_prediction.constants import (
    DATASET_COLUMNS,
    DEFAULT_N_RECORDS,
    DEFAULT_SEED,
    SERVICE_TIME_PARAMS,
    SERVICE_TYPES,
    SERVICE_WEIGHTS,
)
from ai_modules.queue_prediction.validation import (
    format_summary,
    summarise_dataset,
    validate_dataset,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "queue_prediction" / "synthetic_queue_data.csv"
)

# Arrival intensity by hour during 08:30–17:30. Lunch is quieter; opening
# and late morning are busier. These are simulation knobs only.
_HOUR_VALUES = np.array([8, 9, 10, 11, 12, 13, 14, 15, 16, 17])
_HOUR_WEIGHTS = np.array([0.08, 0.16, 0.15, 0.13, 0.06, 0.08, 0.13, 0.11, 0.07, 0.03])
_HOUR_WEIGHTS = _HOUR_WEIGHTS / _HOUR_WEIGHTS.sum()

# Typical people already waiting when a citizen arrives, by hour.
_HOUR_QUEUE_BASE = {
    8: 8.0,
    9: 16.0,
    10: 20.0,
    11: 17.0,
    12: 5.0,
    13: 7.0,
    14: 14.0,
    15: 12.0,
    16: 8.0,
    17: 4.0,
}

# Monday is a little busier; Friday a little quieter.
_WEEKDAY_QUEUE_MULT = {
    0: 1.20,
    1: 1.10,
    2: 1.00,
    3: 0.98,
    4: 0.88,
}

# How stretched the counter is at that hour (affects wait, not a stored feature).
_HOUR_BUSY = {
    8: 1.20,
    9: 1.30,
    10: 1.35,
    11: 1.22,
    12: 0.70,
    13: 0.82,
    14: 1.15,
    15: 1.10,
    16: 1.00,
    17: 0.88,
}

# Popular counters tend to have a couple of extra people ahead.
_SERVICE_QUEUE_ADD = {
    "Income Certificate": 2.2,
    "Residence Certificate": 1.4,
    "Birth Certificate": 1.3,
    "Community Certificate": 0.4,
    "Caste Certificate": 0.3,
    "Welfare Scheme Application": 0.8,
}


def _sample_office_timestamps(rng: np.random.Generator, n: int) -> np.ndarray:
    """n timestamps on weekdays between 08:30 and 17:30 in 2024."""
    days = np.arange(
        np.datetime64("2024-01-01"),
        np.datetime64("2025-01-01"),
        dtype="datetime64[D]",
    )
    weekdays = days[np.is_busday(days)]
    chosen_days = weekdays[rng.integers(0, len(weekdays), size=n)]

    hours = rng.choice(_HOUR_VALUES, size=n, p=_HOUR_WEIGHTS)
    minutes = np.empty(n, dtype=np.int64)
    opening = hours == 8
    closing = hours == 17
    middle = ~opening & ~closing
    minutes[opening] = rng.integers(30, 60, size=int(opening.sum()))
    minutes[closing] = rng.integers(0, 31, size=int(closing.sum()))
    minutes[middle] = rng.integers(0, 60, size=int(middle.sum()))

    return chosen_days.astype("datetime64[m]") + hours * 60 + minutes


def _historical_service_times(rng: np.random.Generator, services: np.ndarray) -> np.ndarray:
    """Typical duration for this service, known before the citizen is seen.

    Drawn from the service's simulated range with noise. Not the duration of
    this visit, and not computed from actual_wait_time.
    """
    times = np.empty(len(services), dtype=np.float64)
    for name, (mean, std, low, high) in SERVICE_TIME_PARAMS.items():
        mask = services == name
        count = int(mask.sum())
        if count == 0:
            continue
        draws = rng.normal(mean, std, size=count)
        times[mask] = np.clip(draws, low, high)
    return np.round(times, 1)


def _queue_depths(
    rng: np.random.Generator,
    hours: np.ndarray,
    weekday_index: np.ndarray,
    services: np.ndarray,
) -> np.ndarray:
    """People already waiting, driven by hour, weekday and counter demand."""
    base = np.array([_HOUR_QUEUE_BASE[int(hour)] for hour in hours], dtype=np.float64)
    weekday_mult = np.array(
        [_WEEKDAY_QUEUE_MULT[int(day)] for day in weekday_index], dtype=np.float64
    )
    extra = np.array([_SERVICE_QUEUE_ADD[name] for name in services], dtype=np.float64)
    mean = np.clip(base * weekday_mult + extra, 0.5, None)
    # Poisson keeps depths as whole people and adds natural variation.
    depths = rng.poisson(mean)
    return depths.astype(np.int64)


def _actual_wait_times(
    rng: np.random.Generator,
    queue_depth: np.ndarray,
    historical_service_time: np.ndarray,
    hours: np.ndarray,
    weekday_index: np.ndarray,
) -> np.ndarray:
    """Simulate waiting time from the features, with operational noise.

    Wait grows with queue depth and with slower counters, and is stretched on
    busy hours. It is not queue_depth * historical_service_time.
    """
    busy = np.array([_HOUR_BUSY[int(hour)] for hour in hours], dtype=np.float64)
    # Monday residual backlog; Friday slightly faster clearing.
    weekday_pace = np.array(
        [1.08, 1.04, 1.00, 0.98, 0.92], dtype=np.float64
    )[weekday_index]

    # People ahead are a mix of services, not all the arriving citizen's type.
    mixed_counter_time = np.clip(rng.normal(8.2, 2.2, size=len(queue_depth)), 3.5, 18.0)
    # Several counters are open, so each person ahead is only a fraction of a
    # full service duration.
    per_person = (
        0.35 * historical_service_time + 0.65 * mixed_counter_time
    ) * rng.uniform(0.28, 0.52, size=len(queue_depth))

    noise = rng.normal(2.5, 4.5, size=len(queue_depth))
    wait = queue_depth * per_person * busy * weekday_pace + noise
    return np.round(np.clip(wait, 0.0, 180.0), 1)


def generate_dataset(
    n_records: int = DEFAULT_N_RECORDS, seed: int = DEFAULT_SEED
) -> pd.DataFrame:
    """Build a reproducible synthetic queue dataset as a DataFrame."""
    if n_records <= 0:
        raise ValueError("n_records must be a positive integer.")

    rng = np.random.default_rng(seed)
    timestamps = _sample_office_timestamps(rng, n_records)

    weights = np.array([SERVICE_WEIGHTS[name] for name in SERVICE_TYPES], dtype=np.float64)
    services = rng.choice(np.array(SERVICE_TYPES), size=n_records, p=weights)

    historical = _historical_service_times(rng, services)

    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps),
            "service_type": services,
            "historical_service_time": historical,
        }
    )
    frame["hour"] = frame["timestamp"].dt.hour
    frame["day_of_week"] = frame["timestamp"].dt.day_name()
    weekday_index = frame["timestamp"].dt.weekday.to_numpy()

    frame["queue_depth"] = _queue_depths(
        rng, frame["hour"].to_numpy(), weekday_index, frame["service_type"].to_numpy()
    )
    frame["actual_wait_time"] = _actual_wait_times(
        rng,
        frame["queue_depth"].to_numpy(),
        frame["historical_service_time"].to_numpy(),
        frame["hour"].to_numpy(),
        weekday_index,
    )

    frame = frame.sort_values("timestamp").reset_index(drop=True)
    frame.insert(0, "appointment_id", np.arange(1, n_records + 1, dtype=np.int64))
    return frame.loc[:, list(DATASET_COLUMNS)]


def write_dataset(
    frame: pd.DataFrame, path: Path | None = None
) -> Path:
    """Write the dataset as CSV and return the path used."""
    output = Path(path) if path is not None else DEFAULT_OUTPUT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return output


def main() -> None:
    frame = generate_dataset()
    validate_dataset(frame)
    summary = summarise_dataset(frame)
    path = write_dataset(frame)
    print(format_summary(summary))
    print(f"wrote: {path}")


if __name__ == "__main__":
    main()
