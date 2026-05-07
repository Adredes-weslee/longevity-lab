"""State-year geography context lookup for serving contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.api.schemas import (
    ContextReadinessResponse,
    GeographyOptionsResponse,
    GeographyServingMetadataResponse,
    ScenarioGeographySelection,
    StateGeographyOptionResponse,
)
from longevity_lab.artifacts.store import ArtifactBundle
from longevity_lab.pipeline.build_context_tables import context_state_year_parquet

DEFAULT_CONTEXT_YEAR = 2023

STATE_FIPS_TO_NAME: dict[str, str] = {
    "01": "Alabama",
    "02": "Alaska",
    "04": "Arizona",
    "05": "Arkansas",
    "06": "California",
    "08": "Colorado",
    "09": "Connecticut",
    "10": "Delaware",
    "11": "District of Columbia",
    "12": "Florida",
    "13": "Georgia",
    "15": "Hawaii",
    "16": "Idaho",
    "17": "Illinois",
    "18": "Indiana",
    "19": "Iowa",
    "20": "Kansas",
    "21": "Kentucky",
    "22": "Louisiana",
    "23": "Maine",
    "24": "Maryland",
    "25": "Massachusetts",
    "26": "Michigan",
    "27": "Minnesota",
    "28": "Mississippi",
    "29": "Missouri",
    "30": "Montana",
    "31": "Nebraska",
    "32": "Nevada",
    "33": "New Hampshire",
    "34": "New Jersey",
    "35": "New Mexico",
    "36": "New York",
    "37": "North Carolina",
    "38": "North Dakota",
    "39": "Ohio",
    "40": "Oklahoma",
    "41": "Oregon",
    "42": "Pennsylvania",
    "44": "Rhode Island",
    "45": "South Carolina",
    "46": "South Dakota",
    "47": "Tennessee",
    "48": "Texas",
    "49": "Utah",
    "50": "Vermont",
    "51": "Virginia",
    "53": "Washington",
    "54": "West Virginia",
    "55": "Wisconsin",
    "56": "Wyoming",
    "60": "American Samoa",
    "66": "Guam",
    "69": "Northern Mariana Islands",
    "72": "Puerto Rico",
    "78": "U.S. Virgin Islands",
}

_STATE_TABLE_REQUIRED_COLUMNS = {"year", "state_fips", "geography_name"}
_STATE_TABLE_KEY_COLUMNS = {"year", "state_fips", "geography_name"}


@dataclass(frozen=True, slots=True)
class StateContextLookup:
    """One state-year context lookup result for trusted local runtime use."""

    geography: ScenarioGeographySelection
    context_features: dict[str, Any]
    readiness: ContextReadinessResponse


@dataclass(frozen=True, slots=True)
class _LoadedStateContext:
    frame: pd.DataFrame | None
    readiness: ContextReadinessResponse


class ContextLookupService:
    """Read processed state-year context tables without exposing local absolute paths."""

    def __init__(self, data_dir: Path, artifact_bundle: ArtifactBundle | None = None) -> None:
        """Store the local data root and optional active artifact context lookup."""
        self._data_dir = data_dir
        self._state_table_path = context_state_year_parquet(data_dir)
        self._artifact_lookup_path = _artifact_lookup_path(artifact_bundle)
        self._artifact_context_features = _artifact_context_features(artifact_bundle)

    def get_serving_metadata(
        self,
        *,
        default_year: int = DEFAULT_CONTEXT_YEAR,
    ) -> GeographyServingMetadataResponse:
        """Return bootstrap geography metadata for the frontend."""
        geographies = self.get_geographies(year=default_year)
        return GeographyServingMetadataResponse(
            supported_levels=["state"],
            default_year=default_year,
            context_lookup_active=geographies.readiness.active,
            geographies_endpoint="/api/context/geographies",
            caveat=(
                "Only state-year geography context is selectable. The selected state is "
                "background context, not a personal behavior input."
            ),
        )

    def get_geographies(self, *, year: int) -> GeographyOptionsResponse:
        """Return state options and readiness for the requested context year."""
        loaded = self._load_state_context(year=year)
        if loaded.frame is not None and loaded.readiness.active:
            options = self._options_from_frame(loaded.frame, year=year)
        else:
            options = self._fallback_options(year=year)
        return GeographyOptionsResponse(
            selected_year=year,
            supported_levels=["state"],
            options=options,
            readiness=loaded.readiness,
        )

    def lookup_state_context(
        self,
        geography: ScenarioGeographySelection,
    ) -> StateContextLookup:
        """Return local state-year context features when a matching processed row exists."""
        loaded = self._load_state_context(year=geography.year)
        context_features: dict[str, Any] = {}
        if loaded.frame is not None and loaded.readiness.active:
            frame = loaded.frame.copy()
            frame["state_fips"] = frame["state_fips"].astype(str).str.zfill(2)
            match = frame.loc[
                (frame["year"].astype(int) == geography.year)
                & (frame["state_fips"] == geography.state_fips)
            ]
            if not match.empty:
                row = match.iloc[0]
                for column in frame.columns:
                    if column in _STATE_TABLE_KEY_COLUMNS:
                        continue
                    value = row[column]
                    if pd.notna(value):
                        context_features[column] = value.item() if hasattr(value, "item") else value
        return StateContextLookup(
            geography=geography,
            context_features=context_features,
            readiness=loaded.readiness,
        )

    def _load_state_context(self, *, year: int) -> _LoadedStateContext:
        if self._artifact_lookup_path is not None:
            return self._load_artifact_state_context(year=year)
        return self._load_processed_state_context(year=year)

    def _load_processed_state_context(self, *, year: int) -> _LoadedStateContext:
        table_path = self._state_table_path
        display_path = _display_path(table_path, root=self._data_dir)
        if not table_path.exists():
            readiness = ContextReadinessResponse(
                active=False,
                table_exists=False,
                year_available=False,
                table_path=display_path,
                state_count=0,
                available_years=[],
                message=(
                    "Processed state-year context table is not present. State selection is "
                    "available as inert metadata only."
                ),
            )
            return _LoadedStateContext(frame=None, readiness=readiness)

        try:
            frame = pd.read_parquet(table_path)
        except Exception:
            readiness = ContextReadinessResponse(
                active=False,
                table_exists=True,
                year_available=False,
                table_path=display_path,
                state_count=0,
                available_years=[],
                message="Processed state-year context table could not be read.",
            )
            return _LoadedStateContext(frame=None, readiness=readiness)

        if not _STATE_TABLE_REQUIRED_COLUMNS.issubset(set(frame.columns)):
            readiness = ContextReadinessResponse(
                active=False,
                table_exists=True,
                year_available=False,
                table_path=display_path,
                state_count=0,
                available_years=_available_years(frame),
                message="Processed state-year context table is missing required serving columns.",
            )
            return _LoadedStateContext(frame=None, readiness=readiness)

        frame = frame.copy()
        frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
        year_frame = frame.loc[frame["year"] == year].copy()
        state_count = int(year_frame["state_fips"].nunique()) if not year_frame.empty else 0
        year_available = state_count > 0
        readiness = ContextReadinessResponse(
            active=year_available,
            table_exists=True,
            year_available=year_available,
            table_path=display_path,
            state_count=state_count,
            available_years=_available_years(frame),
            message=(
                "Processed state-year context table is available for the selected year."
                if year_available
                else "Processed state-year context table exists but has no rows for this year."
            ),
        )
        return _LoadedStateContext(
            frame=year_frame if year_available else None,
            readiness=readiness,
        )

    def _load_artifact_state_context(self, *, year: int) -> _LoadedStateContext:
        lookup_path = self._artifact_lookup_path
        feature_names = self._artifact_context_features
        if lookup_path is None or not feature_names:
            return self._load_processed_state_context(year=year)

        display_path = _safe_display_path(lookup_path)
        if not lookup_path.exists():
            readiness = ContextReadinessResponse(
                active=False,
                table_exists=False,
                year_available=False,
                table_path=display_path,
                state_count=0,
                available_years=[],
                message=(
                    "Active artifact declares state-year context, but its bundle-local lookup "
                    "artifact is missing."
                ),
            )
            return _LoadedStateContext(frame=None, readiness=readiness)

        try:
            payload = json.loads(lookup_path.read_text(encoding="utf-8"))
            rows_payload = payload.get("rows") if isinstance(payload, dict) else None
            payload_features = payload.get("feature_names") if isinstance(payload, dict) else None
            payload_join_keys = payload.get("join_keys") if isinstance(payload, dict) else None
            if payload_features != list(feature_names):
                raise ValueError("feature_names mismatch")
            if payload_join_keys != ["state_fips", "year"]:
                raise ValueError("join_keys mismatch")
            if not isinstance(rows_payload, list):
                raise ValueError("rows is not a list")
            frame = _artifact_rows_to_frame(rows_payload, feature_names=feature_names)
        except Exception:
            readiness = ContextReadinessResponse(
                active=False,
                table_exists=True,
                year_available=False,
                table_path=display_path,
                state_count=0,
                available_years=[],
                message="Active artifact context lookup could not be read.",
            )
            return _LoadedStateContext(frame=None, readiness=readiness)

        year_frame = frame.loc[frame["year"] == year].copy()
        state_count = int(year_frame["state_fips"].nunique()) if not year_frame.empty else 0
        year_available = state_count > 0
        readiness = ContextReadinessResponse(
            active=year_available,
            table_exists=True,
            year_available=year_available,
            table_path=display_path,
            state_count=state_count,
            available_years=_available_years(frame),
            message=(
                "Active artifact context lookup is available for the selected serving year."
                if year_available
                else (
                    "Active artifact context lookup exists but has no rows for this serving year."
                )
            ),
        )
        return _LoadedStateContext(
            frame=year_frame if year_available else None,
            readiness=readiness,
        )

    @staticmethod
    def _options_from_frame(
        frame: pd.DataFrame,
        *,
        year: int,
    ) -> list[StateGeographyOptionResponse]:
        rows: dict[str, str] = {}
        for _, row in frame.iterrows():
            state_fips = _normalize_state_fips(row["state_fips"])
            if state_fips is None:
                continue
            rows[state_fips] = _state_label(state_fips, row.get("geography_name"))
        return [
            StateGeographyOptionResponse(
                state_fips=state_fips,
                label=label,
                year=year,
                context_available=True,
            )
            for state_fips, label in sorted(rows.items(), key=lambda item: item[1])
        ]

    @staticmethod
    def _fallback_options(*, year: int) -> list[StateGeographyOptionResponse]:
        return [
            StateGeographyOptionResponse(
                state_fips=state_fips,
                label=label,
                year=year,
                context_available=False,
            )
            for state_fips, label in sorted(STATE_FIPS_TO_NAME.items(), key=lambda item: item[1])
        ]


def _available_years(frame: pd.DataFrame) -> list[int]:
    if "year" not in frame.columns:
        return []
    years = pd.to_numeric(frame["year"], errors="coerce")
    return sorted({int(value) for value in years.dropna().unique().tolist()})


def _display_path(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.name


def _safe_display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def _artifact_lookup_path(bundle: ArtifactBundle | None) -> Path | None:
    if bundle is None or bundle.manifest.context_features is None:
        return None
    relative_path = Path(bundle.manifest.context_features.lookup_path)
    if relative_path.is_absolute():
        return None
    bundle_root = bundle.path.resolve()
    lookup_path = (bundle.path / relative_path).resolve()
    try:
        lookup_path.relative_to(bundle_root)
    except ValueError:
        return None
    return lookup_path


def _artifact_context_features(bundle: ArtifactBundle | None) -> tuple[str, ...]:
    if bundle is None or bundle.manifest.context_features is None:
        return ()
    return tuple(bundle.manifest.context_features.feature_names)


def _artifact_rows_to_frame(
    rows_payload: list[object],
    *,
    feature_names: tuple[str, ...],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in rows_payload:
        if not isinstance(row, dict):
            continue
        state_fips = _normalize_state_fips(row.get("state_fips"))
        year = _normalize_year(row.get("year"))
        if state_fips is None or year is None:
            continue
        feature_values = {feature: row.get(feature) for feature in feature_names}
        if any(pd.isna(value) for value in feature_values.values()):
            continue
        rows.append(
            {
                "year": year,
                "state_fips": state_fips,
                "geography_name": _state_label(state_fips, row.get("geography_name")),
                **feature_values,
            }
        )
    return pd.DataFrame(rows, columns=["year", "state_fips", "geography_name", *feature_names])


def _normalize_state_fips(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = int(float(text))
    except ValueError:
        return text.zfill(2) if text.isdigit() else None
    return f"{number:02d}"


def _normalize_year(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _state_label(state_fips: str, geography_name: object) -> str:
    if isinstance(geography_name, str) and geography_name.strip():
        return geography_name.strip()
    return STATE_FIPS_TO_NAME.get(state_fips, f"State {state_fips}")
