"""Artifact-backed scenario engine.

This engine is the end-state replacement for the demo heuristic engine. It
loads trained per-condition pipelines and returns condition probabilities.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.api.schemas import FeatureProfile
from longevity_lab.artifacts.store import ArtifactBundle, ArtifactStore
from longevity_lab.domain.catalog import CONDITIONS
from longevity_lab.services.engine_types import ConditionScore, ScenarioEngine
from longevity_lab.services.explanations import build_explanation_records
from longevity_lab.services.uncertainty import build_uncertainty_summary


@dataclass(frozen=True, slots=True)
class LoadedConditionModel:
    """A resolved condition model pipeline."""

    condition_id: str
    pipeline: object
    explanation_pipeline: object | None = None
    uncertainty_payload: dict[str, object] | None = None


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
        frame = self._profile_frame(profile)
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
            explanations = build_explanation_records(
                frame=frame,
                method=condition.explanation_method,
                explanation_artifact=model.explanation_pipeline,
            )
            key_drivers = [record.display_name for record in explanations]
            uncertainty = build_uncertainty_summary(
                probability=probability,
                method=condition.uncertainty_method,
                payload=model.uncertainty_payload,
            )
            results.append(
                ConditionScore(
                    condition_id=condition.condition_id,
                    label=meta.label,
                    organ_id=meta.organ_id,
                    probability=probability,
                    key_drivers=key_drivers,
                    explanations=explanations,
                    uncertainty=uncertainty,
                )
            )
        return results

    def _profile_frame(self, profile: FeatureProfile) -> pd.DataFrame:
        """Return a serving frame aligned to the artifact manifest feature contract."""
        values: dict[str, object] = {
            "sex": "unknown",
            "race_ethnicity": "unknown",
            "has_healthcare_coverage": None,
            "has_personal_doctor": None,
            "cost_barrier_to_care": None,
            "last_checkup_within_year": None,
            "sleep_hours_per_night": None,
            "physical_health_days": None,
            "mental_health_days": None,
        }
        values.update(profile.model_dump())
        for feature_name in self._bundle.manifest.features:
            values.setdefault(feature_name, None)
        return pd.DataFrame([{name: values[name] for name in self._bundle.manifest.features}])

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
                uncertainty_payload=ArtifactScenarioEngine._load_uncertainty_payload(
                    bundle=bundle,
                    condition_id=condition.condition_id,
                    uncertainty_method=condition.uncertainty_method,
                    uncertainty_path=condition.uncertainty_path,
                ),
            )
        return models

    @staticmethod
    def _load_uncertainty_payload(
        *,
        bundle: ArtifactBundle,
        condition_id: str,
        uncertainty_method: str,
        uncertainty_path: str | None,
    ) -> dict[str, object] | None:
        if uncertainty_path is None:
            if uncertainty_method != "none":
                raise ValueError(
                    f"Condition {condition_id} declares uncertainty_method={uncertainty_method!r} "
                    "but has no uncertainty_path."
                )
            return None
        path = ArtifactScenarioEngine._safe_bundle_path(
            bundle.path,
            uncertainty_path,
            label=f"uncertainty_path for {condition_id}",
        )
        if not path.exists():
            raise FileNotFoundError(f"Missing uncertainty artifact for {condition_id}: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Uncertainty artifact for {condition_id} must be a JSON object.")
        return payload

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
