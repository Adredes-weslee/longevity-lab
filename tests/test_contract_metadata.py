"""Contract metadata tests."""

from __future__ import annotations

from pathlib import Path

from longevity_lab.artifacts.manifest import (
    ArtifactManifest,
    ConditionArtifact,
    DatasetInfo,
    ExplanationArtifactManifest,
    save_manifest,
)
from longevity_lab.artifacts.store import ArtifactStore
from longevity_lab.services.contract_metadata import build_artifact_model_metadata


def test_artifact_metadata_reports_manifest_declared_shap_method(tmp_path: Path) -> None:
    """Model metadata should expose SHAP when the manifest declares an existing SHAP artifact."""
    bundle_dir = tmp_path / "models" / "bundle-shap-metadata"
    bundle_dir.mkdir(parents=True)
    pipeline_path = bundle_dir / "heart_disease.joblib"
    tree_path = bundle_dir / "heart_disease_explanation.joblib"
    shap_path = bundle_dir / "heart_disease_shap_explanation.joblib"
    for path in (pipeline_path, tree_path, shap_path):
        path.write_bytes(b"placeholder")
    save_manifest(
        ArtifactManifest(
            dataset=DatasetInfo(name="brfss", version="test"),
            features=["age", "bmi"],
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
                            feature_names=["age", "bmi"],
                        )
                    ],
                )
            ],
        ),
        bundle_dir / "manifest.json",
    )
    bundle = ArtifactStore(tmp_path / "models").resolve(bundle_id="bundle-shap-metadata")

    metadata = build_artifact_model_metadata(bundle)

    assert metadata.explanation_methods == ["shap", "tree_path"]
