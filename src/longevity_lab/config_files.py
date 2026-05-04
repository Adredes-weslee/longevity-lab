"""Helpers for locating bundled configuration files."""

from __future__ import annotations

from importlib import resources
from pathlib import Path


def source_config_dir() -> Path:
    """Return the repo-local configuration directory for source checkouts."""
    return Path(__file__).resolve().parents[2] / "conf"


def config_dir_path() -> Path:
    """Return a filesystem path to configuration files.

    Source checkouts use the repo-level ``conf/`` directory. Installed wheels
    use the copy bundled under ``longevity_lab/conf``.
    """
    source_dir = source_config_dir()
    if source_dir.exists():
        return source_dir
    package_dir = resources.files("longevity_lab").joinpath("conf")
    return Path(str(package_dir))


def config_file_path(*parts: str) -> Path:
    """Return a filesystem path to one configuration file."""
    return config_dir_path().joinpath(*parts)
