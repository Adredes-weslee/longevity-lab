"""Build ACS/SVI geography context tables."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.pipeline.common import (
    FileProvenance,
    add_common_pipeline_args,
    collect_file_provenance,
    parse_years_from_args,
    require_columns,
    write_provenance_json,
)
from longevity_lab.pipeline.download_acs import (
    ACS_QUERY_VARIABLES,
    ACS_SOURCE_ID,
    acs_api_urls,
    acs_raw_json_path,
)
from longevity_lab.pipeline.download_svi import (
    SVI_SOURCE_ID,
    svi_county_csv_path,
    svi_county_csv_url,
)
from longevity_lab.pipeline.provenance import registry_provenance_extra
from longevity_lab.pipeline.sources import load_data_source_registry

SCENARIO_EDITABLE_COLUMNS: frozenset[str] = frozenset(
    {
        "age",
        "bmi",
        "smoker",
        "alcohol_servings_per_week",
        "exercise_minutes_per_week",
        "annual_aqi",
    }
)
CONTEXT_OUTPUT_DIR = "context"
COUNTY_OUTPUT_NAME = "context_county_year.parquet"
STATE_OUTPUT_NAME = "context_state_year.parquet"


@dataclass(frozen=True, slots=True)
class AcsFeature:
    """Configuration for one derived ACS context feature."""

    name: str
    display_name: str
    kind: str
    estimate_variables: tuple[str, ...]
    moe_variables: tuple[str, ...]
    numerator_variables: tuple[str, ...] = ()
    denominator_variable: str | None = None
    units: str | None = None


@dataclass(frozen=True, slots=True)
class SviFeature:
    """Configuration for one selected SVI column."""

    name: str
    display_name: str
    source_column: str


@dataclass(frozen=True, slots=True)
class ContextFeatureConfig:
    """Parsed context feature configuration."""

    schema_version: int
    description: str
    acs_features: tuple[AcsFeature, ...]
    svi_features: tuple[SviFeature, ...]
    svi_missing_sentinel: float


def default_context_config_path() -> Path:
    """Return the repo-local context feature config path."""
    return Path(__file__).resolve().parents[3] / "conf" / "context_features.yaml"


def _as_tuple(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    """Return a tuple of strings from a config list field."""
    values = payload.get(key, [])
    if not isinstance(values, list):
        raise ValueError(f"Expected {key} to be a list.")
    return tuple(str(value) for value in values)


def load_context_feature_config(path: Path | None = None) -> ContextFeatureConfig:
    """Load the JSON-compatible context feature configuration."""
    config_path = path or default_context_config_path()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    acs_payload = payload["acs"]["features"]
    svi_payload = payload["svi"]["features"]

    acs_features = tuple(
        AcsFeature(
            name=str(item["name"]),
            display_name=str(item["display_name"]),
            kind=str(item["kind"]),
            estimate_variables=_as_tuple(item, "estimate_variables"),
            numerator_variables=_as_tuple(item, "numerator_variables"),
            denominator_variable=(
                str(item["denominator_variable"]) if "denominator_variable" in item else None
            ),
            moe_variables=_as_tuple(item, "moe_variables"),
            units=str(item["units"]) if "units" in item else None,
        )
        for item in acs_payload
    )
    svi_features = tuple(
        SviFeature(
            name=str(item["name"]),
            display_name=str(item["display_name"]),
            source_column=str(item["source_column"]),
        )
        for item in svi_payload
    )
    return ContextFeatureConfig(
        schema_version=int(payload["schema_version"]),
        description=str(payload.get("description", "")),
        acs_features=acs_features,
        svi_features=svi_features,
        svi_missing_sentinel=float(payload["svi"].get("missing_sentinel", -999)),
    )


_DEFAULT_CONFIG = load_context_feature_config()
CONTEXT_FEATURE_COLUMNS: tuple[str, ...] = tuple(
    [feature.name for feature in _DEFAULT_CONFIG.acs_features]
    + [feature.name for feature in _DEFAULT_CONFIG.svi_features]
)
ACS_MOE_AVAILABLE_COLUMNS: tuple[str, ...] = tuple(
    f"{feature.name}_moe_available" for feature in _DEFAULT_CONFIG.acs_features
)


def context_processed_dir(base_dir: Path) -> Path:
    """Return the processed context output directory."""
    return base_dir / "processed" / CONTEXT_OUTPUT_DIR


def context_county_year_parquet(base_dir: Path) -> Path:
    """Return the processed county-year context parquet path."""
    return context_processed_dir(base_dir) / COUNTY_OUTPUT_NAME


def context_state_year_parquet(base_dir: Path) -> Path:
    """Return the processed state-year context parquet path."""
    return context_processed_dir(base_dir) / STATE_OUTPUT_NAME


def provenance_context_tables(base_dir: Path, years: Sequence[int]) -> Path:
    """Return the context-table provenance JSON path for a set of years."""
    years_str = "_".join(str(year) for year in years)
    return base_dir / "processed" / "provenance" / f"context_tables_{years_str}.json"


def _read_census_json(path: Path) -> pd.DataFrame:
    """Read a Census API JSON response into a DataFrame."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Invalid ACS JSON payload: {path}")
    headers = [str(item) for item in payload[0]]
    rows = payload[1:]
    return pd.DataFrame(rows, columns=headers)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric ACS/SVI column with Census missing sentinels coerced to null."""
    series = pd.to_numeric(frame[column], errors="coerce")
    return series.mask(series < 0)


def _sum_numeric(frame: pd.DataFrame, columns: Sequence[str]) -> pd.Series:
    """Return a row-wise sum for numeric columns, preserving null when all values are null."""
    values = [_numeric(frame, column) for column in columns]
    combined = pd.concat(values, axis=1)
    return combined.sum(axis=1, min_count=1)


def _percent(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Return numerator / denominator as a percentage with invalid denominators as null."""
    valid_denominator = denominator.where(denominator > 0)
    return (numerator / valid_denominator) * 100.0


def _moe_available(frame: pd.DataFrame, variables: Sequence[str]) -> pd.Series:
    """Return whether all MOE variables are present and non-null for each row."""
    missing = [variable for variable in variables if variable not in frame.columns]
    if missing:
        return pd.Series([False] * len(frame), index=frame.index, dtype=object)
    availability = pd.Series([True] * len(frame), index=frame.index)
    for variable in variables:
        availability = availability & _numeric(frame, variable).notna()
    return availability.map(bool).astype(object)


def _derive_acs_features(
    frame: pd.DataFrame,
    *,
    config: ContextFeatureConfig,
) -> pd.DataFrame:
    """Derive curated ACS features and MOE-availability flags."""
    required = ["NAME", "state", *ACS_QUERY_VARIABLES]
    require_columns(actual=frame.columns, required=required, context="ACS context")
    out = pd.DataFrame(index=frame.index)
    out["geography_name"] = frame["NAME"].astype(str)
    out["state_fips"] = frame["state"].astype(str).str.zfill(2)

    for feature in config.acs_features:
        if feature.kind == "count":
            if len(feature.estimate_variables) != 1:
                raise ValueError(f"Count feature must have one estimate variable: {feature.name}")
            out[feature.name] = _numeric(frame, feature.estimate_variables[0]).astype("Int64")
        elif feature.kind == "estimate":
            if len(feature.estimate_variables) != 1:
                raise ValueError(f"Estimate feature must have one variable: {feature.name}")
            out[feature.name] = _numeric(frame, feature.estimate_variables[0])
        elif feature.kind == "percent_ratio":
            if feature.denominator_variable is None:
                raise ValueError(f"Ratio feature missing denominator: {feature.name}")
            numerator = _sum_numeric(frame, feature.numerator_variables)
            denominator = _numeric(frame, feature.denominator_variable)
            out[feature.name] = _percent(numerator, denominator)
        else:
            raise ValueError(f"Unsupported ACS feature kind for {feature.name}: {feature.kind}")
        out[f"{feature.name}_moe_available"] = _moe_available(frame, feature.moe_variables)

    return out


def _county_fips_from_frame(frame: pd.DataFrame) -> pd.Series:
    """Return a zero-padded county FIPS Series from an SVI frame."""
    if "STCNTY" in frame.columns:
        return frame["STCNTY"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    if "FIPS" in frame.columns:
        return frame["FIPS"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    raise ValueError("Missing SVI county FIPS column: expected STCNTY or FIPS.")


def _read_svi_county_csv(
    path: Path,
    *,
    year: int,
    config: ContextFeatureConfig,
) -> pd.DataFrame:
    """Read and normalize selected SVI county columns."""
    frame = pd.read_csv(path, dtype={"ST": "string", "STCNTY": "string", "FIPS": "string"})
    required = [feature.source_column for feature in config.svi_features]
    require_columns(actual=frame.columns, required=required, context=f"SVI county {year}")

    out = pd.DataFrame(index=frame.index)
    if "ST" in frame.columns:
        out["state_fips"] = (
            frame["ST"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(2)
        )
    else:
        out["state_fips"] = _county_fips_from_frame(frame).str.slice(0, 2)
    out["county_fips"] = _county_fips_from_frame(frame)
    out["year"] = int(year)

    for feature in config.svi_features:
        values = pd.to_numeric(frame[feature.source_column], errors="coerce")
        values = values.mask(values == config.svi_missing_sentinel)
        out[feature.name] = values
    return out


def build_county_context_table(
    *,
    acs_json_path: Path,
    svi_csv_path: Path,
    year: int,
    config: ContextFeatureConfig | None = None,
) -> pd.DataFrame:
    """Build one county-year context table from raw ACS and SVI inputs."""
    feature_config = config or _DEFAULT_CONFIG
    acs = _read_census_json(acs_json_path)
    require_columns(actual=acs.columns, required=["county"], context=f"ACS county {year}")
    out = _derive_acs_features(acs, config=feature_config)
    out["county_fips"] = out["state_fips"] + acs["county"].astype(str).str.zfill(3)
    out["year"] = int(year)

    svi = _read_svi_county_csv(svi_csv_path, year=year, config=feature_config)
    out = out.merge(
        svi,
        on=["year", "state_fips", "county_fips"],
        how="left",
        validate="one_to_one",
    )

    ordered = [
        "year",
        "state_fips",
        "county_fips",
        "geography_name",
        *CONTEXT_FEATURE_COLUMNS,
        *ACS_MOE_AVAILABLE_COLUMNS,
    ]
    return (
        out.loc[:, ordered]
        .sort_values(["year", "state_fips", "county_fips"])
        .reset_index(drop=True)
    )


def _weighted_mean(group: pd.DataFrame, value_column: str, weight_column: str) -> float | None:
    """Return a weighted mean, ignoring null values and non-positive weights."""
    values = pd.to_numeric(group[value_column], errors="coerce")
    weights = pd.to_numeric(group[weight_column], errors="coerce")
    valid = values.notna() & weights.notna() & (weights > 0)
    if not bool(valid.any()):
        return None
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def build_state_context_table(
    *,
    acs_json_path: Path,
    county_context: pd.DataFrame,
    year: int,
    config: ContextFeatureConfig | None = None,
) -> pd.DataFrame:
    """Build one state-year context table from state ACS and county SVI context."""
    feature_config = config or _DEFAULT_CONFIG
    acs = _read_census_json(acs_json_path)
    out = _derive_acs_features(acs, config=feature_config)
    out["year"] = int(year)

    svi_columns = [feature.name for feature in feature_config.svi_features]
    require_columns(
        actual=county_context.columns,
        required=["year", "state_fips", "acs_total_population", *svi_columns],
        context="county context for state aggregation",
    )
    rows: list[dict[str, Any]] = []
    for (state_fips, group_year), group in county_context.groupby(["state_fips", "year"]):
        row: dict[str, Any] = {"state_fips": str(state_fips), "year": int(group_year)}
        for column in svi_columns:
            row[column] = _weighted_mean(group, column, "acs_total_population")
        rows.append(row)
    svi_state = pd.DataFrame(rows)
    if svi_state.empty:
        for column in svi_columns:
            out[column] = pd.NA
    else:
        out = out.merge(svi_state, on=["year", "state_fips"], how="left", validate="one_to_one")

    ordered = [
        "year",
        "state_fips",
        "geography_name",
        *CONTEXT_FEATURE_COLUMNS,
        *ACS_MOE_AVAILABLE_COLUMNS,
    ]
    return out.loc[:, ordered].sort_values(["year", "state_fips"]).reset_index(drop=True)


def _years_present_in_output(path: Path) -> set[int] | None:
    """Return years present in a parquet output, or None if unreadable."""
    try:
        existing = pd.read_parquet(path, columns=["year"])
    except Exception:
        return None
    if "year" not in existing.columns:
        return None
    years = pd.to_numeric(existing["year"], errors="coerce")
    return {int(value) for value in years.dropna().unique().tolist()}


def _outputs_cover_years(
    *,
    base_dir: Path,
    years: Sequence[int],
) -> bool:
    """Return whether both processed context outputs contain all requested years."""
    required = set(years)
    county_years = _years_present_in_output(context_county_year_parquet(base_dir))
    state_years = _years_present_in_output(context_state_year_parquet(base_dir))
    return (
        county_years is not None
        and state_years is not None
        and required.issubset(county_years)
        and required.issubset(state_years)
    )


def _context_source_urls(years: Sequence[int]) -> list[str]:
    """Return all ACS/SVI URLs used to build the context tables."""
    urls: list[str] = []
    for year in years:
        urls.extend(acs_api_urls(year=year, geography="county"))
        urls.extend(acs_api_urls(year=year, geography="state"))
        urls.append(svi_county_csv_url(year))
    return urls


def _context_source_registry_extra(years: Sequence[int]) -> dict[str, Any]:
    """Return registry metadata for all raw sources used by context tables."""
    registry = load_data_source_registry()
    return {
        "source_registry_by_year": {
            str(year): registry_provenance_extra(
                registry=registry,
                source_ids=[ACS_SOURCE_ID, SVI_SOURCE_ID],
                year=year,
            )["source_registry"]
            for year in years
        }
    }


def build_context_tables(
    *,
    base_dir: Path,
    years: list[int],
    force: bool,
    dry_run: bool,
    config: ContextFeatureConfig | None = None,
) -> None:
    """Build processed county-year and state-year context tables for requested years."""
    feature_config = config or _DEFAULT_CONFIG
    county_output = context_county_year_parquet(base_dir)
    state_output = context_state_year_parquet(base_dir)

    if not force and county_output.exists() and state_output.exists():
        if _outputs_cover_years(base_dir=base_dir, years=years):
            print(f"Skip build (exists): {county_output}")
            print(f"Skip build (exists): {state_output}")
            return
        print("Rebuild context tables (existing output missing requested years).")

    county_tables: list[pd.DataFrame] = []
    state_tables: list[pd.DataFrame] = []
    for year in years:
        acs_county_path = acs_raw_json_path(base_dir, year=year, geography="county")
        acs_state_path = acs_raw_json_path(base_dir, year=year, geography="state")
        svi_path = svi_county_csv_path(base_dir, year=year)
        for input_path in [acs_county_path, acs_state_path, svi_path]:
            if not input_path.exists():
                raise FileNotFoundError(
                    f"Missing context input for {year}: {input_path}. "
                    "Run download_acs and download_svi first."
                )

        county = build_county_context_table(
            acs_json_path=acs_county_path,
            svi_csv_path=svi_path,
            year=year,
            config=feature_config,
        )
        state = build_state_context_table(
            acs_json_path=acs_state_path,
            county_context=county,
            year=year,
            config=feature_config,
        )
        county_tables.append(county)
        state_tables.append(state)

    combined_county = pd.concat(county_tables, ignore_index=True).sort_values(
        ["year", "state_fips", "county_fips"]
    )
    combined_state = pd.concat(state_tables, ignore_index=True).sort_values(["year", "state_fips"])

    county_duplicates = combined_county.duplicated(subset=["year", "county_fips"]).sum()
    state_duplicates = combined_state.duplicated(subset=["year", "state_fips"]).sum()
    if int(county_duplicates) != 0:
        raise ValueError("Context county-year output has duplicate (year, county_fips) keys.")
    if int(state_duplicates) != 0:
        raise ValueError("Context state-year output has duplicate (year, state_fips) keys.")

    print(f"County rows written: {len(combined_county):,}")
    print(f"State rows written: {len(combined_state):,}")

    if dry_run:
        print(f"DRY RUN: would write parquet -> {county_output}")
        print(f"DRY RUN: would write parquet -> {state_output}")
    else:
        county_output.parent.mkdir(parents=True, exist_ok=True)
        combined_county.to_parquet(county_output, index=False)
        combined_state.to_parquet(state_output, index=False)

    files: list[FileProvenance] = []
    for year in years:
        for input_path in [
            acs_raw_json_path(base_dir, year=year, geography="county"),
            acs_raw_json_path(base_dir, year=year, geography="state"),
            svi_county_csv_path(base_dir, year=year),
        ]:
            if input_path.exists():
                files.append(collect_file_provenance(input_path, root=base_dir))
    for output_path in [county_output, state_output]:
        if output_path.exists():
            files.append(collect_file_provenance(output_path, root=base_dir))

    write_provenance_json(
        provenance_context_tables(base_dir, years),
        dataset_name="context_tables",
        dataset_version="_".join(str(year) for year in years),
        sources=_context_source_urls(years),
        files=files,
        extra={
            **_context_source_registry_extra(years),
            "years": list(years),
            "context_feature_schema_version": feature_config.schema_version,
            "county_rows": len(combined_county),
            "state_rows": len(combined_state),
            "context_feature_columns": list(CONTEXT_FEATURE_COLUMNS),
            "acs_moe_available_columns": list(ACS_MOE_AVAILABLE_COLUMNS),
            "scenario_editable_columns_excluded": sorted(SCENARIO_EDITABLE_COLUMNS),
            "state_svi_aggregation": (
                "population-weighted mean of county SVI percentile fields using "
                "acs_total_population"
            ),
        },
        dry_run=dry_run,
    )


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for building ACS/SVI context tables."""
    parser = argparse.ArgumentParser(
        description="Build ACS/SVI context state-year/county-year tables."
    )
    add_common_pipeline_args(parser)
    args = parser.parse_args(argv)
    build_context_tables(
        base_dir=Path(args.base_dir),
        years=parse_years_from_args(args),
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
