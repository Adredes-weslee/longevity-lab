"""Metadata service for organs, conditions, and feature definitions."""

from collections.abc import Iterable

from longevity_lab.api.schemas import (
    ConditionDefinitionResponse,
    FeatureDefinition,
    MetadataBootstrapResponse,
    ModelMetadataResponse,
    OrganDefinitionResponse,
    RuntimeMetadataResponse,
)
from longevity_lab.domain.catalog import CONDITIONS, ORGANS, ConditionDefinition
from longevity_lab.services.contract_metadata import build_demo_model_metadata


class MetadataService:
    """Provide static metadata to the UI and pipeline."""

    def __init__(
        self,
        runtime: RuntimeMetadataResponse | None = None,
        model_metadata: ModelMetadataResponse | None = None,
        condition_ids: Iterable[str] | None = None,
    ) -> None:
        """Store runtime metadata that should be visible to the UI."""
        self._runtime = runtime or RuntimeMetadataResponse(
            engine_mode="demo",
            engine_source="explicit",
            artifact_bundle_id=None,
            message="Demo scoring mode is active.",
        )
        self._model_metadata = model_metadata or build_demo_model_metadata()
        self._condition_ids = tuple(condition_ids) if condition_ids is not None else None

    def get_bootstrap(self) -> MetadataBootstrapResponse:
        """Return the bootstrap payload for the frontend."""
        condition_definitions = self._condition_definitions()
        organ_ids = {condition.organ_id for condition in condition_definitions}
        features = [
            FeatureDefinition(
                field="age",
                label="Age",
                kind="number",
                min_value=18,
                max_value=100,
                step=1,
            ),
            FeatureDefinition(
                field="bmi",
                label="BMI",
                kind="number",
                min_value=10,
                max_value=60,
                step=0.1,
            ),
            FeatureDefinition(field="smoker", label="Smoker", kind="boolean"),
            FeatureDefinition(
                field="alcohol_servings_per_week",
                label="Alcohol servings / week",
                kind="number",
                min_value=0,
                max_value=70,
                step=1,
            ),
            FeatureDefinition(
                field="exercise_minutes_per_week",
                label="Exercise minutes / week",
                kind="number",
                min_value=0,
                max_value=2000,
                step=10,
            ),
            FeatureDefinition(
                field="annual_aqi",
                label="Annual AQI (proxy)",
                kind="number",
                min_value=0,
                max_value=500,
                step=1,
            ),
            FeatureDefinition(
                field="pm25_mean",
                label="PM2.5 annual mean",
                kind="number",
                min_value=0,
                max_value=50,
                step=0.1,
            ),
            FeatureDefinition(
                field="ozone_mean",
                label="Ozone annual mean",
                kind="number",
                min_value=0,
                max_value=0.2,
                step=0.001,
            ),
        ]
        organs = [
            OrganDefinitionResponse(
                organ_id=organ.organ_id,
                label=organ.label,
                description=organ.description,
            )
            for organ in ORGANS
            if self._condition_ids is None or organ.organ_id in organ_ids
        ]
        conditions = [
            ConditionDefinitionResponse(
                condition_id=condition.condition_id,
                label=condition.label,
                organ_id=condition.organ_id,
                description=condition.description,
                citation_label=condition.citation_label,
                citation_url=condition.citation_url,
            )
            for condition in condition_definitions
        ]
        return MetadataBootstrapResponse(
            features=features,
            organs=organs,
            conditions=conditions,
            runtime=self._runtime,
            model_metadata=self._model_metadata,
        )

    def _condition_definitions(self) -> list[ConditionDefinition]:
        """Return catalog conditions served by the active runtime."""
        if self._condition_ids is None:
            return list(CONDITIONS)
        served = set(self._condition_ids)
        return [condition for condition in CONDITIONS if condition.condition_id in served]
