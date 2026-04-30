"""Artifact schema and loading tests."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from longevity_lab.artifacts.manifest import (
    ArtifactManifest,
    ConditionArtifact,
    DatasetInfo,
    load_manifest,
    save_manifest,
)


def test_manifest_roundtrip(tmp_path: Path) -> None:
    """Manifests should round-trip through JSON without losing fields."""
    manifest = ArtifactManifest(
        created_at=dt.datetime(2026, 3, 14, tzinfo=dt.UTC),
        dataset=DatasetInfo(
            name="brfss",
            version="2015",
            retrieved_at=dt.datetime(2026, 3, 14, tzinfo=dt.UTC),
            sources=["https://www.cdc.gov/brfss/"],
        ),
        features=["age", "bmi"],
        conditions=[
            ConditionArtifact(
                condition_id="heart_disease",
                pipeline_path="heart_disease.joblib",
                explanation_method="tree_path",
            )
        ],
        git_commit="deadbeef",
        notes="test bundle",
    )
    path = tmp_path / "manifest.json"
    save_manifest(manifest, path)

    loaded = load_manifest(path)
    assert loaded.schema_version == 1
    assert loaded.dataset.name == "brfss"
    assert loaded.features == ["age", "bmi"]
    assert loaded.conditions[0].condition_id == "heart_disease"
