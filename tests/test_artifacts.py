"""Artifact schema and loading tests."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from longevity_lab.artifacts.manifest import (
    ArtifactManifest,
    ConditionArtifact,
    ContextFeatureManifest,
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


def test_manifest_roundtrip_with_context_feature_lookup(tmp_path: Path) -> None:
    """Context-aware manifests should preserve exact feature and lookup provenance."""
    manifest = ArtifactManifest(
        dataset=DatasetInfo(name="integrated_person_year", version="2023"),
        features=["age", "acs_poverty_percent", "svi_overall_percentile"],
        context_features=ContextFeatureManifest(
            feature_names=["acs_poverty_percent", "svi_overall_percentile"],
            source_ids=["census_acs5_api_context", "cdc_atsdr_svi_us_county_csv"],
            join_keys=["state_fips", "year"],
            data_vintage="ACS 2023 5-year; SVI 2022 county aggregation",
            lookup_path="context_state_year_lookup.json",
            default_values={"acs_poverty_percent": 12.5, "svi_overall_percentile": 0.42},
            caveats=[
                "State-year context is background geography context, not a personal behavior.",
            ],
        ),
        conditions=[
            ConditionArtifact(
                condition_id="heart_disease",
                pipeline_path="heart_disease.joblib",
                explanation_method="tree_path",
            )
        ],
    )
    path = tmp_path / "manifest.json"
    save_manifest(manifest, path)

    loaded = load_manifest(path)

    assert loaded.context_features is not None
    assert loaded.context_features.feature_names == [
        "acs_poverty_percent",
        "svi_overall_percentile",
    ]
    assert loaded.context_features.join_keys == ["state_fips", "year"]
    assert loaded.context_features.lookup_path == "context_state_year_lookup.json"


def test_context_feature_manifest_requires_explicit_serving_contract() -> None:
    """Context scoring should not activate without explicit provenance and defaults."""
    with pytest.raises(ValueError, match="source_ids"):
        ContextFeatureManifest(
            feature_names=["acs_poverty_percent"],
            join_keys=["state_fips", "year"],
            data_vintage="ACS 2023 5-year",
            lookup_path="context_state_year_lookup.json",
            default_values={"acs_poverty_percent": 12.0},
            caveats=["State-year context caveat."],
        )

    with pytest.raises(ValueError, match="default_values"):
        ContextFeatureManifest(
            feature_names=["acs_poverty_percent"],
            source_ids=["census_acs5_api_context"],
            join_keys=["state_fips", "year"],
            data_vintage="ACS 2023 5-year",
            lookup_path="context_state_year_lookup.json",
            caveats=["State-year context caveat."],
        )

    with pytest.raises(ValueError, match="caveats"):
        ContextFeatureManifest(
            feature_names=["acs_poverty_percent"],
            source_ids=["census_acs5_api_context"],
            join_keys=["state_fips", "year"],
            data_vintage="ACS 2023 5-year",
            lookup_path="context_state_year_lookup.json",
            default_values={"acs_poverty_percent": 12.0},
        )
