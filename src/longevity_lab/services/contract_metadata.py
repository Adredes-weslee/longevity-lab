"""Helpers for API contract metadata shared by bootstrap and scoring services."""

from collections.abc import Iterable
from typing import cast

from longevity_lab.api.schemas import (
    ContextualGeographyMetadataResponse,
    ExplanationMethod,
    GeographyLevel,
    ModelMetadataResponse,
    UncertaintyMethod,
)
from longevity_lab.artifacts.store import ArtifactBundle

_GEOGRAPHY_LEVEL_ORDER: tuple[GeographyLevel, ...] = ("state", "county", "tract", "zcta")


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


def build_artifact_model_metadata(bundle: ArtifactBundle) -> ModelMetadataResponse:
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
        artifact_id=bundle.path.name,
        data_vintage=bundle.manifest.dataset.version,
        dataset_name=bundle.manifest.dataset.name,
        dataset_version=bundle.manifest.dataset.version,
        dataset_retrieved_at=retrieved_at.isoformat() if retrieved_at else None,
        explanation_methods=explanation_methods,
        uncertainty_available=bool(uncertainty_methods),
        uncertainty_methods=uncertainty_methods,
        contextual_geography=_infer_contextual_geography(bundle.manifest.features),
    )


def _unique_sorted(values: Iterable[object]) -> list[str]:
    """Return deterministic unique string values from a small iterable."""
    return sorted({str(value) for value in values})


def _infer_contextual_geography(features: list[str]) -> ContextualGeographyMetadataResponse:
    levels: set[GeographyLevel] = set()
    for feature in features:
        normalized = feature.lower()
        if normalized in {"annual_aqi", "state_fips"} or normalized.startswith(
            ("pm25_", "ozone_", "aqi_", "state_")
        ):
            levels.add("state")
        if "county" in normalized or normalized.startswith(("places_", "svi_", "acs_")):
            levels.add("county")
        if "tract" in normalized:
            levels.add("tract")
        if "zcta" in normalized:
            levels.add("zcta")

    ordered_levels = [level for level in _GEOGRAPHY_LEVEL_ORDER if level in levels]
    return ContextualGeographyMetadataResponse(
        available=bool(ordered_levels),
        levels=ordered_levels,
        source="artifact_features" if ordered_levels else None,
    )
