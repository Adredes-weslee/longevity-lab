"""Helpers for API contract metadata shared by bootstrap and scoring services."""

from collections.abc import Iterable
from typing import cast

from longevity_lab.api.schemas import (
    ContextualGeographyMetadataResponse,
    ExplanationMethod,
    ModelMetadataResponse,
    UncertaintyMethod,
)
from longevity_lab.artifacts.store import ArtifactBundle


def build_demo_model_metadata() -> ModelMetadataResponse:
    """Return v2 model metadata for the deterministic demo scorer."""
    return ModelMetadataResponse(
        model_mode="demo",
        artifact_id=None,
        data_vintage="demo",
        dataset_name=None,
        dataset_version=None,
        dataset_retrieved_at=None,
        explanation_methods=["demo"],
        uncertainty_available=False,
        uncertainty_methods=[],
        contextual_geography=ContextualGeographyMetadataResponse(
            available=False,
            levels=[],
            source=None,
        ),
    )


def build_artifact_model_metadata(
    bundle: ArtifactBundle,
    *,
    artifact_id: str | None = None,
) -> ModelMetadataResponse:
    """Return v2 model metadata derived from an artifact bundle manifest."""
    uncertainty_methods = [
        cast(UncertaintyMethod, method)
        for method in _unique_sorted(item.uncertainty_method for item in bundle.manifest.conditions)
        if method != "none"
    ]
    explanation_methods = [
        cast(ExplanationMethod, method)
        for method in _unique_sorted(
            item.explanation_method
            for item in bundle.manifest.conditions
            if item.explanation_path is not None
        )
    ]
    retrieved_at = bundle.manifest.dataset.retrieved_at
    return ModelMetadataResponse(
        model_mode="artifact",
        artifact_id=artifact_id or bundle.path.name,
        data_vintage=bundle.manifest.dataset.version,
        dataset_name=bundle.manifest.dataset.name,
        dataset_version=bundle.manifest.dataset.version,
        dataset_retrieved_at=retrieved_at.isoformat() if retrieved_at else None,
        explanation_methods=explanation_methods,
        uncertainty_available=bool(uncertainty_methods),
        uncertainty_methods=uncertainty_methods,
        contextual_geography=ContextualGeographyMetadataResponse(
            available=False,
            levels=[],
            source=None,
        ),
    )


def _unique_sorted(values: Iterable[object]) -> list[str]:
    """Return deterministic unique string values from a small iterable."""
    return sorted({str(value) for value in values})
