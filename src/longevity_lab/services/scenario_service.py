"""Scenario evaluation services."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict

from longevity_lab.api.schemas import (
    ConditionScoreResponse,
    ExplanationRecordResponse,
    FeatureProfile,
    ModelMetadataResponse,
    OrganDeltaResponse,
    OrganSummaryResponse,
    RiskBand,
    ScenarioCompareResponse,
    ScenarioEvaluationResponse,
    UncertaintySummaryResponse,
)
from longevity_lab.domain.catalog import CONDITIONS, ORGANS
from longevity_lab.services.contract_metadata import build_demo_model_metadata
from longevity_lab.services.engine_types import ConditionScore, ScenarioEngine
from longevity_lab.services.explanations import demo_explanation_records


class DemoScenarioEngine:
    """Deterministic placeholder engine used before trained artifacts exist."""

    def evaluate(self, profile: FeatureProfile) -> list[ConditionScore]:
        """Score the profile with simple transparent heuristics."""
        smoker_score = 1.0 if profile.smoker else 0.0
        bmi_pressure = max(profile.bmi - 25.0, 0.0) / 20.0
        age_pressure = max(profile.age - 40, 0) / 45.0
        alcohol_pressure = min(profile.alcohol_servings_per_week / 21.0, 1.0)
        exercise_pressure = max(150 - profile.exercise_minutes_per_week, 0) / 150.0
        aqi_pressure = max(profile.annual_aqi - 50, 0) / 150.0
        pm25_pressure = max(profile.pm25_mean - 8.0, 0) / 12.0
        ozone_pressure = max(profile.ozone_mean - 0.035, 0) / 0.05

        weights = {
            "heart_disease": {
                "base": 0.08,
                "age": 0.17,
                "bmi": 0.18,
                "smoker": 0.16,
                "exercise": 0.14,
                "aqi": 0.08,
                "pm25": 0.04,
            },
            "chronic_lung_disease": {
                "base": 0.04,
                "smoker": 0.36,
                "aqi": 0.20,
                "pm25": 0.10,
                "ozone": 0.08,
                "exercise": 0.05,
                "age": 0.08,
            },
            "asthma": {
                "base": 0.07,
                "smoker": 0.12,
                "aqi": 0.16,
                "pm25": 0.08,
                "ozone": 0.10,
                "exercise": 0.04,
                "age": 0.04,
            },
            "stroke": {
                "base": 0.03,
                "age": 0.16,
                "bmi": 0.08,
                "smoker": 0.08,
                "exercise": 0.08,
                "aqi": 0.05,
            },
            "depression": {
                "base": 0.06,
                "exercise": 0.12,
                "alcohol": 0.09,
                "smoker": 0.05,
            },
            "diabetes": {
                "base": 0.05,
                "bmi": 0.28,
                "exercise": 0.16,
                "age": 0.12,
                "alcohol": 0.04,
            },
            "kidney_disease": {
                "base": 0.03,
                "age": 0.14,
                "bmi": 0.10,
                "smoker": 0.05,
                "exercise": 0.05,
            },
            "arthritis": {
                "base": 0.10,
                "age": 0.20,
                "bmi": 0.12,
                "exercise": 0.06,
                "smoker": 0.03,
            },
        }

        factor_values = {
            "age": age_pressure,
            "bmi": bmi_pressure,
            "smoker": smoker_score,
            "alcohol": alcohol_pressure,
            "exercise": exercise_pressure,
            "aqi": aqi_pressure,
            "pm25": pm25_pressure,
            "ozone": ozone_pressure,
        }

        by_condition = {condition.condition_id: condition for condition in CONDITIONS}
        results: list[ConditionScore] = []
        for condition_id, factors in weights.items():
            condition = by_condition[condition_id]
            contributions = {
                name: value * factors[name]
                for name, value in factor_values.items()
                if name in factors
            }
            probability = min(max(factors["base"] + sum(contributions.values()), 0.01), 0.95)
            explanations = demo_explanation_records(contributions)
            key_drivers = [record.display_name for record in explanations]
            results.append(
                ConditionScore(
                    condition_id=condition_id,
                    label=condition.label,
                    organ_id=condition.organ_id,
                    probability=probability,
                    key_drivers=key_drivers,
                    explanations=explanations,
                )
            )
        return results


class ScenarioService:
    """Scenario evaluation orchestration."""

    def __init__(
        self,
        engine: ScenarioEngine,
        model_metadata: ModelMetadataResponse | None = None,
    ) -> None:
        """Store the scenario engine implementation."""
        self._engine = engine
        self._model_metadata = model_metadata or build_demo_model_metadata()

    def compare(
        self,
        baseline: FeatureProfile,
        candidate: FeatureProfile,
    ) -> ScenarioCompareResponse:
        """Compare two profiles and return organ deltas."""
        baseline_eval = self._evaluate(baseline)
        candidate_eval = self._evaluate(candidate)

        organ_deltas: list[OrganDeltaResponse] = []
        baseline_organs = {organ.organ_id: organ for organ in baseline_eval.organs}
        for candidate_summary in candidate_eval.organs:
            baseline_summary = baseline_organs[candidate_summary.organ_id]
            delta = round(candidate_summary.score - baseline_summary.score, 4)
            organ_deltas.append(
                OrganDeltaResponse(
                    organ_id=candidate_summary.organ_id,
                    label=candidate_summary.label,
                    baseline_score=baseline_summary.score,
                    candidate_score=candidate_summary.score,
                    score_delta=delta,
                    band=self._band(candidate_summary.score),
                    top_conditions=candidate_summary.top_conditions,
                )
            )

        return ScenarioCompareResponse(
            baseline=baseline_eval,
            candidate=candidate_eval,
            organ_deltas=organ_deltas,
            model_metadata=self._model_metadata,
        )

    def _evaluate(self, profile: FeatureProfile) -> ScenarioEvaluationResponse:
        """Evaluate a single profile."""
        condition_scores = self._engine.evaluate(profile)
        condition_responses: list[ConditionScoreResponse] = []
        for item in condition_scores:
            probability = round(item.probability, 4)
            condition_responses.append(
                ConditionScoreResponse(
                    condition_id=item.condition_id,
                    label=item.label,
                    organ_id=item.organ_id,
                    probability=probability,
                    band=self._band(probability),
                    key_drivers=item.key_drivers,
                    explanations=[
                        ExplanationRecordResponse(**asdict(record)) for record in item.explanations
                    ],
                    uncertainty=(
                        UncertaintySummaryResponse(**asdict(item.uncertainty))
                        if item.uncertainty
                        else None
                    ),
                )
            )

        grouped = defaultdict(list)
        for condition in condition_scores:
            grouped[condition.organ_id].append(condition)

        organ_summaries: list[OrganSummaryResponse] = []
        served_organ_ids = {condition.organ_id for condition in condition_scores}
        for organ in ORGANS:
            if organ.organ_id not in served_organ_ids:
                continue
            grouped_scores = grouped.get(organ.organ_id, [])
            organ_score = self._average_probability(grouped_scores)
            top_conditions = [
                item.label
                for item in sorted(
                    grouped_scores,
                    key=lambda value: value.probability,
                    reverse=True,
                )[:2]
            ]
            organ_summaries.append(
                OrganSummaryResponse(
                    organ_id=organ.organ_id,
                    label=organ.label,
                    score=organ_score,
                    band=self._band(organ_score),
                    top_conditions=top_conditions,
                )
            )

        summary_score = (
            round(sum(item.score for item in organ_summaries) / len(organ_summaries) * 100, 2)
            if organ_summaries
            else 0.0
        )
        return ScenarioEvaluationResponse(
            summary_score=summary_score,
            organs=organ_summaries,
            conditions=condition_responses,
        )

    @staticmethod
    def _average_probability(condition_scores: Iterable[ConditionScore]) -> float:
        """Compute an organ-level aggregate probability."""
        scores = [item.probability for item in condition_scores]
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 4)

    @staticmethod
    def _band(probability: float) -> RiskBand:
        """Map a probability to a discrete UI band."""
        if probability < 0.15:
            return "green"
        if probability < 0.35:
            return "amber"
        return "red"
