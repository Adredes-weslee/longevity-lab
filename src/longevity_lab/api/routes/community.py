"""Community context and research evidence routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from longevity_lab.api.dependencies import get_community_context_service
from longevity_lab.api.schemas import CommunityContextOverviewResponse
from longevity_lab.services.community_context_service import CommunityContextService
from longevity_lab.services.context_lookup import DEFAULT_CONTEXT_YEAR

router = APIRouter(prefix="/community", tags=["community"])


@router.get("/overview", response_model=CommunityContextOverviewResponse)
def overview(
    community_context: Annotated[
        CommunityContextService,
        Depends(get_community_context_service),
    ],
    year: int = Query(DEFAULT_CONTEXT_YEAR, ge=2000, le=2100),
    places_year: int = Query(2025, ge=2000, le=2100),
    state_fips: str | None = Query(default=None, pattern=r"^\d{1,2}$"),
    county_fips: str | None = Query(default=None, pattern=r"^\d{1,5}$"),
) -> CommunityContextOverviewResponse:
    """Return state/county context, PLACES validation, and causal report summaries."""
    return community_context.get_overview(
        year=year,
        places_year=places_year,
        state_fips=state_fips,
        county_fips=county_fips,
    )
