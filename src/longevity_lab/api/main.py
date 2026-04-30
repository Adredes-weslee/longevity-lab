"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from longevity_lab.api.middleware import request_logging_middleware
from longevity_lab.api.routes import health, metadata, pipeline, scenario
from longevity_lab.artifacts.store import ArtifactStore
from longevity_lab.config import get_settings
from longevity_lab.services.artifact_engine import ArtifactScenarioEngine
from longevity_lab.services.engine_types import ScenarioEngine
from longevity_lab.services.metadata_service import MetadataService
from longevity_lab.services.scenario_service import DemoScenarioEngine, ScenarioService


def _parse_cors_allow_origins(value: str) -> list[str]:
    origins = [item.strip() for item in value.split(",") if item.strip()]
    if "*" in origins:
        raise ValueError(
            "LONGEVITY_LAB_CORS_ALLOW_ORIGINS cannot include '*'. "
            "Provide explicit origins (comma-separated) instead."
        )
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize app-scoped services once per process."""
    app.state.metadata_service = MetadataService()
    settings = get_settings()
    engine: ScenarioEngine
    if settings.engine == "artifact":
        store = ArtifactStore(settings.artifacts_dir / "models")
        engine = ArtifactScenarioEngine(store=store, bundle_id=settings.artifact_bundle)
    else:
        engine = DemoScenarioEngine()
    app.state.scenario_service = ScenarioService(engine=engine)
    yield


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.middleware("http")(request_logging_middleware)
    origins = _parse_cors_allow_origins(settings.cors_allow_origins)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(metadata.router, prefix=settings.api_prefix)
    app.include_router(pipeline.router, prefix=settings.api_prefix)
    app.include_router(scenario.router, prefix=settings.api_prefix)
    return app


app = create_app()


def run() -> None:
    """Run the development server."""
    uvicorn.run("longevity_lab.api.main:app", host="127.0.0.1", port=8000, reload=True)
