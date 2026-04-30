"""Metadata routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from longevity_lab.api.dependencies import get_metadata_service
from longevity_lab.api.schemas import MetadataBootstrapResponse
from longevity_lab.services.metadata_service import MetadataService

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/bootstrap", response_model=MetadataBootstrapResponse)
def bootstrap(
    metadata_service: Annotated[MetadataService, Depends(get_metadata_service)],
) -> MetadataBootstrapResponse:
    """Return bootstrap metadata for the frontend."""
    return metadata_service.get_bootstrap()
