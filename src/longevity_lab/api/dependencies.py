"""Dependency helpers for route handlers."""

from typing import cast

from fastapi import Request

from longevity_lab.services.metadata_service import MetadataService
from longevity_lab.services.model_card_service import ModelCardService
from longevity_lab.services.scenario_service import ScenarioService


def get_metadata_service(request: Request) -> MetadataService:
    """Return the app-scoped metadata service."""
    return cast(MetadataService, request.app.state.metadata_service)


def get_scenario_service(request: Request) -> ScenarioService:
    """Return the app-scoped scenario service."""
    return cast(ScenarioService, request.app.state.scenario_service)


def get_model_card_service(request: Request) -> ModelCardService:
    """Return the app-scoped model-card service."""
    return cast(ModelCardService, request.app.state.model_card_service)
