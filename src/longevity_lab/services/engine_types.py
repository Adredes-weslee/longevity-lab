"""Shared types for scenario scoring engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from longevity_lab.api.schemas import FeatureProfile
from longevity_lab.services.explanations import ExplanationRecord
from longevity_lab.services.uncertainty import UncertaintySummary


@dataclass(frozen=True, slots=True)
class ConditionScore:
    """Internal condition score."""

    condition_id: str
    label: str
    organ_id: str
    probability: float
    key_drivers: list[str]
    explanations: list[ExplanationRecord] = field(default_factory=list)
    uncertainty: UncertaintySummary | None = None


class ScenarioEngine(Protocol):
    """Protocol for scenario scoring engines."""

    def evaluate(self, profile: FeatureProfile) -> list[ConditionScore]:
        """Return condition-level scores for a single profile."""
