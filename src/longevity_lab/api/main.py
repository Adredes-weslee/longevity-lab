"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from longevity_lab.api.middleware import request_logging_middleware
from longevity_lab.api.routes import health, metadata, models, pipeline, scenario
from longevity_lab.api.schemas import FeatureProfile, ModelMetadataResponse, RuntimeMetadataResponse
from longevity_lab.artifacts.store import ArtifactBundle, ArtifactStore
from longevity_lab.config import Settings, get_settings
from longevity_lab.services.artifact_engine import ArtifactScenarioEngine
from longevity_lab.services.contract_metadata import (
    build_artifact_model_metadata,
    build_demo_model_metadata,
)
from longevity_lab.services.engine_types import ScenarioEngine
from longevity_lab.services.metadata_service import MetadataService
from longevity_lab.services.model_card_service import ModelCardService
from longevity_lab.services.scenario_service import DemoScenarioEngine, ScenarioService


def _parse_cors_allow_origins(value: str) -> list[str]:
    origins = [item.strip() for item in value.split(",") if item.strip()]
    if "*" in origins:
        raise ValueError(
            "LONGEVITY_LAB_CORS_ALLOW_ORIGINS cannot include '*'. "
            "Provide explicit origins (comma-separated) instead."
        )
    return origins


def _try_load_auto_artifact_engine(
    *,
    store: ArtifactStore,
    bundle: ArtifactBundle,
    bundle_id: str,
) -> ArtifactScenarioEngine | None:
    """Load and validate an auto-detected artifact engine, returning None on local defects."""
    try:
        engine = ArtifactScenarioEngine(store=store, bundle_id=bundle_id)
        scores = engine.evaluate(FeatureProfile())
    except Exception:
        return None
    if not scores:
        return None
    return engine


def _select_engine(
    settings: Settings,
) -> tuple[ScenarioEngine, RuntimeMetadataResponse, ModelMetadataResponse]:
    """Select the runtime engine and metadata from settings and local artifacts."""
    store = ArtifactStore(settings.artifacts_dir / "models")

    if settings.engine == "demo":
        return (
            DemoScenarioEngine(),
            RuntimeMetadataResponse(
                engine_mode="demo",
                engine_source="explicit",
                artifact_bundle_id=None,
                message="Demo scoring mode is active because LONGEVITY_LAB_ENGINE=demo.",
            ),
            build_demo_model_metadata(),
        )

    if settings.engine == "artifact":
        bundle = store.resolve(settings.artifact_bundle)
        artifact_id = store.bundle_id(bundle)
        return (
            ArtifactScenarioEngine(store=store, bundle_id=settings.artifact_bundle),
            RuntimeMetadataResponse(
                engine_mode="artifact",
                engine_source="explicit",
                artifact_bundle_id=artifact_id,
                message="Artifact-backed scoring mode is active.",
            ),
            build_artifact_model_metadata(bundle, artifact_id=artifact_id),
        )

    for auto_bundle in store.try_resolve_all(settings.artifact_bundle):
        artifact_id = store.bundle_id(auto_bundle)
        engine = _try_load_auto_artifact_engine(
            store=store,
            bundle=auto_bundle,
            bundle_id=artifact_id,
        )
        if engine is not None:
            return (
                engine,
                RuntimeMetadataResponse(
                    engine_mode="artifact",
                    engine_source="auto",
                    artifact_bundle_id=artifact_id,
                    message=(
                        "Artifact-backed scoring mode was selected automatically "
                        "from local artifacts."
                    ),
                ),
                build_artifact_model_metadata(auto_bundle, artifact_id=artifact_id),
            )

    return (
        DemoScenarioEngine(),
        RuntimeMetadataResponse(
            engine_mode="demo",
            engine_source="fallback",
            artifact_bundle_id=None,
            message="Demo scoring mode is active because no valid local artifact bundle was found.",
        ),
        build_demo_model_metadata(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize app-scoped services once per process."""
    settings = get_settings()
    engine, runtime, model_metadata = _select_engine(settings)
    app.state.metadata_service = MetadataService(
        runtime=runtime,
        model_metadata=model_metadata,
    )
    app.state.model_card_service = ModelCardService(
        artifact_store=ArtifactStore(settings.artifacts_dir / "models"),
        model_metadata=model_metadata,
    )
    app.state.scenario_service = ScenarioService(
        engine=engine,
        model_metadata=model_metadata,
    )
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
    app.include_router(models.router, prefix=settings.api_prefix)
    app.include_router(pipeline.router, prefix=settings.api_prefix)
    app.include_router(scenario.router, prefix=settings.api_prefix)
    return app


app = create_app()


def run() -> None:
    """Run the development server."""
    uvicorn.run("longevity_lab.api.main:app", host="127.0.0.1", port=8000, reload=True)
