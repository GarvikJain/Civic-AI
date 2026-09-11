"""Queue Wait-Time Prediction.

Phase 6A is the synthetic historical dataset only. Model training and the
prediction API are not implemented yet.

The dataset is simulated development data, not records from a real office.
"""

from ai_modules.queue_prediction.constants import (
    DATASET_COLUMNS,
    DEFAULT_N_RECORDS,
    DEFAULT_SEED,
    PREDICTION_FEATURES,
    SERVICE_TYPES,
)

__all__ = [
    "DATASET_COLUMNS",
    "DEFAULT_N_RECORDS",
    "DEFAULT_SEED",
    "PREDICTION_FEATURES",
    "SERVICE_TYPES",
]
