"""Scenario service contract tests."""

from __future__ import annotations

import pytest

from longevity_lab.api.schemas import FeatureProfile, RiskBand
from longevity_lab.services.engine_types import ConditionScore
from longevity_lab.services.scenario_service import ScenarioService


class StubEngine:
    """Scenario engine stub that returns one condition with a chosen probability."""

    def __init__(self, probability: float) -> None:
        """Store the probability to return."""
        self._probability = probability

    def evaluate(self, profile: FeatureProfile) -> list[ConditionScore]:
        """Return a single condition score for the provided profile."""
        return [
            ConditionScore(
                condition_id="heart_disease",
                label="Heart disease",
                organ_id="heart",
                probability=self._probability,
                key_drivers=[],
            )
        ]


@pytest.mark.parametrize(
    ("raw_probability", "expected_probability", "expected_band"),
    [
        (0.14996, 0.15, "amber"),
        (0.34996, 0.35, "red"),
    ],
)
def test_condition_band_aligns_with_returned_probability(
    raw_probability: float,
    expected_probability: float,
    expected_band: RiskBand,
) -> None:
    """Risk bands should align with the returned probability, not an unrounded value."""
    service = ScenarioService(engine=StubEngine(raw_probability))
    profile = FeatureProfile(
        age=40,
        bmi=25.0,
        smoker=False,
        alcohol_servings_per_week=0,
        exercise_minutes_per_week=150,
        annual_aqi=50,
    )
    response = service.compare(profile, profile)
    condition = response.baseline.conditions[0]
    assert condition.probability == expected_probability
    assert condition.band == expected_band
