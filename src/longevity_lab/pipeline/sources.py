"""Versioned public data-source registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from longevity_lab.config_files import config_file_path


class YearSupport(BaseModel):
    """Supported year declaration for a public data source."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["explicit", "range"]
    years: list[int] = Field(default_factory=list)
    start: int | None = None
    end: int | None = None

    def supports(self, year: int) -> bool:
        """Return whether this source supports `year`."""
        if self.mode == "explicit":
            return year in self.years
        if self.start is not None and year < self.start:
            return False
        if self.end is not None and year > self.end:
            return False
        return True


class DataSource(BaseModel):
    """Registry metadata for one scriptable public data source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    title: str
    official_url: str
    download_url_template: str
    year_support: YearSupport
    geography: str
    expected_file_pattern: str
    checksum_policy: str
    license_note: str
    local_landing_path: str

    def ensure_supported_year(self, year: int) -> None:
        """Raise if this source does not support `year`."""
        if not self.year_support.supports(year):
            raise NotImplementedError(
                f"{self.source_id} does not support year {year} in the local registry."
            )

    def format_value(self, template: str, *, year: int) -> str:
        """Format a registry template with supported date tokens."""
        self.ensure_supported_year(year)
        return template.format(year=year, yy=str(year)[-2:])

    def download_url(self, *, year: int) -> str:
        """Return the concrete download URL for `year`."""
        return self.format_value(self.download_url_template, year=year)

    def official_page_url(self, *, year: int) -> str:
        """Return the source landing page URL for `year`."""
        return self.format_value(self.official_url, year=year)

    def expected_file(self, *, year: int) -> str:
        """Return the expected local filename or glob pattern for `year`."""
        return self.format_value(self.expected_file_pattern, year=year)

    def landing_path(self, *, year: int) -> str:
        """Return the registry landing path under the data base directory."""
        return self.format_value(self.local_landing_path, year=year)


class DataSourceRegistry(BaseModel):
    """Collection of versioned source records."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    sources: list[DataSource]

    def by_id(self) -> dict[str, DataSource]:
        """Return sources keyed by `source_id`, rejecting duplicates."""
        indexed: dict[str, DataSource] = {}
        for source in self.sources:
            if source.source_id in indexed:
                raise ValueError(f"Duplicate source_id in registry: {source.source_id}")
            indexed[source.source_id] = source
        return indexed

    def require(self, source_id: str) -> DataSource:
        """Return a source record or raise a clear error."""
        indexed = self.by_id()
        try:
            return indexed[source_id]
        except KeyError as exc:
            raise KeyError(f"Unknown data source: {source_id}") from exc


def default_registry_path() -> Path:
    """Return the repo-local registry path."""
    return config_file_path("data_sources.yaml")


def load_data_source_registry(path: Path | None = None) -> DataSourceRegistry:
    """Load the JSON-compatible YAML registry file."""
    registry_path = path or default_registry_path()
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    return DataSourceRegistry.model_validate(payload)
