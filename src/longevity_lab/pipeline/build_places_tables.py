"""Build CDC PLACES county context tables."""

from __future__ import annotations

import argparse
import re
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
from longevity_lab.pipeline.download_places import (
    PLACES_CONTEXT_CAVEAT,
    PLACES_SOURCE_ID,
    places_county_csv_path,
    places_county_csv_url,
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
PLACES_OUTPUT_DIR = "places"
PLACES_COUNTY_OUTPUT_NAME = "places_county_year.parquet"


@dataclass(frozen=True, slots=True)
class PlacesMeasure:
    """Configuration for one selected PLACES county measure."""

    measure_id: str
    feature_prefix: str
    display_name: str
    role: str


PLACES_CONDITION_MEASURES: dict[str, PlacesMeasure] = {
    "heart_disease": PlacesMeasure(
        measure_id="CHD",
        feature_prefix="coronary_heart_disease",
        display_name="Coronary heart disease among adults",
        role="modeled_condition_context",
    ),
    "chronic_lung_disease": PlacesMeasure(
        measure_id="COPD",
        feature_prefix="chronic_obstructive_pulmonary_disease",
        display_name="Chronic obstructive pulmonary disease among adults",
        role="modeled_condition_context",
    ),
    "stroke": PlacesMeasure(
        measure_id="STROKE",
        feature_prefix="stroke",
        display_name="Stroke among adults",
        role="modeled_condition_context",
    ),
    "depression": PlacesMeasure(
        measure_id="DEPRESSION",
        feature_prefix="depression",
        display_name="Depression among adults",
        role="modeled_condition_context",
    ),
    "diabetes": PlacesMeasure(
        measure_id="DIABETES",
        feature_prefix="diabetes",
        display_name="Diagnosed diabetes among adults",
        role="modeled_condition_context",
    ),
}
PLACES_BEHAVIOR_MEASURES: tuple[PlacesMeasure, ...] = (
    PlacesMeasure(
        measure_id="CSMOKING",
        feature_prefix="current_smoking",
        display_name="Current cigarette smoking among adults",
        role="behavior_context",
    ),
    PlacesMeasure(
        measure_id="BINGE",
        feature_prefix="binge_drinking",
        display_name="Binge drinking among adults",
        role="behavior_context",
    ),
    PlacesMeasure(
        measure_id="LPA",
        feature_prefix="no_leisure_time_physical_activity",
        display_name="No leisure-time physical activity among adults",
        role="behavior_context",
    ),
    PlacesMeasure(
        measure_id="OBESITY",
        feature_prefix="obesity",
        display_name="Obesity among adults",
        role="behavior_context",
    ),
    PlacesMeasure(
        measure_id="SLEEP",
        feature_prefix="short_sleep_duration",
        display_name="Short sleep duration among adults",
        role="behavior_context",
    ),
)
PLACES_CONTEXT_MEASURES: tuple[PlacesMeasure, ...] = (
    *PLACES_CONDITION_MEASURES.values(),
    *PLACES_BEHAVIOR_MEASURES,
)
PLACES_MEASURE_IDS: tuple[str, ...] = tuple(
    measure.measure_id for measure in PLACES_CONTEXT_MEASURES
)
PLACES_VALUE_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("data_value", ""),
    ("low_confidence_limit", "_low"),
    ("high_confidence_limit", "_high"),
)
PLACES_MEASURE_COLUMNS: tuple[str, ...] = tuple(
    column
    for measure in PLACES_CONTEXT_MEASURES
    for column in (
        f"places_{measure.feature_prefix}_estimate_year",
        *(
            f"places_{measure.feature_prefix}_crude_prevalence{suffix}"
            for _, suffix in PLACES_VALUE_SUFFIXES
        ),
    )
)

_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "year": ("year",),
    "state_abbr": ("stateabbr", "state_abbr"),
    "state_name": ("statedesc", "state_desc", "state"),
    "county_name": ("locationname", "location_name", "county"),
    "data_value": ("data_value", "datavalue"),
    "data_value_type": ("data_value_type", "datavaluetype"),
    "low_confidence_limit": ("low_confidence_limit", "lowconfidencelimit"),
    "high_confidence_limit": ("high_confidence_limit", "highconfidencelimit"),
    "totalpopulation": ("totalpopulation", "total_population"),
    "totalpop18plus": ("totalpop18plus", "total_pop18plus", "total_pop_18plus"),
    "locationid": ("locationid", "location_id", "fips", "county_fips"),
    "measureid": ("measureid", "measure_id"),
    "datavaluetypeid": ("datavaluetypeid", "data_value_type_id"),
    "measure": ("measure",),
    "category": ("category",),
}
_REQUIRED_COLUMNS = [
    "year",
    "state_abbr",
    "state_name",
    "county_name",
    "data_value",
    "low_confidence_limit",
    "high_confidence_limit",
    "totalpopulation",
    "totalpop18plus",
    "locationid",
    "measureid",
    "datavaluetypeid",
]
_BASE_COLUMNS = [
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
]


def places_processed_dir(base_dir: Path) -> Path:
    """Return the processed PLACES output directory."""
    return base_dir / "processed" / PLACES_OUTPUT_DIR


def places_county_year_parquet(base_dir: Path) -> Path:
    """Return the processed PLACES county-year parquet path."""
    return places_processed_dir(base_dir) / PLACES_COUNTY_OUTPUT_NAME


def provenance_places_county_year(base_dir: Path, years: Sequence[int]) -> Path:
    """Return the PLACES county table provenance path for release years."""
    years_str = "_".join(str(year) for year in years)
    return base_dir / "processed" / "provenance" / f"places_county_year_{years_str}.json"


def _normalize_column_name(name: str) -> str:
    """Return a punctuation-insensitive lowercase column key."""
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def _rename_places_columns(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = {_normalize_column_name(str(column)): str(column) for column in frame.columns}
    rename_map: dict[str, str] = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            actual = normalized.get(_normalize_column_name(alias))
            if actual is not None:
                rename_map[actual] = canonical
                break
    return frame.rename(columns=rename_map)


def _format_fips(value: object, width: int) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = int(float(text))
    except ValueError:
        return text.zfill(width) if text.isdigit() else None
    return f"{number:0{width}d}"


def _geography_name(county_name: object, state_name: object) -> str:
    county = str(county_name).strip()
    state = str(state_name).strip()
    if county.casefold().endswith(" county"):
        return f"{county}, {state}"
    return f"{county} County, {state}"


def _read_places_csv(csv_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(
        csv_path,
        dtype={"locationid": "string", "LocationID": "string"},
        low_memory=False,
    )
    frame = _rename_places_columns(frame)
    require_columns(actual=frame.columns, required=_REQUIRED_COLUMNS, context="CDC PLACES county")
    return frame


def _selected_crude_rows(frame: pd.DataFrame, *, release_year: int) -> pd.DataFrame:
    out = frame.copy()
    out["measureid"] = out["measureid"].astype(str).str.upper()
    out["datavaluetypeid"] = out["datavaluetypeid"].astype(str)
    is_crude = out["datavaluetypeid"].str.casefold().eq("crdprv")
    if "data_value_type" in out.columns:
        is_crude = is_crude | out["data_value_type"].astype(str).str.contains(
            "crude prevalence",
            case=False,
            na=False,
        )
    out = out.loc[is_crude & out["measureid"].isin(PLACES_MEASURE_IDS)].copy()
    if out.empty:
        raise ValueError("No selected CDC PLACES crude prevalence rows were found.")

    out["release_year"] = int(release_year)
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out["county_fips"] = out["locationid"].map(lambda value: _format_fips(value, 5))
    out = out.loc[out["county_fips"].notna()].copy()
    out["state_fips"] = out["county_fips"].astype(str).str.slice(0, 2)
    out["state_abbr"] = out["state_abbr"].astype(str).str.upper()
    out["state_name"] = out["state_name"].astype(str).str.strip()
    out["county_name"] = out["county_name"].astype(str).str.strip()
    out["geography_name"] = out.apply(
        lambda row: _geography_name(row["county_name"], row["state_name"]),
        axis=1,
    )
    out["places_total_population"] = pd.to_numeric(out["totalpopulation"], errors="coerce").astype(
        "Int64"
    )
    out["places_total_pop_18plus"] = pd.to_numeric(out["totalpop18plus"], errors="coerce").astype(
        "Int64"
    )
    for value_column, _ in PLACES_VALUE_SUFFIXES:
        out[value_column] = pd.to_numeric(out[value_column], errors="coerce")
    return out


def _base_county_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (release_year, county_fips), group in frame.groupby(
        ["release_year", "county_fips"], sort=True
    ):
        first = group.sort_values(["year", "measureid"]).iloc[-1]
        years = pd.to_numeric(group["year"], errors="coerce").dropna()
        rows.append(
            {
                "release_year": int(release_year),
                "year": int(years.max()) if not years.empty else pd.NA,
                "state_fips": str(first["state_fips"]),
                "state_abbr": str(first["state_abbr"]),
                "state_name": str(first["state_name"]),
                "county_fips": str(county_fips),
                "county_name": str(first["county_name"]),
                "geography_name": str(first["geography_name"]),
                "places_total_population": first["places_total_population"],
                "places_total_pop_18plus": first["places_total_pop_18plus"],
                "places_estimate_year_min": int(years.min()) if not years.empty else pd.NA,
                "places_estimate_year_max": int(years.max()) if not years.empty else pd.NA,
            }
        )
    return pd.DataFrame(rows)


def _measure_column_name(measure: PlacesMeasure, suffix: str) -> str:
    return f"places_{measure.feature_prefix}_crude_prevalence{suffix}"


def _measure_year_column_name(measure: PlacesMeasure) -> str:
    return f"places_{measure.feature_prefix}_estimate_year"


def build_places_county_context_table(csv_path: Path, *, release_year: int) -> pd.DataFrame:
    """Build one wide county-year CDC PLACES context table from a raw CSV."""
    selected = _selected_crude_rows(_read_places_csv(csv_path), release_year=release_year)
    key_columns = ["release_year", "county_fips"]
    out = _base_county_rows(selected)

    for measure in PLACES_CONTEXT_MEASURES:
        measure_rows = selected.loc[selected["measureid"] == measure.measure_id].copy()
        if measure_rows.duplicated(subset=key_columns).any():
            raise ValueError(f"Duplicate PLACES crude prevalence rows for {measure.measure_id}.")
        if measure_rows.empty:
            for _, suffix in PLACES_VALUE_SUFFIXES:
                out[_measure_column_name(measure, suffix)] = pd.NA
            out[_measure_year_column_name(measure)] = pd.NA
            continue
        value_columns = {
            source_column: _measure_column_name(measure, suffix)
            for source_column, suffix in PLACES_VALUE_SUFFIXES
        }
        measure_wide = measure_rows.loc[:, [*key_columns, "year", *value_columns.keys()]].rename(
            columns={"year": _measure_year_column_name(measure), **value_columns}
        )
        out = out.merge(measure_wide, on=key_columns, how="left", validate="one_to_one")

    ordered = [
        *_BASE_COLUMNS,
        "places_estimate_year_min",
        "places_estimate_year_max",
        *PLACES_MEASURE_COLUMNS,
    ]
    out = out.loc[:, ordered].sort_values(["release_year", "state_fips", "county_fips"])
    out["release_year"] = out["release_year"].astype(int)
    out["year"] = out["year"].astype(int)
    return out.reset_index(drop=True)


def _years_present_in_output(path: Path) -> set[int] | None:
    try:
        existing = pd.read_parquet(path, columns=["release_year"])
    except Exception:
        return None
    if "release_year" not in existing.columns:
        return None
    years = pd.to_numeric(existing["release_year"], errors="coerce")
    return {int(value) for value in years.dropna().unique().tolist()}


def _output_has_release_years(path: Path, years: Sequence[int]) -> bool:
    if not path.exists():
        return False
    present = _years_present_in_output(path)
    return present is not None and set(years).issubset(present)


def _places_source_registry_extra(years: Sequence[int]) -> dict[str, Any]:
    registry = load_data_source_registry()
    return {
        "source_registry_by_year": {
            str(year): registry_provenance_extra(
                registry=registry,
                source_ids=[PLACES_SOURCE_ID],
                year=year,
            )["source_registry"]
            for year in years
        }
    }


def _append_existing_file(files: list[FileProvenance], path: Path, *, root: Path) -> None:
    if path.exists():
        files.append(collect_file_provenance(path, root=root))


def build_places_tables(
    *,
    base_dir: Path,
    years: list[int],
    force: bool,
    dry_run: bool,
) -> None:
    """Build processed PLACES county-year context tables for release years."""
    output_path = places_county_year_parquet(base_dir)
    if not force and _output_has_release_years(output_path, years):
        print(f"Skip build (exists): {output_path}")
        return
    if output_path.exists():
        print("Rebuild PLACES county context table for requested release years.")

    tables: list[pd.DataFrame] = []
    for year in years:
        input_path = places_county_csv_path(base_dir, year=year)
        if not input_path.exists():
            raise FileNotFoundError(
                f"Missing CDC PLACES county CSV for release {year}: {input_path}. "
                "Run download_places first."
            )
        tables.append(build_places_county_context_table(input_path, release_year=year))

    combined = pd.concat(tables, ignore_index=True).sort_values(
        ["release_year", "state_fips", "county_fips"]
    )
    duplicates = combined.duplicated(subset=["release_year", "county_fips"]).sum()
    if int(duplicates) != 0:
        raise ValueError(
            "PLACES county-year output has duplicate (release_year, county_fips) keys."
        )

    print(f"PLACES county rows written: {len(combined):,}")
    if dry_run:
        print(f"DRY RUN: would write parquet -> {output_path}")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(output_path, index=False)

    files: list[FileProvenance] = []
    for year in years:
        _append_existing_file(files, places_county_csv_path(base_dir, year=year), root=base_dir)
    _append_existing_file(files, output_path, root=base_dir)

    write_provenance_json(
        provenance_places_county_year(base_dir, years),
        dataset_name="cdc_places_county_context",
        dataset_version="_".join(str(year) for year in years),
        sources=[places_county_csv_url(year) for year in years],
        files=files,
        extra={
            **_places_source_registry_extra(years),
            "places_release_years": list(years),
            "places_measure_ids": list(PLACES_MEASURE_IDS),
            "places_measure_columns": list(PLACES_MEASURE_COLUMNS),
            "places_context_caveat": PLACES_CONTEXT_CAVEAT,
            "county_rows": len(combined),
            "scenario_editable_columns_excluded": sorted(SCENARIO_EDITABLE_COLUMNS),
        },
        dry_run=dry_run,
    )


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for building CDC PLACES county context tables."""
    parser = argparse.ArgumentParser(description="Build CDC PLACES county context tables.")
    add_common_pipeline_args(parser)
    args = parser.parse_args(argv)
    build_places_tables(
        base_dir=Path(args.base_dir),
        years=parse_years_from_args(args),
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
