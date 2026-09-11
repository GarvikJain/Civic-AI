"""Tests for queue wait-time model training (Phase 6B).

Training uses small generated frames so the suite stays off the network and
does not depend on the FastAPI app. The real 15,000-row CSV is used only for
split-size and leakage checks.
"""

from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ai_modules.queue_prediction.constants import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    PREDICTION_FEATURES,
    REGRESSION_MODEL_NAMES,
    TARGET,
)
from ai_modules.queue_prediction.dataset_generator import (
    DEFAULT_OUTPUT_PATH,
    generate_dataset,
)
from ai_modules.queue_prediction.evaluation import (
    classification_metrics,
    regression_metrics,
    wait_categories,
    wait_category,
)
from ai_modules.queue_prediction.model_registry import (
    load_registry,
    load_selected_model,
    resolve_artifact_path,
    selected_feature_schema,
    to_project_relative,
)
from ai_modules.queue_prediction.model_training import (
    chronological_split,
    evaluate_on_test,
    load_dataset,
    run_training,
    select_best_regressor,
    train_logistic_baseline,
    train_regression_models,
)
from ai_modules.queue_prediction.preprocessing import (
    build_preprocessor,
    feature_frame,
    target_series,
)


@pytest.fixture
def small_frame() -> pd.DataFrame:
    return generate_dataset(n_records=600, seed=42)


@pytest.fixture
def splits(small_frame):
    return chronological_split(small_frame)


def test_dataset_loading_from_csv():
    frame = load_dataset(DEFAULT_OUTPUT_PATH)
    assert len(frame) == 15_000
    assert TARGET in frame.columns
    for name in PREDICTION_FEATURES:
        assert name in frame.columns


def test_chronological_sorting_and_split_sizes():
    frame = load_dataset(DEFAULT_OUTPUT_PATH)
    train, validation, test = chronological_split(frame)
    assert len(train) == 10_500
    assert len(validation) == 2_250
    assert len(test) == 2_250
    assert len(train) + len(validation) + len(test) == 15_000


def test_splits_do_not_overlap(splits):
    train, validation, test = splits
    ids = [set(part["appointment_id"]) for part in splits]
    assert ids[0].isdisjoint(ids[1])
    assert ids[0].isdisjoint(ids[2])
    assert ids[1].isdisjoint(ids[2])


def test_splits_are_in_timestamp_order():
    frame = load_dataset(DEFAULT_OUTPUT_PATH)
    train, validation, test = chronological_split(frame)
    assert train["timestamp"].is_monotonic_increasing
    assert validation["timestamp"].is_monotonic_increasing
    assert test["timestamp"].is_monotonic_increasing
    assert train["timestamp"].max() <= validation["timestamp"].min()
    assert validation["timestamp"].max() <= test["timestamp"].min()


def test_feature_target_separation(small_frame):
    X = feature_frame(small_frame)
    y = target_series(small_frame)
    assert list(X.columns) == list(PREDICTION_FEATURES)
    assert TARGET not in X.columns
    assert "appointment_id" not in X.columns
    assert "timestamp" not in X.columns
    assert len(y) == len(X)
    assert y.name == TARGET


def test_preprocessor_is_fitted_only_on_training_data(splits):
    train, validation, _test = splits
    X_train = feature_frame(train)
    X_val = feature_frame(validation)
    preprocessor = build_preprocessor()
    preprocessor.fit(X_train)

    scaler: StandardScaler = preprocessor.named_transformers_["numeric"]
    np.testing.assert_allclose(
        scaler.mean_, X_train[list(NUMERIC_FEATURES)].mean().to_numpy(), rtol=1e-6
    )

    encoder: OneHotEncoder = preprocessor.named_transformers_["categorical"]
    train_days = set(X_train["day_of_week"].unique())
    encoded_days = set(encoder.categories_[list(CATEGORICAL_FEATURES).index("day_of_week")])
    assert encoded_days == train_days

    transformed_val = preprocessor.transform(X_val)
    assert transformed_val.shape[0] == len(X_val)
    assert np.isfinite(transformed_val).all()


def test_categorical_encoding_and_numeric_scaling(splits):
    train, *_ = splits
    preprocessor = build_preprocessor()
    Xt = preprocessor.fit_transform(feature_frame(train))
    assert isinstance(preprocessor, ColumnTransformer)
    # Six services + five weekdays + three numeric columns, if all appear.
    assert Xt.shape[1] >= 3 + 2
    numeric = Xt[:, -3:]
    assert abs(numeric[:, 0].mean()) < 1e-6
    assert abs(numeric[:, 0].std(ddof=0) - 1.0) < 1e-6


def test_all_three_regressors_train_and_predict(splits):
    train, validation, _test = splits
    results = train_regression_models(train, validation)
    assert set(results) == set(REGRESSION_MODEL_NAMES)
    n_val = len(validation)
    X_val = feature_frame(validation)
    for name, item in results.items():
        preds = item["pipeline"].predict(X_val)
        assert preds.shape == (n_val,)
        assert np.isfinite(preds).all()
        assert item["train"]["mae"] >= 0
        assert item["validation"]["mae"] >= 0


def test_metrics_match_sklearn_definitions():
    y_true = np.array([10.0, 20.0, 30.0])
    y_pred = np.array([12.0, 18.0, 33.0])
    metrics = regression_metrics(y_true, y_pred)
    assert metrics["mae"] == pytest.approx(7 / 3)
    assert metrics["rmse"] == pytest.approx(np.sqrt((4 + 4 + 9) / 3))
    assert "r2" in metrics


def test_model_selection_uses_validation_mae_not_test(splits):
    train, validation, test = splits
    results = train_regression_models(train, validation)
    selected = select_best_regressor(results)
    best_val = min(results[name]["validation"]["mae"] for name in REGRESSION_MODEL_NAMES)
    assert results[selected]["validation"]["mae"] == best_val

    test_metrics = evaluate_on_test(results[selected]["pipeline"], test)
    # Selection is unchanged even if another model would do better on test.
    assert select_best_regressor(results) == selected
    assert test_metrics["n"] == len(test)


def test_wait_categories_and_logistic_baseline(splits):
    assert wait_category(10) == "Short"
    assert wait_category(15) == "Medium"
    assert wait_category(30) == "Medium"
    assert wait_category(31) == "Long"

    train, validation, _test = splits
    logistic = train_logistic_baseline(train, validation)
    preds = logistic["pipeline"].predict(feature_frame(validation))
    assert set(preds).issubset({"Short", "Medium", "Long"})
    metrics = classification_metrics(
        wait_categories(target_series(validation)), preds
    )
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert metrics["confusion_matrix"]
    assert logistic["validation"]["n"] == len(validation)


def test_full_pipeline_writes_reloadable_artifacts(small_frame, tmp_path: Path):
    csv_path = tmp_path / "queue.csv"
    small_frame.to_csv(csv_path, index=False)
    models_dir = tmp_path / "models"
    result = run_training(
        dataset_path=csv_path,
        models_dir=models_dir,
        evaluation_json=tmp_path / "model_evaluation.json",
        evaluation_csv=tmp_path / "model_evaluation.csv",
    )

    report = result["report"]
    assert report["selected_model"] in REGRESSION_MODEL_NAMES
    assert "mae" in report["test"]
    assert (tmp_path / "model_evaluation.json").is_file()
    assert (tmp_path / "model_evaluation.csv").is_file()
    assert (models_dir / "metadata.json").is_file()
    assert (models_dir / "registry.json").is_file()
    for filename in (
        "random_forest.joblib",
        "knn.joblib",
        "mlp.joblib",
        "logistic_regression.joblib",
    ):
        assert (models_dir / filename).is_file()

    registry = load_registry(models_dir / "registry.json")
    assert registry["selected_model"] == report["selected_model"]
    assert not Path(registry["artifact_path"]).is_absolute()
    assert ":" not in registry["artifact_path"]
    assert "\\" not in registry["artifact_path"]
    assert selected_feature_schema(models_dir / "registry.json") == list(
        PREDICTION_FEATURES
    )

    loaded = load_selected_model(models_dir / "registry.json")
    sample = feature_frame(result["splits"]["validation"]).iloc[:8]
    original = result["regression_results"][report["selected_model"]]["pipeline"].predict(
        sample
    )
    reloaded = loaded.predict(sample)
    np.testing.assert_allclose(original, reloaded, rtol=1e-7, atol=1e-7)

    dumped = joblib.load(models_dir / "random_forest.joblib")
    assert "preprocess" in dumped.named_steps


def test_training_is_reproducible(small_frame, tmp_path: Path):
    csv_path = tmp_path / "queue.csv"
    small_frame.to_csv(csv_path, index=False)
    first = run_training(
        dataset_path=csv_path,
        models_dir=tmp_path / "a",
        evaluation_json=tmp_path / "a.json",
        evaluation_csv=tmp_path / "a.csv",
    )
    second = run_training(
        dataset_path=csv_path,
        models_dir=tmp_path / "b",
        evaluation_json=tmp_path / "b.json",
        evaluation_csv=tmp_path / "b.csv",
    )
    assert first["selected_name"] == second["selected_name"]
    for name in REGRESSION_MODEL_NAMES:
        assert first["report"][name]["validation"]["mae"] == pytest.approx(
            second["report"][name]["validation"]["mae"], rel=1e-6, abs=1e-6
        )


def test_no_target_leakage_in_training_features(small_frame):
    train, validation, test = chronological_split(small_frame)
    for part in (train, validation, test):
        X = feature_frame(part)
        assert TARGET not in X.columns
        assert "predicted_wait_time" not in X.columns


def test_registry_paths_are_project_relative_posix():
    registry = load_registry()
    assert registry["model_version"] == "queue-v1"
    assert registry["selected_model"] == "MLPRegressor"
    assert registry["artifact_path"] == "data/queue_prediction/models/mlp.joblib"
    assert registry["metadata_path"] == "data/queue_prediction/models/metadata.json"
    assert ":" not in registry["artifact_path"]
    assert "\\" not in registry["artifact_path"]
    assert not Path(registry["artifact_path"]).is_absolute()


def test_load_selected_model_resolves_from_relocated_project_root(tmp_path: Path):
    """A copied project tree still loads using the same relative registry path."""
    first_root = tmp_path / "civic-ai-a"
    second_root = tmp_path / "civic-ai-b"
    relative = "data/queue_prediction/models/mlp.joblib"
    payload_a = {"site": "a"}
    payload_b = {"site": "b"}

    for root, payload in ((first_root, payload_a), (second_root, payload_b)):
        models_dir = root / "data" / "queue_prediction" / "models"
        models_dir.mkdir(parents=True)
        joblib.dump(payload, models_dir / "mlp.joblib")
        (models_dir / "registry.json").write_text(
            json.dumps(
                {
                    "model_version": "queue-v1",
                    "selected_model": "MLPRegressor",
                    "artifact_path": relative,
                    "metadata_path": "data/queue_prediction/models/metadata.json",
                    "features": list(PREDICTION_FEATURES),
                    "target": TARGET,
                    "dataset_label": "synthetic development data",
                }
            ),
            encoding="utf-8",
        )

    loaded_a = load_selected_model(
        first_root / "data" / "queue_prediction" / "models" / "registry.json",
        project_root=first_root,
    )
    loaded_b = load_selected_model(
        second_root / "data" / "queue_prediction" / "models" / "registry.json",
        project_root=second_root,
    )
    assert loaded_a == payload_a
    assert loaded_b == payload_b
    assert resolve_artifact_path(relative, project_root=first_root) == (
        first_root / relative
    ).resolve()
    assert resolve_artifact_path(relative, project_root=second_root) == (
        second_root / relative
    ).resolve()
    stored = to_project_relative(first_root / relative, project_root=first_root)
    assert stored == relative
    assert ":" not in stored


def test_negative_predictions_are_counted_not_hidden(splits):
    train, validation, test = splits
    results = train_regression_models(train, validation)
    selected = select_best_regressor(results)
    metrics = evaluate_on_test(results[selected]["pipeline"], test)
    assert "negative_prediction_count" in metrics
    assert metrics["negative_prediction_count"] >= 0
