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
        for method in _unique_sorted(_manifest_uncertainty_methods(bundle))
    ]
    explanation_methods = [
        cast(ExplanationMethod, method)
        for method in _unique_sorted(_manifest_explanation_methods(bundle))
    ]
    retrieved_at = bundle.manifest.dataset.retrieved_at
    context_metadata = bundle.manifest.context_features
    context_features = context_metadata.feature_names if context_metadata is not None else []
    context_caveat = (
        context_metadata.caveats[0]
        if context_metadata is not None and context_metadata.caveats
        else None
    )
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
            available=context_metadata is not None and bool(context_features),
            levels=["state"] if context_metadata is not None and context_features else [],
            source=(
                ", ".join(context_metadata.source_ids)
                if context_metadata is not None and context_metadata.source_ids
                else None
            ),
            feature_count=len(context_features),
            features=list(context_features),
            caveat=context_caveat,
        ),
    )


def _unique_sorted(values: Iterable[object]) -> list[str]:
    """Return deterministic unique string values from a small iterable."""
    return sorted({str(value) for value in values})


def _manifest_explanation_methods(bundle: ArtifactBundle) -> list[str]:
    """Return manifest-declared explanation methods with bundle-local artifact paths."""
    methods: list[str] = []
    for item in bundle.manifest.conditions:
        for record in item.explanation_artifacts:
            if record.artifact_path and _bundle_path_exists(bundle, record.artifact_path):
                methods.append(str(record.method))
        if item.explanation_path is not None and _bundle_path_exists(bundle, item.explanation_path):
            methods.append(str(item.explanation_method))
    return methods


def _manifest_uncertainty_methods(bundle: ArtifactBundle) -> list[str]:
    """Return manifest-declared uncertainty methods with bundle-local artifact paths."""
    methods: list[str] = []
    for item in bundle.manifest.conditions:
        if (
            item.uncertainty_method != "none"
            and item.uncertainty_path is not None
            and _bundle_path_exists(bundle, item.uncertainty_path)
        ):
            methods.append(str(item.uncertainty_method))
    return methods


def _bundle_path_exists(bundle: ArtifactBundle, relative_path: str) -> bool:
    """Return whether a relative path resolves inside the trusted artifact bundle and exists."""
    path = bundle.path / relative_path
    try:
        path.resolve().relative_to(bundle.path.resolve())
    except ValueError:
        return False
    return path.exists()
