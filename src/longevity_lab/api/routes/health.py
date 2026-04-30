"""Health routes."""

from fastapi import APIRouter

from longevity_lab.api.schemas import HealthResponse
from longevity_lab.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return process health information."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.environment,
    )
