"""Build processed EPA AirData tables used in integration (v1)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.pipeline.common import (
    FileProvenance,
    add_common_pipeline_args,
    collect_file_provenance,
    parse_years_from_args,
    require_columns,
    write_provenance_json,
)
from longevity_lab.pipeline.ingest import build_ingest_paths

_STATE_NAME_TO_FIPS: dict[str, str] = {
    "Alabama": "01",
    "Alaska": "02",
    "Arizona": "04",
    "Arkansas": "05",
    "California": "06",
    "Colorado": "08",
    "Connecticut": "09",
    "Delaware": "10",
    "District Of Columbia": "11",
    "Florida": "12",
    "Georgia": "13",
    "Hawaii": "15",
    "Idaho": "16",
    "Illinois": "17",
    "Indiana": "18",
    "Iowa": "19",
    "Kansas": "20",
    "Kentucky": "21",
    "Louisiana": "22",
    "Maine": "23",
    "Maryland": "24",
    "Massachusetts": "25",
    "Michigan": "26",
    "Minnesota": "27",
    "Mississippi": "28",
    "Missouri": "29",
    "Montana": "30",
    "Nebraska": "31",
    "Nevada": "32",
    "New Hampshire": "33",
    "New Jersey": "34",
    "New Mexico": "35",
    "New York": "36",
    "North Carolina": "37",
    "North Dakota": "38",
    "Ohio": "39",
    "Oklahoma": "40",
    "Oregon": "41",
    "Pennsylvania": "42",
    "Rhode Island": "44",
    "South Carolina": "45",
    "South Dakota": "46",
    "Tennessee": "47",
    "Texas": "48",
    "Utah": "49",
    "Vermont": "50",
    "Virginia": "51",
    "Washington": "53",
    "West Virginia": "54",
    "Wisconsin": "55",
    "Wyoming": "56",
    "Puerto Rico": "72",
    "Virgin Islands": "78",
    "American Samoa": "60",
    "Guam": "66",
    "Northern Mariana Islands": "69",
}

_STATE_NAME_TO_FIPS_NORMALIZED: dict[str, str] = {
    key.strip().casefold(): value for key, value in _STATE_NAME_TO_FIPS.items()
}


@dataclass(frozen=True, slots=True)
class EpaBuildResult:
    """One year of processed EPA state-year AQI output."""

    year: int
    table: pd.DataFrame
    dropped_rows: int


def state_name_to_fips(state_name: object) -> str | None:
    """Map an EPA `State` name to a 2-digit state/territory FIPS code."""
    if not isinstance(state_name, str):
        return None
    normalized = state_name.strip().casefold()
    if not normalized:
        return None
    return _STATE_NAME_TO_FIPS_NORMALIZED.get(normalized)


def _years_present_in_output(output_path: Path) -> set[int] | None:
    """Return the set of years present in an existing output parquet (or None if unreadable)."""
    try:
        existing = pd.read_parquet(output_path, columns=["year"])
    except Exception:
        return None
    if "year" not in existing.columns:
        return None

    year_series = pd.to_numeric(existing["year"], errors="coerce")
    return {int(value) for value in year_series.dropna().unique().tolist()}


def _input_csv_path(base_dir: Path, year: int) -> Path:
    paths = build_ingest_paths(base_dir)
    return paths.epa_airdata_annual_aqi_csv(year)


def build_state_year_table(csv_path: Path, *, year: int) -> EpaBuildResult:
    """Convert the EPA county-level file into a state-year table."""
    frame = pd.read_csv(csv_path)
    require_columns(
        actual=frame.columns,
        required=["State", "Year", "Days with AQI", "Median AQI"],
        context=f"EPA annual AQI {year}",
    )
    frame = frame.loc[frame["Year"] == year].copy()
    frame["state_fips"] = frame["State"].map(state_name_to_fips)
    dropped_rows = int(frame["state_fips"].isna().sum())
    frame = frame.loc[frame["state_fips"].notna()].copy()

    frame["days_with_aqi"] = pd.to_numeric(frame["Days with AQI"], errors="coerce")
    frame["median_aqi"] = pd.to_numeric(frame["Median AQI"], errors="coerce")
    valid = (
        frame["days_with_aqi"].notna() & frame["median_aqi"].notna() & (frame["days_with_aqi"] > 0)
    )
    frame["weighted_median_aqi"] = (frame["median_aqi"] * frame["days_with_aqi"]).where(
        valid, other=0.0
    )
    frame["days_with_aqi_valid"] = frame["days_with_aqi"].where(valid, other=0.0)

    agg = (
        frame.groupby(["state_fips", "Year"], as_index=False)
        .agg(
            sum_weighted=("weighted_median_aqi", "sum"),
            sum_weights=("days_with_aqi_valid", "sum"),
        )
        .rename(columns={"Year": "year"})
    )
    weights = agg["sum_weights"].where(agg["sum_weights"] > 0, other=np.nan)
    agg["annual_aqi_float"] = agg["sum_weighted"] / weights

    out = agg[["year", "state_fips", "annual_aqi_float"]].copy()
    out["annual_aqi"] = out["annual_aqi_float"].round().clip(lower=0, upper=500).astype("Int64")
    out = out.drop(columns=["annual_aqi_float"])
    out["year"] = out["year"].astype(int)
    out["state_fips"] = out["state_fips"].astype(str)
    return EpaBuildResult(
        year=year,
        table=out[["year", "state_fips", "annual_aqi"]],
        dropped_rows=dropped_rows,
    )


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for building the processed EPA state-year AQI table."""
    parser = argparse.ArgumentParser(
        description="Build EPA AirData annual AQI state-year table (v1)."
    )
    add_common_pipeline_args(parser)
    args = parser.parse_args(argv)
    years = parse_years_from_args(args)
    paths = build_ingest_paths(Path(args.base_dir))

    output_path = paths.epa_state_year_parquet()
    if output_path.exists() and not args.force:
        present_years = _years_present_in_output(output_path)
        if present_years is not None:
            missing = sorted(set(years) - present_years)
            if not missing:
                print(f"Skip build (exists): {output_path}")
                return
            print(f"Rebuild (output missing years {missing}): {output_path}")
        else:
            print(f"Rebuild (unable to read existing output): {output_path}")

    results: list[EpaBuildResult] = []
    for year in years:
        csv_path = paths.epa_airdata_annual_aqi_csv(year)
        if not csv_path.exists():
            raise FileNotFoundError(
                f"Missing EPA input CSV for {year}: {csv_path}. Run download_epa_airdata first."
            )
        results.append(build_state_year_table(csv_path, year=year))

    combined = pd.concat([item.table for item in results], ignore_index=True)
    combined = combined.sort_values(["year", "state_fips"]).reset_index(drop=True)

    duplicates = combined.duplicated(subset=["year", "state_fips"]).sum()
    if int(duplicates) != 0:
        raise ValueError("EPA state-year output has duplicate (year, state_fips) keys.")

    total_dropped = sum(item.dropped_rows for item in results)
    print(f"Rows written: {len(combined)} (dropped unmapped rows: {total_dropped})")
    print("Null counts:")
    for col in ["annual_aqi"]:
        print(f"  {col}: {int(combined[col].isna().sum())}")

    if args.dry_run:
        print(f"DRY RUN: would write parquet -> {output_path}")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(output_path, index=False)

    year_to_source = {
        year: (f"https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_county_{year}.zip")
        for year in years
    }
    sources = [year_to_source[year] for year in years]
    files: list[FileProvenance] = []
    if output_path.exists():
        files.append(collect_file_provenance(output_path, root=paths.base_dir))
    for year in years:
        zip_path = paths.epa_airdata_annual_aqi_zip(year)
        if zip_path.exists():
            files.append(
                collect_file_provenance(zip_path, url=year_to_source[year], root=paths.base_dir)
            )
        files.append(
            collect_file_provenance(
                paths.epa_airdata_annual_aqi_csv(year),
                root=paths.base_dir,
            )
        )

    write_provenance_json(
        paths.provenance_epa_airdata_state_year(years),
        dataset_name="epa_airdata_annual_aqi_state_year",
        dataset_version="_".join(str(year) for year in years),
        sources=sources,
        files=files,
        extra={"dropped_unmapped_rows": total_dropped},
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
