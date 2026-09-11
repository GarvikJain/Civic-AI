"""Preprocessing for queue wait-time models.

Categorical columns are one-hot encoded. Numeric columns are standardised.
The transformer is fitted only on the training split; validation and test data
are transformed with those same statistics.
"""

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ai_modules.queue_prediction.constants import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    PREDICTION_FEATURES,
    TARGET,
)


def feature_frame(frame):
    """Prediction-time columns only. The target is never included."""
    missing = [name for name in PREDICTION_FEATURES if name not in frame.columns]
    if missing:
        raise ValueError(f"Dataset is missing prediction features: {missing}")
    if TARGET in PREDICTION_FEATURES:
        raise ValueError("The target must not be a prediction-time feature.")
    return frame.loc[:, list(PREDICTION_FEATURES)].copy()


def target_series(frame):
    """The wait-time target, in minutes."""
    if TARGET not in frame.columns:
        raise ValueError(f"Dataset is missing the target column {TARGET}.")
    return frame[TARGET].astype(float).copy()


def build_preprocessor() -> ColumnTransformer:
    """A fresh preprocessor. Call fit() only on the training features."""
    return ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                list(CATEGORICAL_FEATURES),
            ),
            (
                "numeric",
                StandardScaler(),
                list(NUMERIC_FEATURES),
            ),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )


def build_model_pipeline(estimator) -> Pipeline:
    """Preprocessing and the estimator in one object, saved together."""
    return Pipeline(
        steps=[
            ("preprocess", build_preprocessor()),
            ("model", estimator),
        ]
    )
