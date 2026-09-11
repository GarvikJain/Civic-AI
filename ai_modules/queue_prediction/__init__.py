"""Queue Wait-Time Prediction.

Phase 6A: synthetic historical dataset.
Phase 6B: offline training and model comparison.
Phase 6C: live prediction from the selected queue-v1 artifact.

The dataset is simulated development data, not records from a real office.
Live predictions are estimates and have not been validated against real
government-office historical data.
"""

from ai_modules.queue_prediction.constants import (
    DATASET_COLUMNS,
    DEFAULT_N_RECORDS,
    DEFAULT_SEED,
    MODEL_VERSION,
    PREDICTION_FEATURES,
    SERVICE_TYPES,
)

__all__ = [
    "DATASET_COLUMNS",
    "DEFAULT_N_RECORDS",
    "DEFAULT_SEED",
    "MODEL_VERSION",
    "PREDICTION_FEATURES",
    "SERVICE_TYPES",
]
