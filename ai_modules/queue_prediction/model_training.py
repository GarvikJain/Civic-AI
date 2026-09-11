"""Train, compare and persist queue wait-time models.

Run:
    python -m ai_modules.queue_prediction.model_training

This loads the synthetic CSV, splits it chronologically, trains Random Forest,
KNN and MLP regressors, picks the best one by validation MAE, then scores that
one model on the held-out test set. A Logistic Regression classifier is trained
separately as a wait-bucket baseline. Nothing here is a live prediction API.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn import __version__ as sklearn_version
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsRegressor
from sklearn.neural_network import MLPRegressor

from ai_modules.queue_prediction.constants import (
    DEFAULT_SEED,
    MODEL_VERSION,
    PREDICTION_FEATURES,
    REGRESSION_MODEL_NAMES,
    TARGET,
    TEST_RATIO,
    TRAIN_RATIO,
    VALIDATION_RATIO,
)
from ai_modules.queue_prediction.dataset_generator import DEFAULT_OUTPUT_PATH as DATASET_PATH
from ai_modules.queue_prediction.evaluation import (
    classification_metrics,
    overfitting_flag,
    regression_metrics,
    wait_categories,
)
from ai_modules.queue_prediction.model_registry import to_project_relative
from ai_modules.queue_prediction.preprocessing import (
    build_model_pipeline,
    feature_frame,
    target_series,
)
from ai_modules.queue_prediction.validation import validate_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "data" / "queue_prediction" / "models"
EVALUATION_JSON = PROJECT_ROOT / "data" / "queue_prediction" / "model_evaluation.json"
EVALUATION_CSV = PROJECT_ROOT / "data" / "queue_prediction" / "model_evaluation.csv"

# Modest, documented settings. This is an academic comparison, not a search.
REGRESSION_SPECS = {
    "RandomForestRegressor": {
        "n_estimators": 120,
        "max_depth": 12,
        "min_samples_leaf": 5,
        "random_state": DEFAULT_SEED,
        "n_jobs": 1,
    },
    "KNeighborsRegressor": {
        "n_neighbors": 15,
        "weights": "distance",
    },
    "MLPRegressor": {
        "hidden_layer_sizes": (32, 16),
        "max_iter": 400,
        "early_stopping": True,
        "validation_fraction": 0.1,
        "random_state": DEFAULT_SEED,
        "alpha": 1e-3,
    },
}

LOGISTIC_SPEC = {
    "max_iter": 500,
    "class_weight": "balanced",
    "random_state": DEFAULT_SEED,
}

ARTIFACT_FILES = {
    "RandomForestRegressor": "random_forest.joblib",
    "KNeighborsRegressor": "knn.joblib",
    "MLPRegressor": "mlp.joblib",
    "LogisticRegression": "logistic_regression.joblib",
}


def load_dataset(path: Path | None = None) -> pd.DataFrame:
    """Load and validate the synthetic queue CSV."""
    csv_path = Path(path) if path is not None else DATASET_PATH
    frame = pd.read_csv(csv_path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    validate_dataset(frame, expected_rows=None)
    leaked = [name for name in PREDICTION_FEATURES if name == TARGET]
    if leaked:
        raise ValueError("Prediction features include the target.")
    return frame


def chronological_split(
    frame: pd.DataFrame,
    train_ratio: float = TRAIN_RATIO,
    validation_ratio: float = VALIDATION_RATIO,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Oldest train_ratio → train, next validation_ratio → val, remainder → test."""
    if train_ratio <= 0 or validation_ratio <= 0 or train_ratio + validation_ratio >= 1:
        raise ValueError("Split ratios must be positive and leave a test remainder.")

    ordered = frame.sort_values("timestamp").reset_index(drop=True)
    n = len(ordered)
    n_train = int(n * train_ratio)
    n_val = int(n * validation_ratio)
    if n_train == 0 or n_val == 0 or n_train + n_val >= n:
        raise ValueError(f"Not enough rows ({n}) for a 70/15/15 chronological split.")

    train = ordered.iloc[:n_train].copy()
    validation = ordered.iloc[n_train : n_train + n_val].copy()
    test = ordered.iloc[n_train + n_val :].copy()
    return train, validation, test


def split_ranges(train, validation, test) -> dict:
    """Timestamp span and row counts for each split."""
    def _range(part: pd.DataFrame) -> dict:
        stamps = pd.to_datetime(part["timestamp"])
        return {
            "rows": int(len(part)),
            "start": stamps.min().isoformat(),
            "end": stamps.max().isoformat(),
        }

    return {"train": _range(train), "validation": _range(validation), "test": _range(test)}


def _assert_chronological(train, validation, test) -> None:
    train_end = pd.to_datetime(train["timestamp"]).max()
    val_start = pd.to_datetime(validation["timestamp"]).min()
    val_end = pd.to_datetime(validation["timestamp"]).max()
    test_start = pd.to_datetime(test["timestamp"]).min()
    if train_end > val_start:
        raise ValueError("Training timestamps must precede validation timestamps.")
    if val_end > test_start:
        raise ValueError("Validation timestamps must precede test timestamps.")


def _estimator(name: str):
    spec = REGRESSION_SPECS[name]
    if name == "RandomForestRegressor":
        return RandomForestRegressor(**spec)
    if name == "KNeighborsRegressor":
        return KNeighborsRegressor(**spec)
    if name == "MLPRegressor":
        return MLPRegressor(**spec)
    raise ValueError(f"Unknown regression model: {name}")


def _score_split(pipeline, X, y) -> dict:
    predictions = pipeline.predict(X)
    metrics = regression_metrics(y, predictions)
    metrics["predictions_finite"] = bool(np.isfinite(predictions).all())
    return metrics


def train_regression_models(train, validation, random_state: int = DEFAULT_SEED) -> dict:
    """Fit each candidate on train; score train and validation. Test is not used."""
    X_train = feature_frame(train)
    y_train = target_series(train)
    X_val = feature_frame(validation)
    y_val = target_series(validation)

    results = {}
    for name in REGRESSION_MODEL_NAMES:
        pipeline = build_model_pipeline(_estimator(name))
        pipeline.fit(X_train, y_train)
        train_metrics = _score_split(pipeline, X_train, y_train)
        val_metrics = _score_split(pipeline, X_val, y_val)
        results[name] = {
            "pipeline": pipeline,
            "hyperparameters": dict(REGRESSION_SPECS[name]),
            "train": train_metrics,
            "validation": val_metrics,
            "overfitting_flag": overfitting_flag(
                train_metrics["mae"], val_metrics["mae"]
            ),
        }
    return results


def select_best_regressor(results: dict) -> str:
    """Lowest validation MAE wins. Ties go to the first name in REGRESSION_MODEL_NAMES."""
    def key(name: str) -> tuple:
        val = results[name]["validation"]
        return (val["mae"], val["rmse"], -val["r2"])

    return min(REGRESSION_MODEL_NAMES, key=key)


def train_logistic_baseline(train, validation) -> dict:
    """Wait-bucket classifier. Separate from the regression comparison."""
    pipeline = build_model_pipeline(LogisticRegression(**LOGISTIC_SPEC))
    y_train = wait_categories(target_series(train))
    y_val = wait_categories(target_series(validation))
    pipeline.fit(feature_frame(train), y_train)
    return {
        "pipeline": pipeline,
        "hyperparameters": dict(LOGISTIC_SPEC),
        "categories": {
            "Short": f"< {15} minutes",
            "Medium": "15–30 minutes inclusive",
            "Long": "> 30 minutes",
        },
        "train": classification_metrics(y_train, pipeline.predict(feature_frame(train))),
        "validation": classification_metrics(y_val, pipeline.predict(feature_frame(validation))),
        "class_counts_train": pd.Series(y_train).value_counts().to_dict(),
        "class_counts_validation": pd.Series(y_val).value_counts().to_dict(),
    }


def evaluate_on_test(pipeline, test) -> dict:
    """Held-out score. Call only after the regression model has been chosen."""
    return _score_split(pipeline, feature_frame(test), target_series(test))


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def build_report(
    *,
    split_info: dict,
    regression_results: dict,
    selected_name: str,
    test_metrics: dict,
    logistic: dict,
    trained_at: str,
) -> dict:
    candidates = {}
    for name in REGRESSION_MODEL_NAMES:
        item = regression_results[name]
        candidates[name] = {
            "hyperparameters": item["hyperparameters"],
            "train": item["train"],
            "validation": item["validation"],
            "overfitting_flag": item["overfitting_flag"],
        }

    selection_reason = (
        f"{selected_name} had the lowest validation MAE "
        f"({regression_results[selected_name]['validation']['mae']:.3f} minutes). "
        "RMSE and R² were supporting metrics. The held-out test set was not used "
        "to choose the model."
    )
    if regression_results[selected_name]["overfitting_flag"]:
        selection_reason += (
            " The train/validation MAE gap is large, so the model is flagged "
            "for overfitting even though it still won on validation MAE."
        )

    logistic_public = {
        key: value
        for key, value in logistic.items()
        if key != "pipeline"
    }

    return {
        "dataset": {
            "name": "synthetic_queue_data.csv",
            "label": "synthetic development data",
            "disclaimer": (
                "These metrics are from simulated queue data. They do not "
                "represent real government-office performance."
            ),
            "size": split_info["train"]["rows"]
            + split_info["validation"]["rows"]
            + split_info["test"]["rows"],
            "seed": DEFAULT_SEED,
            "features": list(PREDICTION_FEATURES),
            "target": TARGET,
            "split_ratios": {
                "train": TRAIN_RATIO,
                "validation": VALIDATION_RATIO,
                "test": TEST_RATIO,
            },
            "splits": split_info,
        },
        "model_version": MODEL_VERSION,
        "trained_at": trained_at,
        "python_version": sys.version.split()[0],
        "sklearn_version": sklearn_version,
        "platform": platform.python_implementation(),
        "RandomForestRegressor": candidates["RandomForestRegressor"],
        "KNeighborsRegressor": candidates["KNeighborsRegressor"],
        "MLPRegressor": candidates["MLPRegressor"],
        "selected_model": selected_name,
        "selection_reason": selection_reason,
        "test": test_metrics,
        "LogisticRegression": logistic_public,
    }


def save_artifacts(
    *,
    regression_results: dict,
    selected_name: str,
    logistic: dict,
    report: dict,
    models_dir: Path | None = None,
    evaluation_json: Path | None = None,
    evaluation_csv: Path | None = None,
) -> dict:
    """Write joblib pipelines, metadata, registry and the evaluation report."""
    out_dir = Path(models_dir) if models_dir is not None else MODELS_DIR
    json_path = Path(evaluation_json) if evaluation_json is not None else EVALUATION_JSON
    csv_path = Path(evaluation_csv) if evaluation_csv is not None else EVALUATION_CSV
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    artifact_paths = {}
    for name, filename in ARTIFACT_FILES.items():
        path = out_dir / filename
        if name == "LogisticRegression":
            joblib.dump(logistic["pipeline"], path)
        else:
            joblib.dump(regression_results[name]["pipeline"], path)
        artifact_paths[name] = str(path)

    selected_path = out_dir / ARTIFACT_FILES[selected_name]
    metadata = {
        **report,
        "artifacts": artifact_paths,
        "selected_artifact": str(selected_path),
    }
    metadata_path = out_dir / "metadata.json"
    metadata_path.write_text(json.dumps(_json_safe(metadata), indent=2), encoding="utf-8")

    registry = {
        "model_version": MODEL_VERSION,
        "selected_model": selected_name,
        "artifact_path": to_project_relative(selected_path),
        "metadata_path": to_project_relative(metadata_path),
        "features": list(PREDICTION_FEATURES),
        "target": TARGET,
        "dataset_label": "synthetic development data",
    }
    registry_path = out_dir / "registry.json"
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")

    json_path.write_text(json.dumps(_json_safe(report), indent=2), encoding="utf-8")

    rows = []
    for name in REGRESSION_MODEL_NAMES:
        for split in ("train", "validation"):
            metrics = regression_results[name][split]
            rows.append(
                {
                    "model": name,
                    "split": split,
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "r2": metrics["r2"],
                }
            )
    rows.append(
        {
            "model": selected_name,
            "split": "test",
            "mae": report["test"]["mae"],
            "rmse": report["test"]["rmse"],
            "r2": report["test"]["r2"],
        }
    )
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    return {
        "models_dir": str(out_dir),
        "metadata_path": str(metadata_path),
        "registry_path": str(registry_path),
        "evaluation_json": str(json_path),
        "evaluation_csv": str(csv_path),
        "selected_artifact": str(selected_path),
    }


def run_training(
    dataset_path: Path | None = None,
    models_dir: Path | None = None,
    evaluation_json: Path | None = None,
    evaluation_csv: Path | None = None,
) -> dict:
    """Full Phase 6B pipeline. Test data is scored only after selection."""
    frame = load_dataset(dataset_path)
    train, validation, test = chronological_split(frame)
    _assert_chronological(train, validation, test)
    split_info = split_ranges(train, validation, test)

    regression_results = train_regression_models(train, validation)
    selected_name = select_best_regressor(regression_results)
    test_metrics = evaluate_on_test(regression_results[selected_name]["pipeline"], test)
    logistic = train_logistic_baseline(train, validation)

    trained_at = datetime.now(timezone.utc).isoformat()
    report = build_report(
        split_info=split_info,
        regression_results=regression_results,
        selected_name=selected_name,
        test_metrics=test_metrics,
        logistic=logistic,
        trained_at=trained_at,
    )
    paths = save_artifacts(
        regression_results=regression_results,
        selected_name=selected_name,
        logistic=logistic,
        report=report,
        models_dir=models_dir,
        evaluation_json=evaluation_json,
        evaluation_csv=evaluation_csv,
    )
    return {
        "report": report,
        "paths": paths,
        "regression_results": regression_results,
        "selected_name": selected_name,
        "logistic": logistic,
        "splits": {"train": train, "validation": validation, "test": test},
    }


def _print_summary(result: dict) -> None:
    report = result["report"]
    print("Queue wait-time training (synthetic development data only)")
    print(f"model version: {report['model_version']}")
    splits = report["dataset"]["splits"]
    for name in ("train", "validation", "test"):
        part = splits[name]
        print(f"{name}: {part['rows']} rows  {part['start']} -> {part['end']}")
    print()
    print("Model | Train MAE | Val MAE | Val RMSE | Val R2 | overfit?")
    for name in REGRESSION_MODEL_NAMES:
        item = report[name]
        flag = "yes" if item["overfitting_flag"] else "no"
        print(
            f"{name}:  "
            f"{item['train']['mae']:.3f}  "
            f"{item['validation']['mae']:.3f}  "
            f"{item['validation']['rmse']:.3f}  "
            f"{item['validation']['r2']:.3f}  "
            f"{flag}"
        )
    print()
    print(f"Selected model: {report['selected_model']}")
    print(f"Reason: {report['selection_reason']}")
    test = report["test"]
    print(
        f"Held-out test: MAE={test['mae']:.3f}  RMSE={test['rmse']:.3f}  "
        f"R²={test['r2']:.3f}  negative_preds={test['negative_prediction_count']}"
    )
    logistic = report["LogisticRegression"]["validation"]
    print(
        "Logistic Regression (validation): "
        f"acc={logistic['accuracy']:.3f}  F1_macro={logistic['f1_macro']:.3f}"
    )
    print(f"artifacts: {result['paths']['models_dir']}")
    print(report["dataset"]["disclaimer"])


def main() -> None:
    result = run_training()
    _print_summary(result)


if __name__ == "__main__":
    main()
