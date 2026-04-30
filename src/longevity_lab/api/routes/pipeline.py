"""Pipeline status routes.

These endpoints are intended for local development QA: they provide quick, visual
confirmation that raw downloads and processed integration outputs exist.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from longevity_lab.api.schemas import (
    PipelineArtifactStatus,
    PipelineProvenanceSummary,
    PipelineStatusResponse,
)
from longevity_lab.config import get_settings
from longevity_lab.pipeline.ingest import build_ingest_paths

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _iso_utc_from_mtime(mtime_seconds: float) -> str:
    return dt.datetime.fromtimestamp(mtime_seconds, tz=dt.UTC).isoformat()


def _display_path(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _artifact_status(
    artifact_id: str,
    label: str,
    path: Path,
    *,
    base_dir: Path,
) -> PipelineArtifactStatus:
    exists = path.exists()
    display_path = _display_path(path, root=base_dir)
    if not exists:
        return PipelineArtifactStatus(
            artifact_id=artifact_id,
            label=label,
            path=display_path,
            exists=False,
        )

    stat = path.stat()
    return PipelineArtifactStatus(
        artifact_id=artifact_id,
        label=label,
        path=display_path,
        exists=True,
        bytes=stat.st_size,
        modified_at=_iso_utc_from_mtime(stat.st_mtime),
    )


def _load_provenance_summary(path: Path, *, base_dir: Path) -> PipelineProvenanceSummary | None:
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    dataset_name = str(payload.get("dataset_name", ""))
    dataset_version = str(payload.get("dataset_version", ""))
    retrieved_at = str(payload.get("retrieved_at", ""))
    if not dataset_name or not dataset_version or not retrieved_at:
        return None

    extra: dict[str, Any] = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "dataset_name",
            "dataset_version",
            "retrieved_at",
            "sources",
            "files",
        }
    }
    return PipelineProvenanceSummary(
        path=_display_path(path, root=base_dir),
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        retrieved_at=retrieved_at,
        extra=extra,
    )


def _epa_state_year_provenance_candidates(provenance_dir: Path, *, year: int) -> list[Path]:
    """Return EPA state-year provenance file paths that cover the requested year."""
    year_str = str(year)
    prefix = "epa_airdata_annual_aqi_state_year_"
    matches: list[Path] = []
    for candidate in provenance_dir.glob(f"{prefix}*.json"):
        stem = candidate.stem
        if not stem.startswith(prefix):
            continue
        years_part = stem.removeprefix(prefix)
        years = [part for part in years_part.split("_") if part]
        if year_str in years:
            matches.append(candidate)
    return sorted(matches)


@router.get("/status", response_model=PipelineStatusResponse)
def status(year: int = Query(2023, ge=2000, le=2100)) -> PipelineStatusResponse:
    """Return a lightweight readiness check for local pipeline outputs."""
    base_dir = get_settings().data_dir
    paths = build_ingest_paths(base_dir)
    provenance_dir = paths.provenance_dir

    artifacts = [
        _artifact_status(
            "brfss_xpt",
            f"BRFSS {year} raw (XPT)",
            paths.brfss_raw_dir(year) / f"LLCP{year}.XPT",
            base_dir=base_dir,
        ),
        _artifact_status(
            "epa_aqi_csv",
            f"EPA AirData {year} raw (county CSV)",
            paths.epa_airdata_annual_aqi_csv(year),
            base_dir=base_dir,
        ),
        _artifact_status(
            "brfss_person_parquet",
            f"BRFSS {year} processed (Parquet)",
            paths.brfss_person_parquet(year),
            base_dir=base_dir,
        ),
        _artifact_status(
            "epa_aqi_state_year_parquet",
            "EPA processed (state-year AQI Parquet)",
            paths.epa_state_year_parquet(),
            base_dir=base_dir,
        ),
        _artifact_status(
            "integrated_person_year_parquet",
            f"Integrated {year} (BRFSS\u2194EPA Parquet)",
            paths.integrated_person_year_parquet(year),
            base_dir=base_dir,
        ),
        _artifact_status(
            "duckdb",
            "DuckDB views (longevity_lab.duckdb)",
            paths.duckdb_path,
            base_dir=base_dir,
        ),
    ]

    provenance_candidates = [
        paths.provenance_brfss_raw(year),
        paths.provenance_brfss_person(year),
        paths.provenance_epa_airdata_annual_aqi_by_county(year),
        *_epa_state_year_provenance_candidates(provenance_dir, year=year),
        paths.provenance_integrated_person_year(year),
    ]
    seen = set()
    candidates: list[Path] = []
    for candidate in provenance_candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)
    provenance = [
        summary
        for candidate in candidates
        if (summary := _load_provenance_summary(candidate, base_dir=base_dir)) is not None
    ]

    return PipelineStatusResponse(year=year, artifacts=artifacts, provenance=provenance)
