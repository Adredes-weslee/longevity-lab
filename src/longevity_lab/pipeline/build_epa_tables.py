"""Build processed EPA AirData tables used in integration."""

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

_EPA_AIRDATA_BASE_URL = "https://aqs.epa.gov/aqsweb/airdata"
_AQI_COMPLETENESS_MIN_DAYS = 274
_POLLUTANT_COMPLETENESS_MIN_PERCENT = 75.0


@dataclass(frozen=True, slots=True)
class PollutantSpec:
    """Configuration for one EPA AirData pollutant feature family."""

    prefix: str
    parameter_code: int
    standard_keywords: tuple[str, ...]


_POLLUTANT_SPECS: tuple[PollutantSpec, ...] = (
    PollutantSpec(prefix="pm25", parameter_code=88101, standard_keywords=("annual",)),
    PollutantSpec(prefix="ozone", parameter_code=44201, standard_keywords=("8-hour",)),
)
_POLLUTANT_BY_CODE: dict[int, PollutantSpec] = {
    spec.parameter_code: spec for spec in _POLLUTANT_SPECS
}

_COUNTY_KEY_COLUMNS = ["year", "state_fips", "county_key"]
_COUNTY_YEAR_COLUMNS = [
    "year",
    "state_fips",
    "county_fips",
    "county_name",
    "annual_aqi",
    "aqi_days_with_aqi",
    "aqi_observation_complete",
    "pm25_mean",
    "pm25_monitor_count",
    "pm25_observation_percent",
    "pm25_observation_complete",
    "ozone_mean",
    "ozone_monitor_count",
    "ozone_observation_percent",
    "ozone_observation_complete",
]
_STATE_YEAR_BASE_COLUMNS = ["year", "state_fips", "annual_aqi"]
_STATE_YEAR_POLLUTANT_COLUMNS = [
    "pm25_mean",
    "pm25_monitor_count",
    "pm25_observation_percent",
    "pm25_observation_complete",
    "ozone_mean",
    "ozone_monitor_count",
    "ozone_observation_percent",
    "ozone_observation_complete",
]
_STATE_YEAR_COLUMNS = [*_STATE_YEAR_BASE_COLUMNS, *_STATE_YEAR_POLLUTANT_COLUMNS]


@dataclass(frozen=True, slots=True)
class EpaBuildResult:
    """One year of processed EPA output."""

    year: int
    table: pd.DataFrame
    dropped_rows: int
    pollutant_quality_failed_rows: int = 0


def state_name_to_fips(state_name: object) -> str | None:
    """Map an EPA `State` name to a 2-digit state/territory FIPS code."""
    if not isinstance(state_name, str):
        return None
    normalized = state_name.strip().casefold()
    if not normalized:
        return None
    return _STATE_NAME_TO_FIPS_NORMALIZED.get(normalized)


def _annual_conc_by_monitor_zip_path(base_dir: Path, year: int) -> Path:
    return base_dir / "external" / "epa_airdata" / f"annual_conc_by_monitor_{year}.zip"


def _annual_conc_by_monitor_csv_path(base_dir: Path, year: int) -> Path:
    return (
        base_dir
        / "external"
        / "epa_airdata"
        / f"annual_conc_by_monitor_{year}"
        / f"annual_conc_by_monitor_{year}.csv"
    )


def _county_year_output_path(base_dir: Path) -> Path:
    return base_dir / "processed" / "epa_airdata" / "epa_county_year.parquet"


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


def _clean_text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def _normalized_county_name(value: object) -> str | None:
    text = _clean_text(value)
    return text.casefold() if text else None


def _county_key(state_fips: object, county_name: object, county_fips: object) -> str | None:
    state = _clean_text(state_fips)
    county = _normalized_county_name(county_name)
    if state and county:
        return f"{state}:{county}"
    fips = _clean_text(county_fips)
    if fips:
        return f"fips:{fips}"
    return None


def _pollutant_feature_columns(prefix: str) -> list[str]:
    return [
        f"{prefix}_mean",
        f"{prefix}_monitor_count",
        f"{prefix}_observation_percent",
        f"{prefix}_observation_complete",
    ]


def _empty_pollutant_table() -> pd.DataFrame:
    columns = [*_COUNTY_KEY_COLUMNS, "county_fips", "county_name"]
    for spec in _POLLUTANT_SPECS:
        columns.extend(_pollutant_feature_columns(spec.prefix))
    return pd.DataFrame(columns=columns)


def _finalize_pollutant_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for spec in _POLLUTANT_SPECS:
        mean_col = f"{spec.prefix}_mean"
        count_col = f"{spec.prefix}_monitor_count"
        percent_col = f"{spec.prefix}_observation_percent"
        complete_col = f"{spec.prefix}_observation_complete"

        if mean_col not in out.columns:
            out[mean_col] = np.nan
        if count_col not in out.columns:
            out[count_col] = 0
        if percent_col not in out.columns:
            out[percent_col] = np.nan
        if complete_col not in out.columns:
            out[complete_col] = False

        out[count_col] = pd.to_numeric(out[count_col], errors="coerce").fillna(0).astype("Int64")
        out[complete_col] = out[complete_col].map(
            lambda value: bool(value) if pd.notna(value) else False
        )
        out[mean_col] = pd.to_numeric(out[mean_col], errors="coerce").where(out[complete_col])
        out[percent_col] = pd.to_numeric(out[percent_col], errors="coerce").where(out[complete_col])
    return out


def _build_aqi_county_table(csv_path: Path, *, year: int) -> EpaBuildResult:
    frame = pd.read_csv(csv_path)
    require_columns(
        actual=frame.columns,
        required=["State", "County", "Year", "Days with AQI", "Median AQI"],
        context=f"EPA annual AQI {year}",
    )
    frame["year"] = pd.to_numeric(frame["Year"], errors="coerce")
    frame = frame.loc[frame["year"] == year].copy()
    frame["state_fips"] = frame["State"].map(state_name_to_fips)
    dropped_rows = int(frame["state_fips"].isna().sum())
    frame = frame.loc[frame["state_fips"].notna()].copy()

    frame["county_name"] = frame["County"].map(_clean_text)
    if {"State Code", "County Code"}.issubset(frame.columns):
        frame["county_code"] = frame["County Code"].map(lambda value: _format_fips(value, 3))
        frame["county_fips"] = frame.apply(
            lambda row: (
                f"{row['state_fips']}{row['county_code']}"
                if pd.notna(row["state_fips"]) and pd.notna(row["county_code"])
                else pd.NA
            ),
            axis=1,
        )
    else:
        frame["county_fips"] = pd.NA
    frame["county_key"] = frame.apply(
        lambda row: _county_key(row["state_fips"], row["county_name"], row["county_fips"]),
        axis=1,
    )

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
        frame.groupby(
            ["year", "state_fips", "county_key", "county_fips", "county_name"],
            as_index=False,
            dropna=False,
        )
        .agg(
            sum_weighted=("weighted_median_aqi", "sum"),
            sum_weights=("days_with_aqi_valid", "sum"),
        )
        .sort_values(["year", "state_fips", "county_name"])
        .reset_index(drop=True)
    )
    weights = agg["sum_weights"].where(agg["sum_weights"] > 0, other=np.nan)
    agg["annual_aqi_float"] = agg["sum_weighted"] / weights
    agg["annual_aqi"] = agg["annual_aqi_float"].round().clip(lower=0, upper=500).astype("Int64")
    agg["aqi_days_with_aqi"] = agg["sum_weights"].round().astype("Int64")
    agg["aqi_observation_complete"] = agg["sum_weights"] >= _AQI_COMPLETENESS_MIN_DAYS
    agg["year"] = agg["year"].astype(int)
    agg["state_fips"] = agg["state_fips"].astype(str)

    out = agg[
        [
            "year",
            "state_fips",
            "county_key",
            "county_fips",
            "county_name",
            "annual_aqi",
            "aqi_days_with_aqi",
            "aqi_observation_complete",
        ]
    ].copy()
    return EpaBuildResult(year=year, table=out, dropped_rows=dropped_rows)


def _standard_is_preferred(standard: object, spec: PollutantSpec) -> bool:
    text = _clean_text(standard)
    if not text:
        return False
    normalized = text.casefold()
    return any(keyword in normalized for keyword in spec.standard_keywords)


def _event_type_rank(value: object) -> int:
    text = _clean_text(value)
    if not text:
        return 99
    ranks = {
        "no events": 0,
        "events excluded": 1,
        "concurred events excluded": 2,
        "events included": 3,
    }
    return ranks.get(text.casefold(), 50)


def _read_annual_conc_frame(csv_path: Path, *, year: int) -> pd.DataFrame:
    frame = pd.read_csv(
        csv_path,
        dtype={
            "State Code": "string",
            "County Code": "string",
            "Site Num": "string",
            "POC": "string",
        },
    )
    require_columns(
        actual=frame.columns,
        required=[
            "State Code",
            "County Code",
            "Site Num",
            "Parameter Code",
            "POC",
            "Pollutant Standard",
            "Year",
            "Observation Count",
            "Observation Percent",
            "Completeness Indicator",
            "Arithmetic Mean",
            "State Name",
            "County Name",
        ],
        context=f"EPA annual concentration {year}",
    )
    frame["year"] = pd.to_numeric(frame["Year"], errors="coerce")
    frame = frame.loc[frame["year"] == year].copy()
    frame["parameter_code"] = pd.to_numeric(frame["Parameter Code"], errors="coerce")
    frame = frame.loc[frame["parameter_code"].isin(_POLLUTANT_BY_CODE)].copy()
    if frame.empty:
        return frame

    frame["state_fips"] = frame["State Code"].map(lambda value: _format_fips(value, 2))
    missing_state = frame["state_fips"].isna()
    frame.loc[missing_state, "state_fips"] = frame.loc[missing_state, "State Name"].map(
        state_name_to_fips
    )
    frame["county_code"] = frame["County Code"].map(lambda value: _format_fips(value, 3))
    frame["site_num"] = frame["Site Num"].map(lambda value: _format_fips(value, 4))
    frame["poc"] = frame["POC"].map(_clean_text)
    frame["county_fips"] = frame.apply(
        lambda row: (
            f"{row['state_fips']}{row['county_code']}"
            if pd.notna(row["state_fips"]) and pd.notna(row["county_code"])
            else pd.NA
        ),
        axis=1,
    )
    frame["county_name"] = frame["County Name"].map(_clean_text)
    frame["county_key"] = frame.apply(
        lambda row: _county_key(row["state_fips"], row["county_name"], row["county_fips"]),
        axis=1,
    )
    frame["prefix"] = frame["parameter_code"].map(
        lambda value: _POLLUTANT_BY_CODE[int(value)].prefix if pd.notna(value) else None
    )
    frame["monitor_id"] = frame.apply(
        lambda row: "-".join(
            str(part)
            for part in [
                row["state_fips"],
                row["county_code"],
                row["site_num"],
                int(row["parameter_code"]) if pd.notna(row["parameter_code"]) else "",
                row["poc"],
            ]
            if pd.notna(part)
        ),
        axis=1,
    )
    frame["observation_count"] = pd.to_numeric(frame["Observation Count"], errors="coerce")
    frame["observation_percent"] = pd.to_numeric(frame["Observation Percent"], errors="coerce")
    frame["pollutant_mean"] = pd.to_numeric(frame["Arithmetic Mean"], errors="coerce")
    frame["complete_monitor"] = (
        frame["Completeness Indicator"].astype(str).str.strip().str.upper().eq("Y")
        & frame["observation_count"].gt(0)
        & frame["observation_percent"].ge(_POLLUTANT_COMPLETENESS_MIN_PERCENT)
        & frame["pollutant_mean"].notna()
        & frame["county_key"].notna()
    )
    frame["standard_preferred"] = frame.apply(
        lambda row: (
            _standard_is_preferred(
                row["Pollutant Standard"],
                _POLLUTANT_BY_CODE[int(row["parameter_code"])],
            )
            if pd.notna(row["parameter_code"])
            else False
        ),
        axis=1,
    )
    frame["event_rank"] = (
        frame["Event Type"].map(_event_type_rank) if "Event Type" in frame.columns else 99
    )
    return frame


def _canonical_monitor_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    sorted_frame = frame.sort_values(
        [
            "prefix",
            "monitor_id",
            "complete_monitor",
            "standard_preferred",
            "observation_percent",
            "observation_count",
            "event_rank",
        ],
        ascending=[True, True, False, False, False, False, True],
    )
    return sorted_frame.drop_duplicates(subset=["prefix", "monitor_id"], keep="first")


def _aggregate_pollutant_county_features(csv_path: Path, *, year: int) -> EpaBuildResult:
    frame = _canonical_monitor_rows(_read_annual_conc_frame(csv_path, year=year))
    if frame.empty:
        return EpaBuildResult(year=year, table=_empty_pollutant_table(), dropped_rows=0)

    base = frame[
        ["year", "state_fips", "county_key", "county_fips", "county_name"]
    ].drop_duplicates()
    out = base.copy()
    quality_failed = int((~frame["complete_monitor"]).sum())

    for spec in _POLLUTANT_SPECS:
        feature_cols = _pollutant_feature_columns(spec.prefix)
        complete = frame.loc[(frame["prefix"] == spec.prefix) & frame["complete_monitor"]].copy()
        if complete.empty:
            for col in feature_cols:
                out[col] = np.nan
            continue

        complete["weighted_mean"] = complete["pollutant_mean"] * complete["observation_count"]
        complete["weighted_observation_percent"] = (
            complete["observation_percent"] * complete["observation_count"]
        )
        agg = (
            complete.groupby(_COUNTY_KEY_COLUMNS, as_index=False)
            .agg(
                sum_weighted_mean=("weighted_mean", "sum"),
                sum_observation_weights=("observation_count", "sum"),
                sum_weighted_observation_percent=("weighted_observation_percent", "sum"),
                monitor_count=("monitor_id", "nunique"),
            )
            .reset_index(drop=True)
        )
        weights = agg["sum_observation_weights"].where(
            agg["sum_observation_weights"] > 0,
            other=np.nan,
        )
        agg[f"{spec.prefix}_mean"] = agg["sum_weighted_mean"] / weights
        agg[f"{spec.prefix}_observation_percent"] = (
            agg["sum_weighted_observation_percent"] / weights
        )
        agg[f"{spec.prefix}_monitor_count"] = agg["monitor_count"].astype("Int64")
        agg[f"{spec.prefix}_observation_complete"] = agg["monitor_count"] > 0

        out = out.merge(
            agg[[*_COUNTY_KEY_COLUMNS, *feature_cols]],
            on=_COUNTY_KEY_COLUMNS,
            how="left",
        )

    out = _finalize_pollutant_columns(out)
    out["year"] = out["year"].astype(int)
    out["state_fips"] = out["state_fips"].astype(str)
    return EpaBuildResult(
        year=year,
        table=out,
        dropped_rows=0,
        pollutant_quality_failed_rows=quality_failed,
    )


def build_county_year_table(
    aqi_csv_path: Path,
    annual_conc_csv_path: Path,
    *,
    year: int,
) -> EpaBuildResult:
    """Build EPA county-year AQI, PM2.5, and ozone aggregates for one year."""
    aqi_result = _build_aqi_county_table(aqi_csv_path, year=year)
    pollutant_result = _aggregate_pollutant_county_features(annual_conc_csv_path, year=year)

    county = aqi_result.table.merge(
        pollutant_result.table,
        on=_COUNTY_KEY_COLUMNS,
        how="outer",
        suffixes=("_aqi", "_pollutant"),
    )
    county["county_fips"] = county.get("county_fips_pollutant", pd.Series(dtype=object))
    county["county_fips"] = county["county_fips"].combine_first(
        county.get("county_fips_aqi", pd.Series(dtype=object))
    )
    county["county_name"] = county.get("county_name_aqi", pd.Series(dtype=object))
    county["county_name"] = county["county_name"].combine_first(
        county.get("county_name_pollutant", pd.Series(dtype=object))
    )
    county = _finalize_pollutant_columns(county)
    county["annual_aqi"] = pd.to_numeric(county["annual_aqi"], errors="coerce").astype("Int64")
    county["aqi_days_with_aqi"] = pd.to_numeric(
        county["aqi_days_with_aqi"],
        errors="coerce",
    ).astype("Int64")
    county["aqi_observation_complete"] = county["aqi_observation_complete"].map(
        lambda value: bool(value) if pd.notna(value) else False
    )
    county["year"] = county["year"].astype(int)
    county["state_fips"] = county["state_fips"].astype(str)
    county = county.sort_values(["year", "state_fips", "county_fips", "county_name"]).reset_index(
        drop=True
    )

    return EpaBuildResult(
        year=year,
        table=county[_COUNTY_YEAR_COLUMNS],
        dropped_rows=aqi_result.dropped_rows,
        pollutant_quality_failed_rows=pollutant_result.pollutant_quality_failed_rows,
    )


def _aggregate_state_year_table(
    county_table: pd.DataFrame,
    *,
    include_pollutants: bool,
) -> pd.DataFrame:
    county = county_table.copy()
    county["aqi_weighted"] = county["annual_aqi"].astype(float) * county[
        "aqi_days_with_aqi"
    ].astype(float)
    county["aqi_weight"] = (
        county["aqi_days_with_aqi"]
        .astype(float)
        .where(
            county["annual_aqi"].notna() & county["aqi_days_with_aqi"].gt(0),
            other=0.0,
        )
    )
    state = (
        county.groupby(["year", "state_fips"], as_index=False)
        .agg(sum_weighted_aqi=("aqi_weighted", "sum"), sum_aqi_weight=("aqi_weight", "sum"))
        .reset_index(drop=True)
    )
    weights = state["sum_aqi_weight"].where(state["sum_aqi_weight"] > 0, other=np.nan)
    state["annual_aqi"] = (
        (state["sum_weighted_aqi"] / weights).round().clip(lower=0, upper=500).astype("Int64")
    )
    state = state[["year", "state_fips", "annual_aqi"]].copy()

    if not include_pollutants:
        state["year"] = state["year"].astype(int)
        state["state_fips"] = state["state_fips"].astype(str)
        return state[_STATE_YEAR_BASE_COLUMNS]

    for spec in _POLLUTANT_SPECS:
        mean_col = f"{spec.prefix}_mean"
        count_col = f"{spec.prefix}_monitor_count"
        percent_col = f"{spec.prefix}_observation_percent"
        complete_col = f"{spec.prefix}_observation_complete"

        county_monitor_count = pd.to_numeric(county[count_col], errors="coerce").fillna(0)
        valid = county.loc[
            county[complete_col].astype(bool)
            & county[mean_col].notna()
            & county_monitor_count.gt(0)
        ].copy()
        if valid.empty:
            state[mean_col] = np.nan
            state[count_col] = 0
            state[percent_col] = np.nan
            state[complete_col] = False
            continue

        valid["monitor_count_float"] = pd.to_numeric(valid[count_col], errors="coerce").fillna(0.0)
        valid["weighted_mean"] = valid[mean_col] * valid["monitor_count_float"]
        valid["weighted_percent"] = valid[percent_col] * valid["monitor_count_float"]
        pollutant_state = (
            valid.groupby(["year", "state_fips"], as_index=False)
            .agg(
                sum_weighted_mean=("weighted_mean", "sum"),
                sum_weighted_percent=("weighted_percent", "sum"),
                monitor_count=("monitor_count_float", "sum"),
            )
            .reset_index(drop=True)
        )
        weights = pollutant_state["monitor_count"].where(
            pollutant_state["monitor_count"] > 0,
            other=np.nan,
        )
        pollutant_state[mean_col] = pollutant_state["sum_weighted_mean"] / weights
        pollutant_state[percent_col] = pollutant_state["sum_weighted_percent"] / weights
        pollutant_state[count_col] = pollutant_state["monitor_count"].round().astype("Int64")
        pollutant_state[complete_col] = pollutant_state[count_col].gt(0)

        state = state.merge(
            pollutant_state[["year", "state_fips", mean_col, count_col, percent_col, complete_col]],
            on=["year", "state_fips"],
            how="left",
        )

    state = _finalize_pollutant_columns(state)
    state["year"] = state["year"].astype(int)
    state["state_fips"] = state["state_fips"].astype(str)
    return state[_STATE_YEAR_COLUMNS].sort_values(["year", "state_fips"]).reset_index(drop=True)


def build_state_year_table(
    csv_path: Path,
    *,
    year: int,
    annual_conc_csv_path: Path | None = None,
) -> EpaBuildResult:
    """Convert EPA county-level files into a state-year table."""
    if annual_conc_csv_path is None:
        aqi_result = _build_aqi_county_table(csv_path, year=year)
        state = _aggregate_state_year_table(aqi_result.table, include_pollutants=False)
        return EpaBuildResult(year=year, table=state, dropped_rows=aqi_result.dropped_rows)

    county_result = build_county_year_table(csv_path, annual_conc_csv_path, year=year)
    state = _aggregate_state_year_table(county_result.table, include_pollutants=True)
    return EpaBuildResult(
        year=year,
        table=state,
        dropped_rows=county_result.dropped_rows,
        pollutant_quality_failed_rows=county_result.pollutant_quality_failed_rows,
    )


def _output_has_years(path: Path, years: list[int]) -> bool:
    if not path.exists():
        return False
    present_years = _years_present_in_output(path)
    return present_years is not None and set(years).issubset(present_years)


def _require_input(path: Path, *, year: int, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing EPA {label} CSV for {year}: {path}.")


def _collect_existing_file(
    path: Path,
    *,
    root: Path,
    url: str | None = None,
) -> FileProvenance | None:
    if not path.exists():
        return None
    return collect_file_provenance(path, url=url, root=root)


def _append_existing(files: list[FileProvenance], item: FileProvenance | None) -> None:
    if item is not None:
        files.append(item)


def _annual_conc_by_monitor_url(year: int) -> str:
    return f"{_EPA_AIRDATA_BASE_URL}/annual_conc_by_monitor_{year}.zip"


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for building processed EPA county-year and state-year tables."""
    parser = argparse.ArgumentParser(
        description="Build EPA AirData AQI, PM2.5, and ozone county/state-year tables."
    )
    add_common_pipeline_args(parser)
    args = parser.parse_args(argv)
    years = parse_years_from_args(args)
    paths = build_ingest_paths(Path(args.base_dir))

    output_path = paths.epa_state_year_parquet()
    county_output_path = _county_year_output_path(paths.base_dir)
    if (
        not args.force
        and _output_has_years(output_path, years)
        and _output_has_years(county_output_path, years)
    ):
        print(f"Skip build (exists): {output_path}")
        print(f"Skip build (exists): {county_output_path}")
        return
    if output_path.exists() or county_output_path.exists():
        print(f"Rebuild EPA outputs for requested years: {years}")

    state_results: list[EpaBuildResult] = []
    county_results: list[EpaBuildResult] = []
    for year in years:
        aqi_csv_path = paths.epa_airdata_annual_aqi_csv(year)
        annual_conc_csv_path = _annual_conc_by_monitor_csv_path(paths.base_dir, year)
        _require_input(aqi_csv_path, year=year, label="annual AQI by county")
        _require_input(annual_conc_csv_path, year=year, label="annual concentration by monitor")

        county_result = build_county_year_table(aqi_csv_path, annual_conc_csv_path, year=year)
        state_table = _aggregate_state_year_table(county_result.table, include_pollutants=True)
        county_results.append(county_result)
        state_results.append(
            EpaBuildResult(
                year=year,
                table=state_table,
                dropped_rows=county_result.dropped_rows,
                pollutant_quality_failed_rows=county_result.pollutant_quality_failed_rows,
            )
        )

    combined_state = pd.concat([item.table for item in state_results], ignore_index=True)
    combined_state = combined_state.sort_values(["year", "state_fips"]).reset_index(drop=True)
    combined_county = pd.concat([item.table for item in county_results], ignore_index=True)
    combined_county = combined_county.sort_values(
        ["year", "state_fips", "county_fips", "county_name"]
    ).reset_index(drop=True)

    duplicates = combined_state.duplicated(subset=["year", "state_fips"]).sum()
    if int(duplicates) != 0:
        raise ValueError("EPA state-year output has duplicate (year, state_fips) keys.")
    county_duplicates = combined_county.duplicated(
        subset=["year", "state_fips", "county_fips", "county_name"]
    ).sum()
    if int(county_duplicates) != 0:
        raise ValueError("EPA county-year output has duplicate county-year keys.")

    total_dropped = sum(item.dropped_rows for item in state_results)
    total_quality_failed = sum(item.pollutant_quality_failed_rows for item in state_results)
    print(
        f"State rows written: {len(combined_state)}; county rows written: {len(combined_county)} "
        f"(dropped unmapped AQI rows: {total_dropped}; "
        f"quality-failed pollutant monitor rows: {total_quality_failed})"
    )
    print("State null counts:")
    for col in ["annual_aqi", "pm25_mean", "ozone_mean"]:
        print(f"  {col}: {int(combined_state[col].isna().sum())}")

    if args.dry_run:
        print(f"DRY RUN: would write parquet -> {output_path}")
        print(f"DRY RUN: would write parquet -> {county_output_path}")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        combined_state.to_parquet(output_path, index=False)
        county_output_path.parent.mkdir(parents=True, exist_ok=True)
        combined_county.to_parquet(county_output_path, index=False)

    year_to_aqi_source = {
        year: (f"{_EPA_AIRDATA_BASE_URL}/annual_aqi_by_county_{year}.zip") for year in years
    }
    year_to_annual_conc_source = {year: _annual_conc_by_monitor_url(year) for year in years}
    sources = [
        source
        for year in years
        for source in [year_to_aqi_source[year], year_to_annual_conc_source[year]]
    ]
    files: list[FileProvenance] = []
    _append_existing(files, _collect_existing_file(output_path, root=paths.base_dir))
    _append_existing(files, _collect_existing_file(county_output_path, root=paths.base_dir))
    for year in years:
        _append_existing(
            files,
            _collect_existing_file(
                paths.epa_airdata_annual_aqi_zip(year),
                url=year_to_aqi_source[year],
                root=paths.base_dir,
            ),
        )
        _append_existing(
            files,
            _collect_existing_file(paths.epa_airdata_annual_aqi_csv(year), root=paths.base_dir),
        )
        _append_existing(
            files,
            _collect_existing_file(
                _annual_conc_by_monitor_zip_path(paths.base_dir, year),
                url=year_to_annual_conc_source[year],
                root=paths.base_dir,
            ),
        )
        _append_existing(
            files,
            _collect_existing_file(
                _annual_conc_by_monitor_csv_path(paths.base_dir, year),
                root=paths.base_dir,
            ),
        )

    write_provenance_json(
        paths.provenance_epa_airdata_state_year(years),
        dataset_name="epa_airdata_environment_state_county_year",
        dataset_version="_".join(str(year) for year in years),
        sources=sources,
        files=files,
        extra={
            "dropped_unmapped_aqi_rows": total_dropped,
            "pollutant_quality_failed_monitor_rows": total_quality_failed,
            "county_output": county_output_path.relative_to(paths.base_dir).as_posix(),
            "state_output": output_path.relative_to(paths.base_dir).as_posix(),
            "pollutants": {
                spec.prefix: {
                    "parameter_code": spec.parameter_code,
                    "minimum_observation_percent": _POLLUTANT_COMPLETENESS_MIN_PERCENT,
                    "requires_completeness_indicator": "Y",
                }
                for spec in _POLLUTANT_SPECS
            },
            "aqi_minimum_days_with_aqi": _AQI_COMPLETENESS_MIN_DAYS,
        },
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
