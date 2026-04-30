"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(env_prefix="LONGEVITY_LAB_", env_file=".env", extra="ignore")

    app_name: str = "Longevity Lab API"
    environment: str = "development"
    api_prefix: str = "/api"
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    data_dir: Path = Field(default_factory=lambda: Path("data"))
    artifacts_dir: Path = Field(default_factory=lambda: Path("artifacts"))
    engine: Literal["auto", "demo", "artifact"] = "auto"
    artifact_bundle: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
