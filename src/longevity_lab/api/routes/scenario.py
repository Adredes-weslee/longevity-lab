"""Scenario routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from longevity_lab.api.dependencies import get_scenario_service
from longevity_lab.api.schemas import ScenarioCompareRequest, ScenarioCompareResponse
from longevity_lab.services.scenario_service import ScenarioService

router = APIRouter(prefix="/scenario", tags=["scenario"])


@router.post("/compare", response_model=ScenarioCompareResponse)
def compare(
    payload: ScenarioCompareRequest,
    scenario_service: Annotated[ScenarioService, Depends(get_scenario_service)],
) -> ScenarioCompareResponse:
    """Compare baseline and candidate profiles."""
    return scenario_service.compare(payload.baseline, payload.candidate)
