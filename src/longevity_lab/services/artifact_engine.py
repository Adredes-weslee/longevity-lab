"""Artifact-backed scenario engine.

This engine is the end-state replacement for the demo heuristic engine. It
loads trained per-condition pipelines and returns condition probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.api.schemas import FeatureProfile
from longevity_lab.artifacts.store import ArtifactBundle, ArtifactStore
from longevity_lab.domain.catalog import CONDITIONS
from longevity_lab.services.engine_types import ConditionScore, ScenarioEngine


@dataclass(frozen=True, slots=True)
class LoadedConditionModel:
    """A resolved condition model pipeline."""

    condition_id: str
    pipeline: object
    explanation_pipeline: object | None = None


class ArtifactScenarioEngine(ScenarioEngine):
    """Scenario engine backed by persisted model artifacts."""

    def __init__(self, store: ArtifactStore, bundle_id: str | None = None) -> None:
        """Load the requested (or latest) bundle and its per-condition pipelines."""
        self._bundle = store.resolve(bundle_id=bundle_id)
        self._by_condition = {item.condition_id: item for item in CONDITIONS}
        unknown_conditions = [
            item.condition_id
            for item in self._bundle.manifest.conditions
            if item.condition_id not in self._by_condition
        ]
        if unknown_conditions:
            raise ValueError(
                "Artifact manifest contains unknown condition_id values: "
                f"{sorted(set(unknown_conditions))}. "
                "Update src/longevity_lab/domain/catalog.py or fix the artifact bundle."
            )
        self._models = self._load_models(self._bundle)

    def evaluate(self, profile: FeatureProfile) -> list[ConditionScore]:
        """Evaluate a profile by calling each loaded per-condition pipeline."""
        frame = pd.DataFrame([profile.model_dump()])
        results: list[ConditionScore] = []
        for condition in self._bundle.manifest.conditions:
            model = self._models[condition.condition_id]
            pipeline = model.pipeline
            if not hasattr(pipeline, "predict_proba"):
                raise TypeError(
                    f"Pipeline for {condition.condition_id} does not expose predict_proba()."
                )
            proba = pipeline.predict_proba(frame)
            probability = self._positive_class_probability(
                pipeline,
                proba,
                condition_id=condition.condition_id,
            )
            meta = self._by_condition[condition.condition_id]
            key_drivers = self._derive_key_drivers(
                loaded_model=model,
                frame=frame,
                explanation_method=condition.explanation_method,
            )
            results.append(
                ConditionScore(
                    condition_id=condition.condition_id,
                    label=meta.label,
                    organ_id=meta.organ_id,
                    probability=probability,
                    key_drivers=key_drivers,
                )
            )
        return results

    @staticmethod
    def _load_models(bundle: ArtifactBundle) -> dict[str, LoadedConditionModel]:
        models: dict[str, LoadedConditionModel] = {}
        for condition in bundle.manifest.conditions:
            if condition.condition_id in models:
                raise ValueError(
                    "Artifact manifest contains duplicate condition_id entries: "
                    f"{condition.condition_id}"
                )

            pipeline_path = ArtifactScenarioEngine._safe_bundle_path(
                bundle.path,
                condition.pipeline_path,
                label=f"pipeline_path for {condition.condition_id}",
            )
            if not pipeline_path.exists():
                raise FileNotFoundError(
                    f"Missing pipeline artifact for {condition.condition_id}: {pipeline_path}"
                )
            explanation_pipeline: object | None = None
            if condition.explanation_path:
                explanation_path = ArtifactScenarioEngine._safe_bundle_path(
                    bundle.path,
                    condition.explanation_path,
                    label=f"explanation_path for {condition.condition_id}",
                )
                if not explanation_path.exists():
                    raise FileNotFoundError(
                        "Missing explanation artifact for "
                        f"{condition.condition_id}: {explanation_path}"
                    )
                explanation_pipeline = joblib.load(explanation_path)
            models[condition.condition_id] = LoadedConditionModel(
                condition_id=condition.condition_id,
                pipeline=joblib.load(pipeline_path),
                explanation_pipeline=explanation_pipeline,
            )
        return models

    @staticmethod
    def _derive_key_drivers(
        *,
        loaded_model: LoadedConditionModel,
        frame: pd.DataFrame,
        explanation_method: str,
    ) -> list[str]:
        """Return model-derived key drivers when an explanation path is available."""
        if explanation_method != "tree_path":
            return []
        pipeline = loaded_model.explanation_pipeline
        if pipeline is None or not hasattr(pipeline, "named_steps"):
            return []

        named_steps = pipeline.named_steps  # type: ignore[attr-defined]
        preprocess = named_steps.get("preprocess")
        model = named_steps.get("model")
        if preprocess is None or model is None:
            return []
        if (
            not hasattr(model, "decision_path")
            or not hasattr(model, "tree_")
            or not hasattr(model, "apply")
        ):
            return []

        transformed = preprocess.transform(frame)
        if isinstance(transformed, pd.DataFrame):
            feature_names = list(transformed.columns)
            decision_input = transformed
        else:
            decision_input = np.asarray(transformed)
            if hasattr(preprocess, "get_feature_names_out"):
                feature_names = list(preprocess.get_feature_names_out())
            elif hasattr(model, "feature_names_in_"):
                feature_names = list(model.feature_names_in_)  # type: ignore[attr-defined]
            else:
                feature_names = [f"feature_{idx}" for idx in range(decision_input.shape[1])]

        node_indicator = model.decision_path(decision_input)
        leaf_id = int(model.apply(decision_input)[0])
        node_indices = node_indicator.indices[node_indicator.indptr[0] : node_indicator.indptr[1]]
        labels: list[str] = []
        for node_id in node_indices:
            if int(node_id) == leaf_id:
                continue
            feature_idx = int(model.tree_.feature[node_id])
            if feature_idx < 0 or feature_idx >= len(feature_names):
                continue
            label = ArtifactScenarioEngine._feature_label(feature_names[feature_idx])
            if label not in labels:
                labels.append(label)
        return labels[:3]

    @staticmethod
    def _feature_label(feature_name: str) -> str:
        """Map a feature column to a UI-friendly label."""
        labels = {
            "age": "Age",
            "bmi": "BMI",
            "smoker": "Smoking",
            "alcohol_servings_per_week": "Alcohol servings / week",
            "exercise_minutes_per_week": "Exercise minutes / week",
            "annual_aqi": "Annual AQI",
        }
        return labels.get(feature_name, feature_name.replace("_", " ").title())

    @staticmethod
    def _safe_bundle_path(bundle_dir: Path, relative_path: str, *, label: str) -> Path:
        """Resolve a bundle-local relative path and reject path traversal."""
        rel = Path(relative_path)
        if rel.is_absolute():
            raise ValueError(f"Unsafe {label}: expected relative path, got {relative_path!r}")

        bundle_resolved = bundle_dir.resolve()
        target = (bundle_dir / rel).resolve()
        try:
            target.relative_to(bundle_resolved)
        except ValueError as exc:
            raise ValueError(f"Unsafe {label}: {relative_path!r}") from exc
        return target

    @staticmethod
    def _positive_class_probability(pipeline: object, proba: object, *, condition_id: str) -> float:
        """Return the predicted probability for the positive class (label 1)."""
        array = np.asarray(proba)
        if array.ndim != 2 or array.shape[0] != 1:
            raise ValueError(
                f"predict_proba() for {condition_id} returned unexpected shape {array.shape}."
            )

        if not hasattr(pipeline, "classes_"):
            raise TypeError(
                f"Pipeline for {condition_id} must expose classes_ so probabilities can be mapped "
                "to label values."
            )
        classes = np.asarray(pipeline.classes_)  # type: ignore[attr-defined]
        if classes.ndim != 1:
            raise ValueError(f"Pipeline classes_ for {condition_id} is not 1D: {classes!r}")

        if set(classes.tolist()) != {0, 1}:
            raise ValueError(
                f"Pipeline classes_ for {condition_id} must be {{0, 1}} (got {classes.tolist()})."
            )
        matches = np.where(classes == 1)[0]
        if len(matches) != 1:  # pragma: no cover
            raise ValueError(
                f"Could not locate positive class label 1 for {condition_id} in {classes.tolist()}."
            )
        idx = int(matches[0])
        probability = float(array[0][idx])
        if not np.isfinite(probability) or probability < 0.0 or probability > 1.0:
            raise ValueError(
                f"predict_proba() returned invalid probability for {condition_id}: {probability}."
            )
        return probability
