"""Artifact-backed engine smoke tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import joblib  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
import pytest
from sklearn.dummy import DummyClassifier  # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.tree import DecisionTreeClassifier  # type: ignore[import-untyped]

from longevity_lab.api.schemas import FeatureProfile, ScenarioGeographySelection
from longevity_lab.artifacts.manifest import (
    ArtifactManifest,
    ConditionArtifact,
    ContextFeatureManifest,
    DatasetInfo,
    ExplanationArtifactManifest,
    save_manifest,
)
from longevity_lab.artifacts.store import ArtifactStore
from longevity_lab.pipeline.modeling import FeaturePreprocessor, SampleWeightPipeline
from longevity_lab.services.artifact_engine import ArtifactScenarioEngine
from longevity_lab.services.explanations import build_explanation_records
from longevity_lab.services.uncertainty import build_uncertainty_summary


class ReversedClassesPipeline:
    """Pickleable stub pipeline with reversed class ordering."""

    classes_ = np.array([1, 0])

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:  # noqa: ARG002
        """Return probabilities aligned with classes_ ordering."""
        return np.array([[0.2, 0.8]])


class ContextAwarePipeline:
    """Pickleable stub pipeline whose score changes with state-year context."""

    classes_ = np.array([0, 1])

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        """Return higher risk for higher manifest-supplied poverty context."""
        poverty = float(frame["acs_poverty_percent"].iloc[0])
        probability = 0.8 if poverty >= 20.0 else 0.2
        return np.array([[1.0 - probability, probability]])


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
    assert scores[0].explanations == []
    assert scores[0].uncertainty is None


def test_artifact_engine_returns_typed_tree_explanations_and_uncertainty(
    tmp_path: Path,
) -> None:
    """Manifest-declared explanation and uncertainty artifacts should reach scores."""
    base_dir = tmp_path / "models"
    bundle_id = "bundle-explanations"
    bundle_dir = base_dir / bundle_id
    bundle_dir.mkdir(parents=True)
    frame = pd.DataFrame(
        [
            {
                "age": 65,
                "bmi": 31.0,
                "smoker": True,
                "alcohol_servings_per_week": 8,
                "exercise_minutes_per_week": 20,
                "annual_aqi": 95,
            },
            {
                "age": 30,
                "bmi": 22.0,
                "smoker": False,
                "alcohol_servings_per_week": 1,
                "exercise_minutes_per_week": 240,
                "annual_aqi": 40,
            },
            {
                "age": 72,
                "bmi": 35.0,
                "smoker": True,
                "alcohol_servings_per_week": 10,
                "exercise_minutes_per_week": 5,
                "annual_aqi": 120,
            },
            {
                "age": 44,
                "bmi": 24.0,
                "smoker": False,
                "alcohol_servings_per_week": 2,
                "exercise_minutes_per_week": 160,
                "annual_aqi": 55,
            },
        ]
    )
    labels = [1, 0, 1, 0]
    explanation_pipeline = SampleWeightPipeline(
        [
            ("preprocess", FeaturePreprocessor(feature_names=tuple(frame.columns))),
            ("model", DecisionTreeClassifier(max_depth=2, random_state=7)),
        ]
    )
    explanation_pipeline.fit(frame, pd.Series(labels))
    pipeline_path = bundle_dir / "heart_disease.joblib"
    explanation_path = bundle_dir / "heart_disease_explanation.joblib"
    uncertainty_path = bundle_dir / "heart_disease_uncertainty.json"
    joblib.dump(explanation_pipeline, pipeline_path)
    joblib.dump(explanation_pipeline, explanation_path)
    uncertainty_path.write_text(
        ('{"half_width": 0.08, "confidence_level": 0.9, "caveat": "Test calibration interval."}\n'),
        encoding="utf-8",
    )
    save_manifest(
        ArtifactManifest(
            dataset=DatasetInfo(name="brfss", version="test"),
            features=list(frame.columns),
            conditions=[
                ConditionArtifact(
                    condition_id="heart_disease",
                    pipeline_path=pipeline_path.name,
                    explanation_path=explanation_path.name,
                    explanation_method="tree_path",
                    uncertainty_method="calibration_interval",
                    uncertainty_path=uncertainty_path.name,
                )
            ],
        ),
        bundle_dir / "manifest.json",
    )

    engine = ArtifactScenarioEngine(store=ArtifactStore(base_dir), bundle_id=bundle_id)
    scores = engine.evaluate(
        FeatureProfile(
            age=65,
            bmi=31.0,
            smoker=True,
            alcohol_servings_per_week=8,
            exercise_minutes_per_week=20,
            annual_aqi=95,
        )
    )

    assert scores[0].explanations
    assert scores[0].explanations[0].method == "tree_path"
    assert scores[0].explanations[0].caveat
    assert scores[0].key_drivers == [record.display_name for record in scores[0].explanations]
    assert scores[0].uncertainty is not None
    assert scores[0].uncertainty.method == "calibration_interval"
    assert scores[0].uncertainty.confidence_level == pytest.approx(0.9)
    assert scores[0].uncertainty.caveat == "Test calibration interval."


def test_tree_path_direction_uses_branch_positive_class_risk() -> None:
    """Tree-path direction should describe risk movement, not merely branch side."""
    frame = pd.DataFrame({"age": [30.0, 40.0, 60.0, 70.0]})
    labels = pd.Series([1, 1, 0, 0])
    pipeline = SampleWeightPipeline(
        [
            ("preprocess", FeaturePreprocessor(feature_names=("age",))),
            ("model", DecisionTreeClassifier(max_depth=1, random_state=7)),
        ]
    )
    pipeline.fit(frame, labels)

    records = build_explanation_records(
        method="tree_path",
        explanation_artifact=pipeline,
        frame=pd.DataFrame({"age": [70.0]}),
    )

    assert records
    assert records[0].feature == "age"
    assert records[0].direction == "decreases"


def test_uncertainty_requires_manifest_payload() -> None:
    """Manifest-declared uncertainty must not fabricate default intervals without payloads."""
    with pytest.raises(ValueError, match="requires an explicit artifact payload"):
        build_uncertainty_summary(
            probability=0.4,
            method="calibration_interval",
            payload=None,
        )

    with pytest.raises(ValueError, match="requires `half_width`"):
        build_uncertainty_summary(
            probability=0.4,
            method="calibration_interval",
            payload={},
        )

    with pytest.raises(ValueError, match="between 0 and 1"):
        build_uncertainty_summary(
            probability=0.4,
            method="calibration_interval",
            payload={"half_width": float("nan")},
        )


def test_artifact_engine_rejects_uncertainty_method_without_payload_path(
    tmp_path: Path,
) -> None:
    """A manifest cannot opt into uncertainty without a concrete artifact file."""
    base_dir = tmp_path / "models"
    bundle_id = "bundle-uncertainty-missing-path"
    bundle_dir = base_dir / bundle_id
    bundle_dir.mkdir(parents=True)
    pipeline_path = bundle_dir / "heart_disease.joblib"
    joblib.dump(ReversedClassesPipeline(), pipeline_path)
    save_manifest(
        ArtifactManifest(
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
                    uncertainty_method="calibration_interval",
                )
            ],
        ),
        bundle_dir / "manifest.json",
    )

    with pytest.raises(ValueError, match="has no uncertainty_path"):
        ArtifactScenarioEngine(store=ArtifactStore(base_dir), bundle_id=bundle_id)


def test_shap_explanations_use_optional_tree_explainer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SHAP explanations should be lazy and use a TreeExplainer when available."""
    frame = pd.DataFrame({"age": [65.0], "bmi": [31.0]})

    class _FakeExplainer:
        def __init__(self, model: object) -> None:
            self.model = model

        def shap_values(self, transformed: pd.DataFrame) -> np.ndarray:
            assert list(transformed.columns) == ["age", "bmi"]
            return np.array([[0.4, -0.1]])

    monkeypatch.setitem(
        sys.modules,
        "shap",
        SimpleNamespace(TreeExplainer=_FakeExplainer),
    )

    records = build_explanation_records(
        method="shap",
        explanation_artifact=object(),
        frame=frame,
    )

    assert [record.feature for record in records] == ["age", "bmi"]
    assert records[0].direction == "increases"
    assert records[1].direction == "decreases"
    assert records[0].method == "shap"


def test_shap_explanations_use_compact_background_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SHAP explanation payloads should carry compact background data, not raw full tables."""
    frame = pd.DataFrame({"age": [65.0], "bmi": [31.0]})
    background = pd.DataFrame({"age": [40.0, 70.0], "bmi": [24.0, 35.0]})
    seen_background: list[pd.DataFrame] = []

    class _FakeExplainer:
        def __init__(self, model: object, data: pd.DataFrame | None = None) -> None:
            self.model = model
            if data is not None:
                seen_background.append(data)

        def shap_values(self, transformed: pd.DataFrame) -> np.ndarray:
            assert list(transformed.columns) == ["age", "bmi"]
            return np.array([[0.25, 0.05]])

    class _IdentityPreprocess:
        def transform(self, values: pd.DataFrame) -> pd.DataFrame:
            return values

        def get_feature_names_out(self) -> list[str]:
            return ["age", "bmi"]

    pipeline = SimpleNamespace(
        named_steps={
            "preprocess": _IdentityPreprocess(),
            "model": object(),
        }
    )
    monkeypatch.setitem(
        sys.modules,
        "shap",
        SimpleNamespace(TreeExplainer=_FakeExplainer),
    )

    records = build_explanation_records(
        method="shap",
        explanation_artifact={
            "kind": "tree_shap",
            "pipeline": pipeline,
            "background": background,
            "feature_names": ["age", "bmi"],
        },
        frame=frame,
    )

    assert seen_background
    assert len(seen_background[0]) == 2
    assert [record.method for record in records] == ["shap", "shap"]


def test_artifact_engine_prefers_manifest_declared_shap_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Artifact scoring should select manifest-declared SHAP when the artifact is present."""
    base_dir = tmp_path / "models"
    bundle_id = "bundle-shap"
    bundle_dir = base_dir / bundle_id
    bundle_dir.mkdir(parents=True)
    frame = pd.DataFrame(
        [
            {
                "age": 65,
                "bmi": 31.0,
                "smoker": True,
                "alcohol_servings_per_week": 8,
                "exercise_minutes_per_week": 20,
                "annual_aqi": 95,
            },
            {
                "age": 30,
                "bmi": 22.0,
                "smoker": False,
                "alcohol_servings_per_week": 1,
                "exercise_minutes_per_week": 240,
                "annual_aqi": 40,
            },
            {
                "age": 72,
                "bmi": 35.0,
                "smoker": True,
                "alcohol_servings_per_week": 10,
                "exercise_minutes_per_week": 5,
                "annual_aqi": 120,
            },
            {
                "age": 44,
                "bmi": 24.0,
                "smoker": False,
                "alcohol_servings_per_week": 2,
                "exercise_minutes_per_week": 160,
                "annual_aqi": 55,
            },
        ]
    )
    labels = [1, 0, 1, 0]
    pipeline = SampleWeightPipeline(
        [
            ("preprocess", FeaturePreprocessor(feature_names=tuple(frame.columns))),
            ("model", DecisionTreeClassifier(max_depth=2, random_state=7)),
        ]
    )
    pipeline.fit(frame, pd.Series(labels))
    pipeline_path = bundle_dir / "heart_disease.joblib"
    tree_path = bundle_dir / "heart_disease_explanation.joblib"
    shap_path = bundle_dir / "heart_disease_shap_explanation.joblib"
    joblib.dump(pipeline, pipeline_path)
    joblib.dump(pipeline, tree_path)
    joblib.dump(
        {
            "kind": "tree_shap",
            "pipeline": pipeline,
            "background": frame.head(2),
            "feature_names": list(frame.columns),
        },
        shap_path,
    )

    class _FakeExplainer:
        def __init__(self, model: object, data: pd.DataFrame | None = None) -> None:
            self.model = model
            self.data = data

        def shap_values(self, transformed: pd.DataFrame) -> np.ndarray:
            return np.array([[0.4, -0.2, 0.1, 0.0, 0.0, 0.0]])

    monkeypatch.setitem(sys.modules, "shap", SimpleNamespace(TreeExplainer=_FakeExplainer))
    save_manifest(
        ArtifactManifest(
            dataset=DatasetInfo(name="brfss", version="test"),
            features=list(frame.columns),
            conditions=[
                ConditionArtifact(
                    condition_id="heart_disease",
                    pipeline_path=pipeline_path.name,
                    explanation_path=tree_path.name,
                    explanation_method="tree_path",
                    explanation_artifacts=[
                        ExplanationArtifactManifest(
                            method="tree_path",
                            artifact_path=tree_path.name,
                            feature_names=list(frame.columns),
                        ),
                        ExplanationArtifactManifest(
                            method="shap",
                            artifact_path=shap_path.name,
                            background_sample_size=2,
                            feature_names=list(frame.columns),
                        ),
                    ],
                )
            ],
        ),
        bundle_dir / "manifest.json",
    )

    engine = ArtifactScenarioEngine(store=ArtifactStore(base_dir), bundle_id=bundle_id)
    scores = engine.evaluate(
        FeatureProfile(
            age=65,
            bmi=31.0,
            smoker=True,
            alcohol_servings_per_week=8,
            exercise_minutes_per_week=20,
            annual_aqi=95,
        )
    )

    assert scores[0].explanations
    assert scores[0].explanations[0].method == "shap"


def test_artifact_engine_falls_back_when_shap_artifact_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bad SHAP payload should not abort scoring when tree-path fallback is declared."""
    base_dir = tmp_path / "models"
    bundle_id = "bundle-shap-fallback"
    bundle_dir = base_dir / bundle_id
    bundle_dir.mkdir(parents=True)
    frame = pd.DataFrame(
        [
            {
                "age": 65,
                "bmi": 31.0,
                "smoker": True,
                "alcohol_servings_per_week": 8,
                "exercise_minutes_per_week": 20,
                "annual_aqi": 95,
            },
            {
                "age": 30,
                "bmi": 22.0,
                "smoker": False,
                "alcohol_servings_per_week": 1,
                "exercise_minutes_per_week": 240,
                "annual_aqi": 40,
            },
            {
                "age": 72,
                "bmi": 35.0,
                "smoker": True,
                "alcohol_servings_per_week": 10,
                "exercise_minutes_per_week": 5,
                "annual_aqi": 120,
            },
            {
                "age": 44,
                "bmi": 24.0,
                "smoker": False,
                "alcohol_servings_per_week": 2,
                "exercise_minutes_per_week": 160,
                "annual_aqi": 55,
            },
        ]
    )
    labels = [1, 0, 1, 0]
    pipeline = SampleWeightPipeline(
        [
            ("preprocess", FeaturePreprocessor(feature_names=tuple(frame.columns))),
            ("model", DecisionTreeClassifier(max_depth=2, random_state=7)),
        ]
    )
    pipeline.fit(frame, pd.Series(labels))
    pipeline_path = bundle_dir / "heart_disease.joblib"
    tree_path = bundle_dir / "heart_disease_explanation.joblib"
    shap_path = bundle_dir / "heart_disease_shap_explanation.joblib"
    joblib.dump(pipeline, pipeline_path)
    joblib.dump(pipeline, tree_path)
    joblib.dump(
        {
            "kind": "tree_shap",
            "pipeline": pipeline,
            "background": frame.head(2),
            "feature_names": list(frame.columns),
        },
        shap_path,
    )

    class _ExplodingExplainer:
        def __init__(self, model: object, data: pd.DataFrame | None = None) -> None:
            self.model = model
            self.data = data

        def shap_values(self, transformed: pd.DataFrame) -> np.ndarray:
            raise Exception("simulated shap explainer failure")

    monkeypatch.setitem(
        sys.modules,
        "shap",
        SimpleNamespace(TreeExplainer=_ExplodingExplainer),
    )
    save_manifest(
        ArtifactManifest(
            dataset=DatasetInfo(name="brfss", version="test"),
            features=list(frame.columns),
            conditions=[
                ConditionArtifact(
                    condition_id="heart_disease",
                    pipeline_path=pipeline_path.name,
                    explanation_path=tree_path.name,
                    explanation_method="tree_path",
                    explanation_artifacts=[
                        ExplanationArtifactManifest(
                            method="shap",
                            artifact_path=shap_path.name,
                            background_sample_size=2,
                            feature_names=list(frame.columns),
                        ),
                        ExplanationArtifactManifest(
                            method="tree_path",
                            artifact_path=tree_path.name,
                            feature_names=list(frame.columns),
                        ),
                    ],
                )
            ],
        ),
        bundle_dir / "manifest.json",
    )

    engine = ArtifactScenarioEngine(store=ArtifactStore(base_dir), bundle_id=bundle_id)
    scores = engine.evaluate(
        FeatureProfile(
            age=65,
            bmi=31.0,
            smoker=True,
            alcohol_servings_per_week=8,
            exercise_minutes_per_week=20,
            annual_aqi=95,
        )
    )

    assert scores[0].explanations
    assert scores[0].explanations[0].method == "tree_path"


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


def test_artifact_engine_uses_manifest_context_lookup_for_selected_geography(
    tmp_path: Path,
) -> None:
    """Selected state-year geography should populate only manifest-declared context features."""
    base_dir = tmp_path / "models"
    bundle_id = "bundle-context"
    bundle_dir = base_dir / bundle_id
    bundle_dir.mkdir(parents=True)
    pipeline_path = bundle_dir / "heart_disease.joblib"
    joblib.dump(ContextAwarePipeline(), pipeline_path)
    lookup_path = bundle_dir / "context_state_year_lookup.json"
    lookup_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "feature_names": ["acs_poverty_percent"],
                "join_keys": ["state_fips", "year"],
                "rows": [
                    {"state_fips": "06", "year": 2023, "acs_poverty_percent": 25.0},
                    {"state_fips": "13", "year": 2023, "acs_poverty_percent": 8.0},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    save_manifest(
        ArtifactManifest(
            dataset=DatasetInfo(name="integrated_person_year", version="2023"),
            features=[
                "age",
                "bmi",
                "smoker",
                "alcohol_servings_per_week",
                "exercise_minutes_per_week",
                "annual_aqi",
                "acs_poverty_percent",
            ],
            context_features=ContextFeatureManifest(
                feature_names=["acs_poverty_percent"],
                source_ids=["census_acs5_api_context"],
                join_keys=["state_fips", "year"],
                data_vintage="ACS 2023 5-year",
                lookup_path=lookup_path.name,
                default_values={"acs_poverty_percent": 10.0},
                caveats=[
                    "State-year context is background geography context, not a personal behavior.",
                ],
            ),
            conditions=[
                ConditionArtifact(
                    condition_id="heart_disease",
                    pipeline_path=pipeline_path.name,
                    explanation_method="tree_path",
                )
            ],
        ),
        bundle_dir / "manifest.json",
    )

    engine = ArtifactScenarioEngine(store=ArtifactStore(base_dir), bundle_id=bundle_id)
    profile = FeatureProfile()

    california = engine.evaluate(
        profile,
        geography=ScenarioGeographySelection(level="state", state_fips="06", year=2023),
    )
    georgia = engine.evaluate(
        profile,
        geography=ScenarioGeographySelection(level="state", state_fips="13", year=2023),
    )
    defaulted = engine.evaluate(profile)

    assert california[0].probability == pytest.approx(0.8)
    assert georgia[0].probability == pytest.approx(0.2)
    assert defaulted[0].probability == pytest.approx(0.2)


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
