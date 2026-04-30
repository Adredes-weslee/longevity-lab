"""Artifact-backed engine smoke tests."""

from __future__ import annotations

from pathlib import Path

import joblib  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
import pytest
from sklearn.dummy import DummyClassifier  # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]

from longevity_lab.api.schemas import FeatureProfile
from longevity_lab.artifacts.manifest import (
    ArtifactManifest,
    ConditionArtifact,
    DatasetInfo,
    save_manifest,
)
from longevity_lab.artifacts.store import ArtifactStore
from longevity_lab.services.artifact_engine import ArtifactScenarioEngine


class ReversedClassesPipeline:
    """Pickleable stub pipeline with reversed class ordering."""

    classes_ = np.array([1, 0])

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:  # noqa: ARG002
        """Return probabilities aligned with classes_ ordering."""
        return np.array([[0.2, 0.8]])


def _write_bundle(base_dir: Path) -> str:
    bundle_id = "bundle-test"
    bundle_dir = base_dir / bundle_id
    bundle_dir.mkdir(parents=True)

    frame = pd.DataFrame(
        [
            {
                "age": 45,
                "bmi": 28.0,
                "smoker": True,
                "alcohol_servings_per_week": 10,
                "exercise_minutes_per_week": 60,
                "annual_aqi": 80,
            },
            {
                "age": 45,
                "bmi": 26.0,
                "smoker": False,
                "alcohol_servings_per_week": 4,
                "exercise_minutes_per_week": 180,
                "annual_aqi": 55,
            },
        ]
    )
    labels = [1, 0]

    pipeline = Pipeline([("model", DummyClassifier(strategy="prior"))])
    pipeline.fit(frame, labels)

    pipeline_path = bundle_dir / "heart_disease.joblib"
    joblib.dump(pipeline, pipeline_path)

    manifest = ArtifactManifest(
        dataset=DatasetInfo(name="brfss", version="test"),
        features=list(frame.columns),
        conditions=[
            ConditionArtifact(
                condition_id="heart_disease",
                pipeline_path=pipeline_path.name,
                explanation_method="tree_path",
            )
        ],
    )
    save_manifest(manifest, bundle_dir / "manifest.json")
    return bundle_id


def test_artifact_engine_evaluate(tmp_path: Path) -> None:
    """ArtifactScenarioEngine should load a bundle and score a profile."""
    base_dir = tmp_path / "models"
    bundle_id = _write_bundle(base_dir)

    store = ArtifactStore(base_dir)
    engine = ArtifactScenarioEngine(store=store, bundle_id=bundle_id)
    profile = FeatureProfile(
        age=45,
        bmi=28.0,
        smoker=True,
        alcohol_servings_per_week=10,
        exercise_minutes_per_week=60,
        annual_aqi=80,
    )
    scores = engine.evaluate(profile)
    assert len(scores) == 1
    assert scores[0].condition_id == "heart_disease"
    assert 0.0 <= scores[0].probability <= 1.0


def test_artifact_engine_selects_positive_class_probability(tmp_path: Path) -> None:
    """The engine should pick the probability where classes_ == 1, not column index 1."""
    base_dir = tmp_path / "models"
    bundle_id = "bundle-reversed"
    bundle_dir = base_dir / bundle_id
    bundle_dir.mkdir(parents=True)

    pipeline_path = bundle_dir / "heart_disease.joblib"
    joblib.dump(ReversedClassesPipeline(), pipeline_path)

    manifest = ArtifactManifest(
        dataset=DatasetInfo(name="brfss", version="test"),
        features=[
            "age",
            "bmi",
            "smoker",
            "alcohol_servings_per_week",
            "exercise_minutes_per_week",
            "annual_aqi",
        ],
        conditions=[
            ConditionArtifact(
                condition_id="heart_disease",
                pipeline_path=pipeline_path.name,
                explanation_method="tree_path",
            )
        ],
    )
    save_manifest(manifest, bundle_dir / "manifest.json")

    store = ArtifactStore(base_dir)
    engine = ArtifactScenarioEngine(store=store, bundle_id=bundle_id)
    profile = FeatureProfile(
        age=45,
        bmi=28.0,
        smoker=True,
        alcohol_servings_per_week=10,
        exercise_minutes_per_week=60,
        annual_aqi=80,
    )
    scores = engine.evaluate(profile)
    assert scores[0].probability == pytest.approx(0.2)


def test_artifact_engine_rejects_path_traversal(tmp_path: Path) -> None:
    """Bundle manifests should not be able to reference files outside the bundle directory."""
    base_dir = tmp_path / "models"
    bundle_id = "bundle-unsafe"
    bundle_dir = base_dir / bundle_id
    bundle_dir.mkdir(parents=True)

    safe_pipeline_path = bundle_dir / "heart_disease.joblib"
    joblib.dump(ReversedClassesPipeline(), safe_pipeline_path)

    manifest = ArtifactManifest(
        dataset=DatasetInfo(name="brfss", version="test"),
        features=[],
        conditions=[
            ConditionArtifact(
                condition_id="heart_disease",
                pipeline_path="../heart_disease.joblib",
                explanation_method="tree_path",
            )
        ],
    )
    save_manifest(manifest, bundle_dir / "manifest.json")

    store = ArtifactStore(base_dir)
    with pytest.raises(ValueError, match="Unsafe pipeline_path"):
        ArtifactScenarioEngine(store=store, bundle_id=bundle_id)


def test_artifact_engine_rejects_unknown_conditions(tmp_path: Path) -> None:
    """Unknown condition IDs in the manifest should fail fast with a clear error."""
    base_dir = tmp_path / "models"
    bundle_id = "bundle-unknown"
    bundle_dir = base_dir / bundle_id
    bundle_dir.mkdir(parents=True)

    pipeline_path = bundle_dir / "unknown.joblib"
    joblib.dump(ReversedClassesPipeline(), pipeline_path)

    manifest = ArtifactManifest(
        dataset=DatasetInfo(name="brfss", version="test"),
        features=[],
        conditions=[
            ConditionArtifact(
                condition_id="not_in_catalog",
                pipeline_path=pipeline_path.name,
                explanation_method="tree_path",
            )
        ],
    )
    save_manifest(manifest, bundle_dir / "manifest.json")

    store = ArtifactStore(base_dir)
    with pytest.raises(ValueError, match="unknown condition_id"):
        ArtifactScenarioEngine(store=store, bundle_id=bundle_id)
