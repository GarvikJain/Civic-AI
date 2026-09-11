"""How a future prediction service finds the selected wait-time model.

This module only loads artifacts written by model_training.py. It does not
train anything and it is not an HTTP API.

Persisted paths in registry.json are project-relative POSIX paths, for example:

    data/queue_prediction/models/mlp.joblib

They are resolved from the CivicAI project root at load time. The root is
derived from this package's location, never from a hard-coded drive letter.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib

from ai_modules.queue_prediction.constants import MODEL_VERSION, PREDICTION_FEATURES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = (
    PROJECT_ROOT / "data" / "queue_prediction" / "models" / "registry.json"
)

_MODELS_RELATIVE_PREFIX = "data/queue_prediction/models/"


class ModelNotTrainedError(FileNotFoundError):
    """No selected wait-time model has been saved yet."""


def to_project_relative(path: Path | str, project_root: Path | None = None) -> str:
    """Store artifact locations as POSIX paths relative to the project root."""
    resolved = Path(path).resolve()
    root = Path(project_root).resolve() if project_root is not None else PROJECT_ROOT.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.name


def resolve_artifact_path(
    stored: str,
    *,
    project_root: Path | None = None,
    registry_path: Path | None = None,
) -> Path:
    """Turn a registry path into an absolute filesystem path.

    Relative entries are joined to the project root. Absolute entries from an
    older registry are re-rooted using the ``data/queue_prediction/models/``
    suffix when present, so a copied project does not keep a stale drive letter.
    """
    root = Path(project_root).resolve() if project_root is not None else PROJECT_ROOT.resolve()
    posix = Path(str(stored)).as_posix()
    if Path(stored).is_absolute() or (len(posix) >= 2 and posix[1] == ":"):
        idx = posix.lower().find(_MODELS_RELATIVE_PREFIX)
        if idx >= 0:
            return (root / posix[idx:]).resolve()
        return Path(stored)

    joined = (root / posix).resolve()
    if joined.is_file():
        return joined
    if registry_path is not None:
        beside = Path(registry_path).resolve().parent / Path(posix).name
        if beside.is_file():
            return beside
    return joined


def load_registry(path: Path | None = None) -> dict:
    """Read registry.json written by training."""
    registry_path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
    if not registry_path.is_file():
        raise ModelNotTrainedError(
            f"No model registry at {registry_path}. "
            "Run: python -m ai_modules.queue_prediction.model_training"
        )
    return json.loads(registry_path.read_text(encoding="utf-8"))


def load_selected_model(
    registry_path: Path | None = None,
    project_root: Path | None = None,
):
    """The sklearn Pipeline (preprocess + estimator) chosen on validation MAE."""
    registry_file = Path(registry_path) if registry_path is not None else DEFAULT_REGISTRY_PATH
    registry = load_registry(registry_file)
    artifact = resolve_artifact_path(
        registry["artifact_path"],
        project_root=project_root,
        registry_path=registry_file,
    )
    if not artifact.is_file():
        raise ModelNotTrainedError(f"Selected artifact is missing: {artifact}")
    return joblib.load(artifact)


def selected_feature_schema(registry_path: Path | None = None) -> list[str]:
    """Feature names the persisted pipeline expects, in order."""
    registry = load_registry(registry_path)
    return list(registry.get("features") or PREDICTION_FEATURES)


def model_version(registry_path: Path | None = None) -> str:
    registry = load_registry(registry_path)
    return str(registry.get("model_version") or MODEL_VERSION)
