"""Metrics and wait-time categories for queue models."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)

from ai_modules.queue_prediction.constants import (
    WAIT_CATEGORY_LONG,
    WAIT_CATEGORY_MEDIUM,
    WAIT_CATEGORY_SHORT,
    WAIT_MEDIUM_MAX_MINUTES,
    WAIT_SHORT_MAX_MINUTES,
)

WAIT_CATEGORY_LABELS = (
    WAIT_CATEGORY_SHORT,
    WAIT_CATEGORY_MEDIUM,
    WAIT_CATEGORY_LONG,
)


def wait_category(minutes: float) -> str:
    """Map a wait in minutes to Short / Medium / Long."""
    if minutes < WAIT_SHORT_MAX_MINUTES:
        return WAIT_CATEGORY_SHORT
    if minutes <= WAIT_MEDIUM_MAX_MINUTES:
        return WAIT_CATEGORY_MEDIUM
    return WAIT_CATEGORY_LONG


def wait_categories(values) -> np.ndarray:
    """Vectorised wait_category()."""
    return np.array([wait_category(float(value)) for value in values], dtype=object)


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    """MAE, RMSE and R². Predictions are not clipped; this is the honest score."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    return {
        "mae": mae,
        "rmse": rmse,
        "r2": float(r2_score(y_true, y_pred)),
        "n": int(len(y_true)),
        "min_prediction": float(np.min(y_pred)) if len(y_pred) else float("nan"),
        "max_prediction": float(np.max(y_pred)) if len(y_pred) else float("nan"),
        "negative_prediction_count": int(np.sum(y_pred < 0)),
    }


def classification_metrics(y_true, y_pred) -> dict:
    """Accuracy, precision, recall, F1 and confusion matrix for wait buckets."""
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)
    labels = list(WAIT_CATEGORY_LABELS)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(
            precision_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
        ),
        "recall_macro": float(
            recall_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
        ),
        "f1_macro": float(
            f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
        ),
        "labels": labels,
        "confusion_matrix": confusion_matrix(
            y_true, y_pred, labels=labels
        ).tolist(),
        "n": int(len(y_true)),
    }


def overfitting_flag(train_mae: float, validation_mae: float) -> bool:
    """True when validation MAE is much worse than training MAE."""
    if train_mae <= 0:
        return validation_mae > 1.0
    return validation_mae > train_mae * 1.75 and (validation_mae - train_mae) > 3.0
