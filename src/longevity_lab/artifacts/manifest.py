"""Artifact manifest schema.

This module defines a small, versioned JSON format for trained model bundles.
The goal is to make training outputs discoverable and loadable by the API
without requiring tribal knowledge.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ExplanationMethod = Literal["demo", "tree_path", "shap"]
UncertaintyMethod = Literal["none", "calibration_interval"]


class DatasetInfo(BaseModel):
    """Provenance metadata for the training dataset snapshot."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    retrieved_at: dt.datetime | None = None
    sources: list[str] = Field(default_factory=list)


class ContextFeatureManifest(BaseModel):
    """State-year context feature lookup metadata for trusted artifact bundles."""

    model_config = ConfigDict(extra="forbid")

    feature_names: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    join_keys: list[str] = Field(default_factory=list)
    data_vintage: str
    lookup_path: str
    default_values: dict[str, int | float | str | bool | None] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_explicit_serving_contract(self) -> ContextFeatureManifest:
        """Require complete metadata before context features can activate scoring."""
        if not self.feature_names:
            raise ValueError("context_features.feature_names must not be empty.")
        if not self.source_ids:
            raise ValueError("context_features.source_ids must not be empty.")
        if self.join_keys != ["state_fips", "year"]:
            raise ValueError("context_features.join_keys must be exactly ['state_fips', 'year'].")
        if not self.data_vintage.strip():
            raise ValueError("context_features.data_vintage must not be empty.")
        if not self.lookup_path.strip():
            raise ValueError("context_features.lookup_path must not be empty.")
        missing_defaults = sorted(set(self.feature_names) - set(self.default_values))
        if missing_defaults:
            raise ValueError(
                "context_features.default_values must include every context feature "
                f"(missing {missing_defaults})."
            )
        if not self.caveats:
            raise ValueError("context_features.caveats must not be empty.")
        return self


class ExplanationArtifactManifest(BaseModel):
    """Metadata for one model-matched explanation artifact."""

    model_config = ConfigDict(extra="forbid")

    method: ExplanationMethod
    artifact_path: str
    background_sample_size: int | None = None
    feature_names: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class ConditionArtifact(BaseModel):
    """One condition model artifact entry inside a bundle."""

    model_config = ConfigDict(extra="forbid")

    condition_id: str
    pipeline_path: str
    explanation_path: str | None = None
    metrics_path: str | None = None
    explanation_method: ExplanationMethod = "tree_path"
    explanation_artifacts: list[ExplanationArtifactManifest] = Field(default_factory=list)
    uncertainty_method: UncertaintyMethod = "none"
    uncertainty_path: str | None = None
    notes: str | None = None


class ArtifactManifest(BaseModel):
    """Top-level bundle manifest."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    dataset: DatasetInfo
    features: list[str] = Field(default_factory=list)
    context_features: ContextFeatureManifest | None = None
    conditions: list[ConditionArtifact] = Field(default_factory=list)
    git_commit: str | None = None
    notes: str | None = None


def load_manifest(path: Path) -> ArtifactManifest:
    """Load a manifest from disk."""
    data = path.read_text(encoding="utf-8")
    return ArtifactManifest.model_validate_json(data)


def save_manifest(manifest: ArtifactManifest, path: Path) -> None:
    """Write a manifest to disk as pretty-printed JSON."""
    payload = manifest.model_dump_json(indent=2)
    path.write_text(payload + "\n", encoding="utf-8")
