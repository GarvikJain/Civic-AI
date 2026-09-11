"""Service types used by the queue wait-time simulation.

These names are the only values allowed in the synthetic dataset. They are
development labels, not a claim about any real office's workload.
"""

from typing import Final

# The six CivicAI counter services, in a stable order.
SERVICE_TYPES: Final[tuple[str, ...]] = (
    "Income Certificate",
    "Residence Certificate",
    "Birth Certificate",
    "Caste Certificate",
    "Community Certificate",
    "Welfare Scheme Application",
)

# Approximate share of visits. Used only to sample the synthetic dataset.
SERVICE_WEIGHTS: Final[dict[str, float]] = {
    "Income Certificate": 0.25,
    "Residence Certificate": 0.20,
    "Birth Certificate": 0.20,
    "Caste Certificate": 0.12,
    "Community Certificate": 0.13,
    "Welfare Scheme Application": 0.10,
}

# Typical historical service duration for each counter, in minutes.
# (mean, standard deviation, clip_low, clip_high)
SERVICE_TIME_PARAMS: Final[dict[str, tuple[float, float, float, float]]] = {
    "Birth Certificate": (5.0, 0.55, 3.0, 8.0),
    "Residence Certificate": (6.0, 0.55, 3.5, 9.0),
    "Income Certificate": (8.0, 0.60, 5.0, 12.0),
    "Community Certificate": (9.0, 0.60, 6.0, 13.0),
    "Caste Certificate": (10.5, 0.85, 7.0, 16.0),
    "Welfare Scheme Application": (15.0, 1.80, 10.0, 24.0),
}

WEEKDAYS: Final[tuple[str, ...]] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

OPEN_WEEKDAYS: Final[tuple[str, ...]] = WEEKDAYS[:5]

DATASET_COLUMNS: Final[tuple[str, ...]] = (
    "appointment_id",
    "timestamp",
    "service_type",
    "day_of_week",
    "hour",
    "queue_depth",
    "historical_service_time",
    "actual_wait_time",
)

# Columns a future model may use at prediction time. actual_wait_time is the
# target and is deliberately not in this list.
PREDICTION_FEATURES: Final[tuple[str, ...]] = (
    "service_type",
    "day_of_week",
    "hour",
    "queue_depth",
    "historical_service_time",
)

LEAKAGE_COLUMNS: Final[tuple[str, ...]] = (
    "predicted_wait_time",
    "completed_service_duration",
    "completion_timestamp",
    "future_queue_depth",
    "actual_completion_time",
)

DEFAULT_N_RECORDS: Final[int] = 15_000
DEFAULT_SEED: Final[int] = 42

TARGET: Final[str] = "actual_wait_time"

CATEGORICAL_FEATURES: Final[tuple[str, ...]] = (
    "service_type",
    "day_of_week",
)

NUMERIC_FEATURES: Final[tuple[str, ...]] = (
    "hour",
    "queue_depth",
    "historical_service_time",
)

TRAIN_RATIO: Final[float] = 0.70
VALIDATION_RATIO: Final[float] = 0.15
TEST_RATIO: Final[float] = 0.15

MODEL_VERSION: Final[str] = "queue-v1"

# Classification baseline buckets. Medium includes both 15 and 30 minutes.
WAIT_CATEGORY_SHORT = "Short"
WAIT_CATEGORY_MEDIUM = "Medium"
WAIT_CATEGORY_LONG = "Long"
WAIT_SHORT_MAX_MINUTES: Final[float] = 15.0
WAIT_MEDIUM_MAX_MINUTES: Final[float] = 30.0

REGRESSION_MODEL_NAMES: Final[tuple[str, ...]] = (
    "RandomForestRegressor",
    "KNeighborsRegressor",
    "MLPRegressor",
)
