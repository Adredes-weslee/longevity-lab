"""Model-card routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from longevity_lab.api.dependencies import get_model_card_service
from longevity_lab.api.schemas import ModelCardBundleResponse
from longevity_lab.services.model_card_service import ModelCardService

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/cards", response_model=ModelCardBundleResponse)
def model_cards(
    model_card_service: Annotated[ModelCardService, Depends(get_model_card_service)],
) -> ModelCardBundleResponse:
    """Return model-card metrics for the active model bundle."""
    return model_card_service.get_model_cards()
