"""Model-aligned explanation helpers for served artifact predictions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, cast

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

ExplanationDirection = Literal["increases", "decreases", "neutral"]
ExplanationMethod = Literal["demo", "tree_path", "shap"]

FEATURE_LABELS: dict[str, str] = {
    "age": "Age",
    "bmi": "BMI",
    "smoker": "Smoking",
    "alcohol_servings_per_week": "Alcohol servings / week",
    "exercise_minutes_per_week": "Exercise minutes / week",
    "annual_aqi": "Annual AQI",
    "pm25_mean": "PM2.5 annual mean",
    "ozone_mean": "Ozone annual mean",
    "alcohol": "Alcohol use",
    "exercise": "Low exercise",
    "aqi": "Air quality",
    "pm25": "PM2.5 concentration",
    "ozone": "Ozone concentration",
    "sex": "Sex",
    "race_ethnicity": "Race/ethnicity",
    "has_healthcare_coverage": "Healthcare coverage",
    "has_personal_doctor": "Personal doctor",
    "cost_barrier_to_care": "Could not see doctor due to cost",
    "last_checkup_within_year": "Checkup in past year",
    "sleep_hours_per_night": "Sleep hours / night",
    "physical_health_days": "Poor physical health days",
    "mental_health_days": "Poor mental health days",
}


@dataclass(frozen=True, slots=True)
class ExplanationRecord:
    """One typed, model-derived explanation item for a condition score."""

    feature: str
    display_name: str
    direction: ExplanationDirection
    magnitude: float
    method: ExplanationMethod
    caveat: str


class ShapTreeExplainer(Protocol):
    """Small protocol for the optional SHAP TreeExplainer."""

    def shap_values(self, transformed: pd.DataFrame | np.ndarray) -> object:
        """Return SHAP values for the transformed row."""


class ShapExplainerFactory(Protocol):
    """Callable factory for optional SHAP explainers."""

    def __call__(self, model: object) -> ShapTreeExplainer:
        """Build a tree explainer for a fitted model."""


class ShapModule(Protocol):
    """Subset of the optional SHAP module used by serving."""

    TreeExplainer: ShapExplainerFactory


class SupportsTreePathModel(Protocol):
    """Decision-tree attributes needed for rule-path explanations."""

    tree_: object
    classes_: object


def demo_explanation_records(
    contributions: dict[str, float],
    *,
    limit: int = 3,
) -> list[ExplanationRecord]:
    """Convert demo-engine contribution scores into typed explanation records."""
    rows: list[ExplanationRecord] = []
    for feature, magnitude in sorted(contributions.items(), key=lambda item: item[1], reverse=True):
        if magnitude <= 0.0:
            continue
        rows.append(
            ExplanationRecord(
                feature=feature,
                display_name=feature_label(feature),
                direction="increases",
                magnitude=float(magnitude),
                method="demo",
                caveat="Demo-mode heuristic contribution; not a trained-model explanation.",
            )
        )
    return rows[:limit]


def build_explanation_records(
    *,
    method: str,
    explanation_artifact: object | None,
    frame: pd.DataFrame,
    limit: int = 3,
) -> list[ExplanationRecord]:
    """Build explanation records using the method declared by the artifact manifest."""
    if explanation_artifact is None:
        return []
    if method == "tree_path":
        return _tree_path_explanations(explanation_artifact, frame=frame, limit=limit)
    if method == "shap":
        return _shap_explanations(explanation_artifact, frame=frame, limit=limit)
    return []


def feature_label(feature_name: str) -> str:
    """Map a model feature name to user-facing copy."""
    return FEATURE_LABELS.get(feature_name, feature_name.replace("_", " ").title())


def _tree_path_explanations(
    explanation_artifact: object,
    *,
    frame: pd.DataFrame,
    limit: int,
) -> list[ExplanationRecord]:
    if not hasattr(explanation_artifact, "named_steps"):
        return []
    named_steps = explanation_artifact.named_steps  # type: ignore[attr-defined]
    preprocess = named_steps.get("preprocess")
    model = named_steps.get("model")
    if preprocess is None or model is None:
        return []
    if not all(hasattr(model, name) for name in ("decision_path", "tree_", "apply")):
        return []

    transformed = preprocess.transform(frame)
    decision_input = (
        transformed if isinstance(transformed, pd.DataFrame) else np.asarray(transformed)
    )
    feature_names = _transformed_feature_names(preprocess, model, decision_input)
    values = _first_row_values(decision_input)
    node_indicator = model.decision_path(decision_input)
    leaf_id = int(model.apply(decision_input)[0])
    node_indices = node_indicator.indices[node_indicator.indptr[0] : node_indicator.indptr[1]]

    records: list[ExplanationRecord] = []
    seen: set[str] = set()
    for node_id in node_indices:
        if int(node_id) == leaf_id:
            continue
        feature_idx = int(model.tree_.feature[node_id])
        if feature_idx < 0 or feature_idx >= len(feature_names):
            continue
        feature_name = str(feature_names[feature_idx])
        if feature_name in seen:
            continue
        threshold = float(model.tree_.threshold[node_id])
        value = float(values[feature_idx])
        direction = _tree_branch_risk_direction(
            model=model,
            node_id=int(node_id),
            went_right=value > threshold,
        )
        records.append(
            ExplanationRecord(
                feature=feature_name,
                display_name=feature_label(feature_name),
                direction=direction,
                magnitude=abs(value - threshold),
                method="tree_path",
                caveat=(
                    "Decision-tree rule-path split; direction compares branch positive-class risk, "
                    "not a causal effect."
                ),
            )
        )
        seen.add(feature_name)
        if len(records) >= limit:
            break
    return records


def _tree_branch_risk_direction(
    *,
    model: object,
    node_id: int,
    went_right: bool,
) -> ExplanationDirection:
    tree_model = cast(SupportsTreePathModel, model)
    tree = tree_model.tree_
    left_child = int(tree.children_left[node_id])  # type: ignore[attr-defined]
    right_child = int(tree.children_right[node_id])  # type: ignore[attr-defined]
    chosen_child = right_child if went_right else left_child
    other_child = left_child if went_right else right_child
    chosen_risk = _node_positive_class_rate(tree_model, chosen_child)
    other_risk = _node_positive_class_rate(tree_model, other_child)
    if chosen_risk > other_risk:
        return "increases"
    if chosen_risk < other_risk:
        return "decreases"
    return "neutral"


def _node_positive_class_rate(model: SupportsTreePathModel, node_id: int) -> float:
    tree = model.tree_
    raw_values = tree.value[node_id]  # type: ignore[attr-defined]
    values = np.asarray(raw_values, dtype=np.float64).reshape(-1)
    classes = np.asarray(model.classes_)
    matches = np.where(classes == 1)[0]
    class_idx = int(matches[0]) if len(matches) == 1 and len(values) > int(matches[0]) else -1
    total = float(values.sum())
    if total <= 0.0:
        return 0.0
    return float(values[class_idx] / total)


def _shap_explanations(
    explanation_artifact: object,
    *,
    frame: pd.DataFrame,
    limit: int,
) -> list[ExplanationRecord]:
    shap_module = _import_shap_module()
    transformed, model, feature_names = _model_and_transformed_frame(explanation_artifact, frame)
    if model is None:
        return []
    explainer = shap_module.TreeExplainer(model)
    raw_values = explainer.shap_values(transformed)
    values = _first_shap_row(raw_values)
    ranked = sorted(
        zip(feature_names, values, strict=True),
        key=lambda item: abs(float(item[1])),
        reverse=True,
    )
    records: list[ExplanationRecord] = []
    for feature_name, value in ranked[:limit]:
        magnitude = abs(float(value))
        records.append(
            ExplanationRecord(
                feature=str(feature_name),
                display_name=feature_label(str(feature_name)),
                direction=_direction_from_signed_value(float(value)),
                magnitude=magnitude,
                method="shap",
                caveat=(
                    "TreeSHAP attribution from the served artifact; correlated features can "
                    "share or shift attribution and values are not causal effects."
                ),
            )
        )
    return records


def _import_shap_module() -> ShapModule:
    try:
        import shap  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "SHAP explanations require the optional `shap` package in the serving environment."
        ) from exc
    return cast(ShapModule, shap)


def _model_and_transformed_frame(
    explanation_artifact: object,
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame | np.ndarray, object | None, list[str]]:
    if hasattr(explanation_artifact, "named_steps"):
        named_steps = explanation_artifact.named_steps  # type: ignore[attr-defined]
        preprocess = named_steps.get("preprocess")
        model = named_steps.get("model")
        if preprocess is None or model is None:
            return frame, None, list(frame.columns)
        transformed = preprocess.transform(frame)
        return transformed, model, _transformed_feature_names(preprocess, model, transformed)
    return frame, explanation_artifact, list(frame.columns)


def _transformed_feature_names(
    preprocess: object,
    model: object,
    transformed: pd.DataFrame | np.ndarray,
) -> list[str]:
    if isinstance(transformed, pd.DataFrame):
        return [str(column) for column in transformed.columns]
    if hasattr(preprocess, "get_feature_names_out"):
        return [str(item) for item in preprocess.get_feature_names_out()]
    if hasattr(model, "feature_names_in_"):
        return [str(item) for item in model.feature_names_in_]  # type: ignore[attr-defined]
    return [f"feature_{idx}" for idx in range(np.asarray(transformed).shape[1])]


def _first_row_values(transformed: pd.DataFrame | np.ndarray) -> np.ndarray:
    if isinstance(transformed, pd.DataFrame):
        return cast(np.ndarray, transformed.iloc[0].to_numpy(dtype=float))
    return cast(np.ndarray, np.asarray(transformed, dtype=float)[0])


def _first_shap_row(raw_values: object) -> np.ndarray:
    values = raw_values
    if isinstance(raw_values, list):
        values = raw_values[1] if len(raw_values) > 1 else raw_values[0]
    array = np.asarray(values, dtype=float)
    if array.ndim == 3:
        array = array[:, :, 1]
    if array.ndim != 2 or array.shape[0] < 1:
        raise ValueError(f"Unexpected SHAP values shape: {array.shape}.")
    return cast(np.ndarray, array[0])


def _direction_from_signed_value(value: float) -> ExplanationDirection:
    if value > 0:
        return "increases"
    if value < 0:
        return "decreases"
    return "neutral"
