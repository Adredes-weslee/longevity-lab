"""Metadata service for organs, conditions, and feature definitions."""

from longevity_lab.api.schemas import (
    ConditionDefinitionResponse,
    FeatureDefinition,
    MetadataBootstrapResponse,
    OrganDefinitionResponse,
)
from longevity_lab.domain.catalog import CONDITIONS, ORGANS


class MetadataService:
    """Provide static metadata to the UI and pipeline."""

    def get_bootstrap(self) -> MetadataBootstrapResponse:
        """Return the bootstrap payload for the frontend."""
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
        ]
        organs = [
            OrganDefinitionResponse(
                organ_id=organ.organ_id,
                label=organ.label,
                description=organ.description,
            )
            for organ in ORGANS
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
            for condition in CONDITIONS
        ]
        return MetadataBootstrapResponse(features=features, organs=organs, conditions=conditions)
