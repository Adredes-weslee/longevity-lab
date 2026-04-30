"""Registry-backed provenance helpers for pipeline outputs."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from longevity_lab.pipeline.common import FileProvenance, write_provenance_json
from longevity_lab.pipeline.sources import DataSourceRegistry, load_data_source_registry


def registry_provenance_extra(
    *,
    registry: DataSourceRegistry,
    source_ids: Sequence[str],
    year: int,
) -> dict[str, Any]:
    """Return structured provenance metadata from the source registry."""
    source_records = []
    for source_id in source_ids:
        source = registry.require(source_id)
        source_records.append(
            {
                "source_id": source.source_id,
                "title": source.title,
                "official_url": source.official_page_url(year=year),
                "download_url": source.download_url(year=year),
                "geography": source.geography,
                "expected_file_pattern": source.expected_file(year=year),
                "checksum_policy": source.checksum_policy,
                "license_note": source.license_note,
                "local_landing_path": source.landing_path(year=year),
            }
        )
    return {
        "source_registry": {
            "schema_version": registry.schema_version,
            "source_ids": list(source_ids),
            "sources": source_records,
        }
    }


def write_registry_provenance_json(
    out_path: Path,
    *,
    dataset_name: str,
    dataset_version: str,
    source_ids: Sequence[str],
    year: int,
    sources: Sequence[str],
    files: Sequence[FileProvenance],
    extra: dict[str, Any] | None = None,
    dry_run: bool = False,
    registry: DataSourceRegistry | None = None,
) -> None:
    """Write provenance JSON enriched with registry source records."""
    source_registry = registry or load_data_source_registry()
    merged_extra = registry_provenance_extra(
        registry=source_registry,
        source_ids=source_ids,
        year=year,
    )
    if extra:
        merged_extra.update(extra)
    write_provenance_json(
        out_path,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        sources=sources,
        files=files,
        extra=merged_extra,
        dry_run=dry_run,
    )
