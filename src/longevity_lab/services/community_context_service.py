"""Read-only community context and research-report summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.api.schemas import (
    CommunityCausalReportSummaryResponse,
    CommunityContextOverviewResponse,
    CommunityFeatureValueResponse,
    CommunityGeographyOptionResponse,
    CommunityGeographySummaryResponse,
    CommunityPlacesValidationRowResponse,
    CommunityPlacesValidationSummaryResponse,
)
from longevity_lab.artifacts.store import ArtifactBundle
from longevity_lab.config import Settings
from longevity_lab.pipeline.build_context_tables import (
    CONTEXT_FEATURE_COLUMNS,
    context_county_year_parquet,
    context_state_year_parquet,
    load_context_feature_config,
)
from longevity_lab.pipeline.build_places_tables import (
    PLACES_CONTEXT_MEASURES,
    places_county_year_parquet,
)
from longevity_lab.pipeline.download_places import PLACES_CONTEXT_CAVEAT
from longevity_lab.pipeline.validate_external_context import (
    EXTERNAL_VALIDATION_CAVEAT,
    places_external_validation_report_json_path,
)
from longevity_lab.services.context_lookup import STATE_FIPS_TO_NAME

COMMUNITY_CONTEXT_CAVEAT = (
    "Community context is background aggregate evidence. It does not directly change Explorer "
    "personal risk scores unless an active artifact explicitly declares state-year context."
)
COUNTY_CONTEXT_CAVEAT = (
    "County context is displayed for evidence and comparison only. Public BRFSS serving rows do "
    "not expose respondent county, so county values are not injected into person-level scoring."
)
CAUSAL_REPORT_CAVEAT = (
    "Causal workbench reports are exploratory observational analyses under stated assumptions. "
    "They are separate from predictive Explorer scenario deltas."
)

_STATE_KEY_COLUMNS = {"year", "state_fips", "geography_name"}
_COUNTY_KEY_COLUMNS = {"year", "state_fips", "county_fips", "geography_name"}
_PLACES_KEY_COLUMNS = {
    "release_year",
    "year",
    "state_fips",
    "state_abbr",
    "state_name",
    "county_fips",
    "county_name",
    "geography_name",
    "places_total_population",
    "places_total_pop_18plus",
    "places_estimate_year_min",
    "places_estimate_year_max",
}


class CommunityContextService:
    """Build community/context evidence summaries for the UI."""

    def __init__(self, *, settings: Settings, artifact_bundle: ArtifactBundle | None) -> None:
        """Store local roots and optional active artifact bundle."""
        self._settings = settings
        self._artifact_bundle = artifact_bundle
        self._repo_root = Path.cwd()
        self._context_labels = _context_feature_labels()
        self._places_labels = _places_feature_labels()

    def get_overview(
        self,
        *,
        year: int,
        places_year: int,
        state_fips: str | None = None,
        county_fips: str | None = None,
    ) -> CommunityContextOverviewResponse:
        """Return community context, PLACES validation, and causal report summaries."""
        state_frame, state_path = self._load_state_context(year=year)
        normalized_state = _normalize_optional_fips(state_fips, width=2)
        selected_state = self._selected_state_fips(state_frame, normalized_state)
        county_frame, county_path = self._read_year_frame(
            context_county_year_parquet(self._settings.data_dir),
            year_column="year",
            year=year,
        )
        normalized_county = _normalize_optional_fips(county_fips, width=5)
        selected_county = self._selected_county_fips(
            county_frame,
            state_fips=selected_state,
            county_fips=normalized_county,
        )
        places_frame, places_path = self._read_year_frame(
            places_county_year_parquet(self._settings.data_dir),
            year_column="release_year",
            year=places_year,
        )

        return CommunityContextOverviewResponse(
            year=year,
            places_year=places_year,
            state_context=self._state_summary(
                frame=state_frame,
                path=state_path,
                year=year,
                selected_state=selected_state,
            ),
            county_context=self._county_summary(
                frame=county_frame,
                path=county_path,
                year=year,
                selected_state=selected_state,
                selected_county=selected_county,
            ),
            places_context=self._places_summary(
                frame=places_frame,
                path=places_path,
                places_year=places_year,
                selected_state=selected_state,
                selected_county=selected_county,
            ),
            places_validation=self._places_validation(
                places_year=places_year,
                selected_state=selected_state,
                selected_county=selected_county,
            ),
            causal_reports=self._causal_reports(),
            caveat=COMMUNITY_CONTEXT_CAVEAT,
        )

    def _load_state_context(self, *, year: int) -> tuple[pd.DataFrame | None, Path]:
        artifact_frame, artifact_path = self._artifact_state_context(year=year)
        if artifact_frame is not None:
            return artifact_frame, artifact_path
        return self._read_year_frame(
            context_state_year_parquet(self._settings.data_dir),
            year_column="year",
            year=year,
        )

    def _artifact_state_context(self, *, year: int) -> tuple[pd.DataFrame | None, Path]:
        bundle = self._artifact_bundle
        if bundle is None or bundle.manifest.context_features is None:
            return None, context_state_year_parquet(self._settings.data_dir)
        lookup_path = (bundle.path / bundle.manifest.context_features.lookup_path).resolve()
        if not _path_inside(lookup_path, bundle.path.resolve()) or not lookup_path.exists():
            return None, lookup_path
        try:
            payload = json.loads(lookup_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None, lookup_path
        rows = payload.get("rows") if isinstance(payload, dict) else None
        feature_names = payload.get("feature_names") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not isinstance(feature_names, list):
            return None, lookup_path
        frame = pd.DataFrame(rows)
        if frame.empty or "year" not in frame.columns or "state_fips" not in frame.columns:
            return None, lookup_path
        frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
        frame = frame.loc[frame["year"] == year].copy()
        if frame.empty:
            return None, lookup_path
        frame["state_fips"] = frame["state_fips"].map(lambda value: _format_fips(value, 2))
        if "geography_name" not in frame.columns:
            frame["geography_name"] = frame["state_fips"].map(
                lambda value: STATE_FIPS_TO_NAME.get(str(value), f"State {value}")
            )
        return frame, lookup_path

    def _read_year_frame(
        self,
        path: Path,
        *,
        year_column: str,
        year: int,
    ) -> tuple[pd.DataFrame | None, Path]:
        if not path.exists():
            return None, path
        try:
            frame = pd.read_parquet(path)
        except Exception:
            return None, path
        if year_column not in frame.columns:
            return None, path
        frame = frame.copy()
        frame[year_column] = pd.to_numeric(frame[year_column], errors="coerce")
        filtered = frame.loc[frame[year_column] == year].copy()
        return (filtered if not filtered.empty else None), path

    def _selected_state_fips(self, frame: pd.DataFrame | None, requested: str | None) -> str | None:
        if frame is None or "state_fips" not in frame.columns:
            return requested
        states = sorted(
            str(value)
            for value in frame["state_fips"].map(lambda item: _format_fips(item, 2)).dropna()
        )
        if requested is not None and requested in states:
            return requested
        return states[0] if states else None

    def _selected_county_fips(
        self,
        frame: pd.DataFrame | None,
        *,
        state_fips: str | None,
        county_fips: str | None,
    ) -> str | None:
        if frame is None or "county_fips" not in frame.columns:
            return county_fips
        filtered = frame.copy()
        filtered["county_fips"] = filtered["county_fips"].map(lambda item: _format_fips(item, 5))
        if state_fips is not None and "state_fips" in filtered.columns:
            filtered["state_fips"] = filtered["state_fips"].map(lambda item: _format_fips(item, 2))
            filtered = filtered.loc[filtered["state_fips"] == state_fips]
        counties = sorted(str(value) for value in filtered["county_fips"].dropna())
        if county_fips is not None and county_fips in counties:
            return county_fips
        return counties[0] if counties else None

    def _state_summary(
        self,
        *,
        frame: pd.DataFrame | None,
        path: Path,
        year: int,
        selected_state: str | None,
    ) -> CommunityGeographySummaryResponse:
        if frame is None:
            return _missing_geography_summary(
                level="state",
                year=year,
                path=path,
                root=self._display_root(path),
                message="No state-year ACS/SVI context table is available in this runtime.",
                caveat=COMMUNITY_CONTEXT_CAVEAT,
            )
        working = frame.copy()
        working["state_fips"] = working["state_fips"].map(lambda item: _format_fips(item, 2))
        options = [
            CommunityGeographyOptionResponse(
                level="state",
                state_fips=str(row["state_fips"]),
                label=_state_label(str(row["state_fips"]), row.get("geography_name")),
                year=year,
                feature_count=_feature_count(row, excluded=_STATE_KEY_COLUMNS),
                selected=str(row["state_fips"]) == selected_state,
            )
            for _, row in working.sort_values("state_fips").iterrows()
        ]
        selected = working.loc[working["state_fips"] == selected_state]
        if selected.empty:
            selected = working.head(1)
        row = selected.iloc[0]
        return CommunityGeographySummaryResponse(
            level="state",
            available=True,
            label=_state_label(str(row["state_fips"]), row.get("geography_name")),
            state_fips=str(row["state_fips"]),
            year=year,
            source_path=_display_path(path, root=self._display_root(path)),
            message="State-year ACS/SVI context is available for comparison.",
            features=self._features_from_row(
                row,
                excluded=_STATE_KEY_COLUMNS,
                role="state_context",
                label_lookup=self._context_labels,
            ),
            options=options,
            caveat=COMMUNITY_CONTEXT_CAVEAT,
        )

    def _county_summary(
        self,
        *,
        frame: pd.DataFrame | None,
        path: Path,
        year: int,
        selected_state: str | None,
        selected_county: str | None,
    ) -> CommunityGeographySummaryResponse:
        if frame is None:
            return _missing_geography_summary(
                level="county",
                year=year,
                path=path,
                root=self._settings.data_dir,
                message="No county-year ACS/SVI context table is available in this runtime.",
                caveat=COUNTY_CONTEXT_CAVEAT,
            )
        working = frame.copy()
        working["state_fips"] = working["state_fips"].map(lambda item: _format_fips(item, 2))
        working["county_fips"] = working["county_fips"].map(lambda item: _format_fips(item, 5))
        if selected_state is not None:
            option_frame = working.loc[working["state_fips"] == selected_state].copy()
        else:
            option_frame = working
        options = [
            CommunityGeographyOptionResponse(
                level="county",
                state_fips=str(row["state_fips"]),
                county_fips=str(row["county_fips"]),
                label=str(row.get("geography_name") or row["county_fips"]),
                year=year,
                feature_count=_feature_count(row, excluded=_COUNTY_KEY_COLUMNS),
                selected=str(row["county_fips"]) == selected_county,
            )
            for _, row in option_frame.sort_values("county_fips").iterrows()
        ][:300]
        selected = working.loc[working["county_fips"] == selected_county]
        if selected.empty and not option_frame.empty:
            selected = option_frame.head(1)
        if selected.empty:
            return _missing_geography_summary(
                level="county",
                year=year,
                path=path,
                root=self._settings.data_dir,
                message="County context exists, but no matching county row was found.",
                caveat=COUNTY_CONTEXT_CAVEAT,
            )
        row = selected.iloc[0]
        return CommunityGeographySummaryResponse(
            level="county",
            available=True,
            label=str(row.get("geography_name") or row["county_fips"]),
            state_fips=str(row["state_fips"]),
            county_fips=str(row["county_fips"]),
            year=year,
            source_path=_display_path(path, root=self._settings.data_dir),
            message="County ACS/SVI context is available for background comparison.",
            features=self._features_from_row(
                row,
                excluded=_COUNTY_KEY_COLUMNS,
                role="county_context",
                label_lookup=self._context_labels,
            ),
            options=options,
            caveat=COUNTY_CONTEXT_CAVEAT,
        )

    def _places_summary(
        self,
        *,
        frame: pd.DataFrame | None,
        path: Path,
        places_year: int,
        selected_state: str | None,
        selected_county: str | None,
    ) -> CommunityGeographySummaryResponse:
        if frame is None:
            return _missing_geography_summary(
                level="county",
                year=places_year,
                path=path,
                root=self._settings.data_dir,
                message="No CDC PLACES county context table is available in this runtime.",
                caveat=PLACES_CONTEXT_CAVEAT,
            )
        working = frame.copy()
        working["state_fips"] = working["state_fips"].map(lambda item: _format_fips(item, 2))
        working["county_fips"] = working["county_fips"].map(lambda item: _format_fips(item, 5))
        if selected_county is not None:
            selected = working.loc[working["county_fips"] == selected_county]
        elif selected_state is not None:
            selected = working.loc[working["state_fips"] == selected_state].head(1)
        else:
            selected = working.head(1)
        if selected.empty:
            selected = working.head(1)
        row = selected.iloc[0]
        return CommunityGeographySummaryResponse(
            level="county",
            available=True,
            label=str(row.get("geography_name") or row["county_fips"]),
            state_fips=str(row["state_fips"]),
            county_fips=str(row["county_fips"]),
            year=places_year,
            source_path=_display_path(path, root=self._settings.data_dir),
            message="CDC PLACES modeled county context is available for comparison.",
            features=self._features_from_row(
                row,
                excluded=_PLACES_KEY_COLUMNS,
                role="places_context",
                label_lookup=self._places_labels,
            ),
            options=[],
            caveat=PLACES_CONTEXT_CAVEAT,
        )

    def _features_from_row(
        self,
        row: pd.Series,
        *,
        excluded: set[str],
        role: Literal["state_context", "county_context", "places_context"],
        label_lookup: dict[str, tuple[str, str | None]],
    ) -> list[CommunityFeatureValueResponse]:
        features: list[CommunityFeatureValueResponse] = []
        for column in row.index:
            if column in excluded or str(column).endswith("_moe_available"):
                continue
            value = row[column]
            if _is_missing(value):
                continue
            label, units = label_lookup.get(str(column), (_labelize(str(column)), None))
            features.append(
                CommunityFeatureValueResponse(
                    feature=str(column),
                    label=label,
                    value=_json_scalar(value),
                    formatted_value=_format_value(value, units=units, feature=str(column)),
                    units=units,
                    role=role,
                    caveat=_feature_caveat(role),
                )
            )
        return features[:24]

    def _places_validation(
        self,
        *,
        places_year: int,
        selected_state: str | None,
        selected_county: str | None,
    ) -> CommunityPlacesValidationSummaryResponse:
        path = places_external_validation_report_json_path(
            self._settings.data_dir,
            places_year=places_year,
        )
        if not path.exists():
            return CommunityPlacesValidationSummaryResponse(
                available=False,
                places_release_year=places_year,
                row_count=0,
                caveat=EXTERNAL_VALIDATION_CAVEAT,
                message="No local PLACES external-validation report is available.",
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return CommunityPlacesValidationSummaryResponse(
                available=False,
                report_path=_display_path(path, root=self._settings.data_dir),
                places_release_year=places_year,
                row_count=0,
                caveat=EXTERNAL_VALIDATION_CAVEAT,
                message="The PLACES validation report could not be parsed.",
            )
        raw_rows = payload.get("rows") if isinstance(payload, dict) else None
        if not isinstance(raw_rows, list):
            raw_rows = []
        rows = [
            _validation_row(row)
            for row in raw_rows
            if isinstance(row, dict)
            and _row_matches_geography(
                row,
                state_fips=selected_state,
                county_fips=selected_county,
            )
        ]
        if not rows and raw_rows:
            rows = [_validation_row(row) for row in raw_rows[:12] if isinstance(row, dict)]
        summary = payload.get("summary") if isinstance(payload, dict) else {}
        conditions = summary.get("conditions_compared") if isinstance(summary, dict) else []
        compared_conditions = (
            [str(item) for item in conditions] if isinstance(conditions, list) else []
        )
        return CommunityPlacesValidationSummaryResponse(
            available=True,
            report_path=_display_path(path, root=self._settings.data_dir),
            places_release_year=places_year,
            row_count=len(raw_rows),
            conditions_compared=compared_conditions,
            rows=rows[:12],
            caveat=str(payload.get("caveat") or EXTERNAL_VALIDATION_CAVEAT)
            if isinstance(payload, dict)
            else EXTERNAL_VALIDATION_CAVEAT,
            message="PLACES aggregate validation report is available.",
        )

    def _causal_reports(self) -> list[CommunityCausalReportSummaryResponse]:
        root = self._settings.data_dir / "processed" / "reports" / "causal"
        if not root.exists():
            return []
        reports: list[CommunityCausalReportSummaryResponse] = []
        for path in sorted(root.glob("*/*_report.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            markdown = path.with_suffix(".md")
            reports.append(
                CommunityCausalReportSummaryResponse(
                    question_id=str(payload.get("question_id") or path.parent.name),
                    title=str(payload.get("title") or _labelize(path.parent.name)),
                    status=str(payload.get("status") or "unknown"),
                    report_path=_display_path(path, root=self._settings.data_dir),
                    markdown_path=(
                        _display_path(markdown, root=self._settings.data_dir)
                        if markdown.exists()
                        else None
                    ),
                    rows=_nested_int(payload, "analysis_dataset", "rows"),
                    treatment=_nested_str(payload, "question", "treatment", "column"),
                    outcome=_nested_str(payload, "question", "outcome", "column"),
                    estimand=_nested_str(payload, "question", "estimand"),
                    estimate_method=_nested_str(payload, "estimate", "method"),
                    risk_difference=_nested_float(payload, "estimate", "risk_difference"),
                    diagnostic_status=_nested_str(
                        payload,
                        "diagnostics",
                        "diagnostic_gate",
                        "status",
                    ),
                    heterogeneity_status=_nested_str(payload, "heterogeneity", "status"),
                    caveat=CAUSAL_REPORT_CAVEAT,
                )
            )
        return reports

    def _display_root(self, path: Path) -> Path:
        if self._artifact_bundle is not None and _path_inside(
            path.resolve(),
            self._artifact_bundle.path.resolve(),
        ):
            return self._repo_root
        return self._settings.data_dir


def _missing_geography_summary(
    *,
    level: Literal["state", "county"],
    year: int,
    path: Path,
    root: Path,
    message: str,
    caveat: str,
) -> CommunityGeographySummaryResponse:
    return CommunityGeographySummaryResponse(
        level=level,
        available=False,
        year=year,
        source_path=_display_path(path, root=root),
        message=message,
        caveat=caveat,
    )


def _context_feature_labels() -> dict[str, tuple[str, str | None]]:
    config = load_context_feature_config()
    labels: dict[str, tuple[str, str | None]] = {}
    for acs_feature in config.acs_features:
        labels[acs_feature.name] = (acs_feature.display_name, acs_feature.units)
    for svi_feature in config.svi_features:
        labels[svi_feature.name] = (svi_feature.display_name, "percentile")
    for column in CONTEXT_FEATURE_COLUMNS:
        labels.setdefault(column, (_labelize(column), None))
    return labels


def _places_feature_labels() -> dict[str, tuple[str, str | None]]:
    labels: dict[str, tuple[str, str | None]] = {
        "places_total_population": ("Total population", "people"),
        "places_total_pop_18plus": ("Adult population", "people"),
    }
    for measure in PLACES_CONTEXT_MEASURES:
        base = f"places_{measure.feature_prefix}_crude_prevalence"
        labels[base] = (measure.display_name, "percent")
        labels[f"{base}_low"] = (f"{measure.display_name} low CI", "percent")
        labels[f"{base}_high"] = (f"{measure.display_name} high CI", "percent")
        labels[f"places_{measure.feature_prefix}_estimate_year"] = (
            f"{measure.display_name} estimate year",
            None,
        )
    return labels


def _display_path(path: Path, *, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            return path.name


def _format_fips(value: object, width: int) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = int(float(text))
    except ValueError:
        return text.zfill(width) if text.isdigit() else None
    return f"{number:0{width}d}"


def _normalize_optional_fips(value: str | None, *, width: int) -> str | None:
    if value is None:
        return None
    return _format_fips(value, width)


def _state_label(state_fips: str, geography_name: object) -> str:
    if isinstance(geography_name, str) and geography_name.strip():
        return geography_name.strip()
    return STATE_FIPS_TO_NAME.get(state_fips, f"State {state_fips}")


def _feature_count(row: pd.Series, *, excluded: set[str]) -> int:
    return sum(
        1
        for column, value in row.items()
        if column not in excluded
        and not str(column).endswith("_moe_available")
        and not _is_missing(value)
    )


def _json_scalar(value: object) -> float | int | str | bool | None:
    if _is_missing(value):
        return None
    if hasattr(value, "item"):
        return cast(float | int | str | bool | None, value.item())
    if isinstance(value, float | int | str | bool):
        return value
    return str(value)


def _format_value(value: object, *, units: str | None, feature: str) -> str:
    scalar = _json_scalar(value)
    if scalar is None:
        return "Unavailable"
    if isinstance(scalar, bool):
        return "Yes" if scalar else "No"
    if isinstance(scalar, int):
        if units == "people" or feature.endswith("_population"):
            return f"{scalar:,}"
        return str(scalar)
    if isinstance(scalar, float):
        if units == "percent":
            return f"{scalar:.1f}%"
        if units == "percentile":
            return f"{scalar:.2f}"
        if abs(scalar) >= 1000:
            return f"{scalar:,.0f}"
        return f"{scalar:.2f}"
    return scalar


def _labelize(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _feature_caveat(role: str) -> str:
    if role == "places_context":
        return PLACES_CONTEXT_CAVEAT
    if role == "county_context":
        return COUNTY_CONTEXT_CAVEAT
    return COMMUNITY_CONTEXT_CAVEAT


def _validation_row(row: dict[str, Any]) -> CommunityPlacesValidationRowResponse:
    geography_level = str(row.get("geography_level") or "state")
    if geography_level not in {"state", "county", "national"}:
        geography_level = "state"
    return CommunityPlacesValidationRowResponse(
        condition_id=str(row.get("condition_id") or ""),
        geography_level=cast(Literal["state", "county", "national"], geography_level),
        geography_name=_optional_str(row.get("geography_name")),
        state_fips=_normalize_optional_fips(_optional_str(row.get("state_fips")), width=2),
        county_fips=_normalize_optional_fips(_optional_str(row.get("county_fips")), width=5),
        model_mean_predicted_probability=_optional_float(
            row.get("model_mean_predicted_probability")
        ),
        places_crude_prevalence_probability=_optional_float(
            row.get("places_crude_prevalence_probability")
        ),
        absolute_difference=_optional_float(row.get("absolute_difference")),
        comparison_direction=_optional_str(row.get("comparison_direction")),
        places_reference_kind=_optional_str(row.get("places_reference_kind")),
    )


def _row_matches_geography(
    row: dict[str, Any],
    *,
    state_fips: str | None,
    county_fips: str | None,
) -> bool:
    if county_fips is not None:
        row_county = _normalize_optional_fips(_optional_str(row.get("county_fips")), width=5)
        if row_county == county_fips:
            return True
    if state_fips is not None:
        row_state = _normalize_optional_fips(_optional_str(row.get("state_fips")), width=2)
        return row_state == state_fips
    return True


def _optional_float(value: object) -> float | None:
    if _is_missing(value):
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if _is_missing(value):
        return None
    return str(value)


def _nested_value(payload: dict[str, Any], *keys: str) -> object:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _nested_str(payload: dict[str, Any], *keys: str) -> str | None:
    return _optional_str(_nested_value(payload, *keys))


def _nested_float(payload: dict[str, Any], *keys: str) -> float | None:
    return _optional_float(_nested_value(payload, *keys))


def _nested_int(payload: dict[str, Any], *keys: str) -> int | None:
    value = _nested_value(payload, *keys)
    if _is_missing(value):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _path_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, list | tuple | dict | set):
        return False
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(result, bool):
        return result
    if hasattr(result, "item"):
        try:
            return bool(result.item())
        except (TypeError, ValueError):
            return False
    return False
