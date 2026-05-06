"""Geography context routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from longevity_lab.api.dependencies import get_context_lookup_service
from longevity_lab.api.schemas import GeographyOptionsResponse
from longevity_lab.services.context_lookup import DEFAULT_CONTEXT_YEAR, ContextLookupService

router = APIRouter(prefix="/context", tags=["context"])


@router.get("/geographies", response_model=GeographyOptionsResponse)
def geographies(
    context_lookup: Annotated[ContextLookupService, Depends(get_context_lookup_service)],
    year: int = Query(DEFAULT_CONTEXT_YEAR, ge=2000, le=2100),
) -> GeographyOptionsResponse:
    """Return state-year geography options and local context readiness."""
    return context_lookup.get_geographies(year=year)
