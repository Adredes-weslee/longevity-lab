"""Tests for CORS configuration settings."""

from __future__ import annotations

import pytest
from starlette.middleware.cors import CORSMiddleware

from longevity_lab.api.main import create_app
from longevity_lab.config import get_settings


def test_create_app_uses_cors_allow_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    """CORS origins should be configurable via LONGEVITY_LAB_CORS_ALLOW_ORIGINS."""
    monkeypatch.setenv(
        "LONGEVITY_LAB_CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://localhost:3000",
    )
    get_settings.cache_clear()
    app = create_app()
    cors = next(m for m in app.user_middleware if getattr(m, "cls", None) is CORSMiddleware)
    assert cors.kwargs["allow_origins"] == ["http://localhost:5173", "http://localhost:3000"]
    get_settings.cache_clear()


def test_create_app_rejects_wildcard_cors_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wildcard origins should be rejected to avoid confusing credentials behavior."""
    monkeypatch.setenv("LONGEVITY_LAB_CORS_ALLOW_ORIGINS", "*")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="cannot include '\\*'"):
        create_app()
    get_settings.cache_clear()


def test_create_app_disables_cors_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """If configured empty, CORS middleware should not be added."""
    monkeypatch.setenv("LONGEVITY_LAB_CORS_ALLOW_ORIGINS", "")
    get_settings.cache_clear()
    app = create_app()
    assert not any(getattr(m, "cls", None) is CORSMiddleware for m in app.user_middleware)
    get_settings.cache_clear()
