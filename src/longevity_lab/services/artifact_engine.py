"""Artifact-backed scenario engine.

This engine is the end-state replacement for the demo heuristic engine. It
loads trained per-condition pipelines and returns condition probabilities.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import joblib  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.api.schemas import FeatureProfile, ScenarioGeographySelection
from longevity_lab.artifacts.store import ArtifactBundle, ArtifactStore
from longevity_lab.domain.catalog import CONDITIONS
from longevity_lab.services.engine_types import ConditionScore, ScenarioEngine
from longevity_lab.services.explanations import ExplanationRecord, build_explanation_records
from longevity_lab.services.uncertainty import build_uncertainty_summary


@dataclass(frozen=True, slots=True)
class LoadedExplanationArtifact:
    """A loaded model-matched explanation artifact."""

    method: str
    artifact: object


@dataclass(frozen=True, slots=True)
class LoadedConditionModel:
    """A resolved condition model pipeline."""

    condition_id: str
    pipeline: object
    explanation_artifacts: tuple[LoadedExplanationArtifact, ...] = ()
    uncertainty_payload: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class LoadedContextFeatureLookup:
    """Bundle-local state-year context lookup data."""

    feature_names: tuple[str, ...]
    rows_by_key: dict[tuple[str, int], dict[str, object]]
    default_values: dict[str, object]


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
        self._context_lookup = self._load_context_feature_lookup(self._bundle)
        self._models = self._load_models(self._bundle)

    def evaluate(
        self,
        profile: FeatureProfile,
        geography: ScenarioGeographySelection | None = None,
    ) -> list[ConditionScore]:
        """Evaluate a profile by calling each loaded per-condition pipeline.

        Selected geography supplies state-year context only when the trusted bundle
        manifest declares the exact feature list and a bundle-local lookup asset.
        """
        frame = self._profile_frame(profile, geography=geography)
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
            explanations = _build_first_available_explanations(
                frame=frame,
                artifacts=model.explanation_artifacts,
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

    def _profile_frame(
        self,
        profile: FeatureProfile,
        *,
        geography: ScenarioGeographySelection | None,
    ) -> pd.DataFrame:
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
        values.update(self._context_values_for_geography(geography))
        for feature_name in self._bundle.manifest.features:
            values.setdefault(feature_name, None)
        return pd.DataFrame([{name: values[name] for name in self._bundle.manifest.features}])

    def _context_values_for_geography(
        self,
        geography: ScenarioGeographySelection | None,
    ) -> dict[str, object]:
        """Return manifest-declared context values for the selected geography or defaults."""
        lookup = self._context_lookup
        if lookup is None:
            return {}
        if geography is not None:
            row = lookup.rows_by_key.get((geography.state_fips, geography.year))
            if row is not None:
                return {name: row.get(name) for name in lookup.feature_names}
        return {name: lookup.default_values.get(name) for name in lookup.feature_names}

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
            models[condition.condition_id] = LoadedConditionModel(
                condition_id=condition.condition_id,
                pipeline=joblib.load(pipeline_path),
                explanation_artifacts=ArtifactScenarioEngine._load_explanation_artifacts(
                    bundle=bundle,
                    condition_id=condition.condition_id,
                    legacy_method=condition.explanation_method,
                    legacy_path=condition.explanation_path,
                    records=condition.explanation_artifacts,
                ),
                uncertainty_payload=ArtifactScenarioEngine._load_uncertainty_payload(
                    bundle=bundle,
                    condition_id=condition.condition_id,
                    uncertainty_method=condition.uncertainty_method,
                    uncertainty_path=condition.uncertainty_path,
                ),
            )
        return models

    @staticmethod
    def _load_explanation_artifacts(
        *,
        bundle: ArtifactBundle,
        condition_id: str,
        legacy_method: str,
        legacy_path: str | None,
        records: Sequence[object],
    ) -> tuple[LoadedExplanationArtifact, ...]:
        loaded: list[LoadedExplanationArtifact] = []
        seen_paths: set[str] = set()
        for record in sorted(
            records,
            key=lambda item: 0 if getattr(item, "method", "") == "shap" else 1,
        ):
            method = str(getattr(record, "method", ""))
            artifact_path = str(getattr(record, "artifact_path", ""))
            if not method or not artifact_path:
                continue
            artifact = ArtifactScenarioEngine._load_explanation_artifact_path(
                bundle=bundle,
                condition_id=condition_id,
                relative_path=artifact_path,
            )
            loaded.append(LoadedExplanationArtifact(method=method, artifact=artifact))
            seen_paths.add(artifact_path)

        if legacy_path and legacy_path not in seen_paths:
            loaded.append(
                LoadedExplanationArtifact(
                    method=legacy_method,
                    artifact=ArtifactScenarioEngine._load_explanation_artifact_path(
                        bundle=bundle,
                        condition_id=condition_id,
                        relative_path=legacy_path,
                    ),
                )
            )
        return tuple(loaded)

    @staticmethod
    def _load_explanation_artifact_path(
        *,
        bundle: ArtifactBundle,
        condition_id: str,
        relative_path: str,
    ) -> object:
        explanation_path = ArtifactScenarioEngine._safe_bundle_path(
            bundle.path,
            relative_path,
            label=f"explanation_path for {condition_id}",
        )
        if not explanation_path.exists():
            raise FileNotFoundError(
                f"Missing explanation artifact for {condition_id}: {explanation_path}"
            )
        return joblib.load(explanation_path)

    @staticmethod
    def _load_context_feature_lookup(bundle: ArtifactBundle) -> LoadedContextFeatureLookup | None:
        metadata = bundle.manifest.context_features
        if metadata is None or not metadata.feature_names:
            return None
        feature_names = tuple(metadata.feature_names)
        missing_features = sorted(set(feature_names) - set(bundle.manifest.features))
        if missing_features:
            raise ValueError(
                "Artifact context_features must be included in manifest.features "
                f"(missing {missing_features})."
            )
        if metadata.join_keys != ["state_fips", "year"]:
            raise ValueError(
                "Artifact context_features currently support only state-year join keys "
                "['state_fips', 'year']."
            )
        lookup_path = ArtifactScenarioEngine._safe_bundle_path(
            bundle.path,
            metadata.lookup_path,
            label="context_features.lookup_path",
        )
        if not lookup_path.exists():
            raise FileNotFoundError(f"Missing context lookup artifact: {lookup_path}")
        payload = json.loads(lookup_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Context lookup artifact must be a JSON object.")
        payload_features = payload.get("feature_names")
        if payload_features != list(feature_names):
            raise ValueError(
                "Context lookup feature_names must exactly match manifest context_features."
            )
        payload_join_keys = payload.get("join_keys")
        if payload_join_keys != metadata.join_keys:
            raise ValueError("Context lookup join_keys must match manifest context_features.")
        rows_payload = payload.get("rows")
        if not isinstance(rows_payload, list):
            raise ValueError("Context lookup artifact must contain a rows list.")

        rows_by_key: dict[tuple[str, int], dict[str, object]] = {}
        for row in rows_payload:
            if not isinstance(row, dict):
                raise ValueError("Context lookup rows must be JSON objects.")
            state_fips = _normalize_state_fips(row.get("state_fips"))
            year = _normalize_year(row.get("year"))
            if state_fips is None or year is None:
                raise ValueError("Context lookup rows require state_fips and year.")
            key = (state_fips, year)
            if key in rows_by_key:
                raise ValueError(f"Duplicate context lookup state-year key: {key}.")
            rows_by_key[key] = {name: row.get(name) for name in feature_names}
        return LoadedContextFeatureLookup(
            feature_names=feature_names,
            rows_by_key=rows_by_key,
            default_values={name: metadata.default_values.get(name) for name in feature_names},
        )

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


def _normalize_state_fips(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return f"{int(float(text)):02d}"
    except ValueError:
        return text.zfill(2) if text.isdigit() else None


def _normalize_year(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _build_first_available_explanations(
    *,
    frame: pd.DataFrame,
    artifacts: tuple[LoadedExplanationArtifact, ...],
) -> list[ExplanationRecord]:
    """Return the first non-empty explanation list from manifest-declared artifacts."""
    for artifact in artifacts:
        try:
            records = build_explanation_records(
                frame=frame,
                method=artifact.method,
                explanation_artifact=artifact.artifact,
            )
        except Exception:
            continue
        if records:
            return records
    return []
