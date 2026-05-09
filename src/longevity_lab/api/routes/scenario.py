"""Scenario routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from longevity_lab.api.dependencies import get_scenario_service
from longevity_lab.api.schemas import (
    ScenarioCompareRequest,
    ScenarioCompareResponse,
    ScenarioExplainRequest,
)
from longevity_lab.domain.catalog import CONDITIONS
from longevity_lab.services.scenario_service import ScenarioService

router = APIRouter(prefix="/scenario", tags=["scenario"])


@router.post("/compare", response_model=ScenarioCompareResponse)
def compare(
    payload: ScenarioCompareRequest,
    scenario_service: Annotated[ScenarioService, Depends(get_scenario_service)],
) -> ScenarioCompareResponse:
    """Compare baseline and candidate profiles."""
    return scenario_service.compare(
        payload.baseline,
        payload.candidate,
        geography=payload.geography,
        include_explanations=payload.explanation_mode == "full",
    )


@router.post("/explain", response_model=ScenarioCompareResponse)
def explain(
    payload: ScenarioExplainRequest,
    scenario_service: Annotated[ScenarioService, Depends(get_scenario_service)],
) -> ScenarioCompareResponse:
    """Return selected model explanations without forcing live compare to compute all SHAP."""
    condition_ids = _selected_condition_ids(payload)
    return scenario_service.compare(
        payload.baseline,
        payload.candidate,
        geography=payload.geography,
        include_explanations=True,
        explanation_condition_ids=condition_ids,
    )


def _selected_condition_ids(payload: ScenarioExplainRequest) -> set[str]:
    if payload.condition_id:
        known_condition_ids = {condition.condition_id for condition in CONDITIONS}
        if payload.condition_id not in known_condition_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown condition_id: {payload.condition_id}",
            )
        return {payload.condition_id}

    if payload.organ_id:
        condition_ids = {
            condition.condition_id
            for condition in CONDITIONS
            if condition.organ_id == payload.organ_id
        }
        if not condition_ids:
            raise HTTPException(status_code=404, detail=f"Unknown organ_id: {payload.organ_id}")
        return condition_ids

    raise HTTPException(
        status_code=422,
        detail="Either organ_id or condition_id is required for lazy explanations.",
    )
