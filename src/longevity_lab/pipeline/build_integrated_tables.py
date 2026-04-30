"""Build integrated BRFSS + EPA tables for model training."""

from __future__ import annotations

import argparse
from pathlib import Path

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

BRFSS_REQUIRED_COLUMNS: list[str] = [
    "year",
    "state_fips",
    "age",
    "bmi",
    "smoker",
    "alcohol_servings_per_week",
    "exercise_minutes_per_week",
    "label_heart_disease",
    "label_chronic_lung_disease",
    "label_stroke",
    "label_depression",
    "label_diabetes",
    "survey_weight",
]

BRFSS_V2_REQUIRED_COLUMNS: list[str] = [
    "sex",
    "race_ethnicity",
    "has_healthcare_coverage",
    "has_personal_doctor",
    "cost_barrier_to_care",
    "last_checkup_within_year",
    "sleep_hours_per_night",
    "physical_health_days",
    "mental_health_days",
]

EPA_REQUIRED_COLUMNS: list[str] = ["year", "state_fips", "annual_aqi"]
EPA_OPTIONAL_COLUMNS: list[str] = [
    "pm25_mean",
    "pm25_monitor_count",
    "pm25_observation_percent",
    "pm25_observation_complete",
    "ozone_mean",
    "ozone_monitor_count",
    "ozone_observation_percent",
    "ozone_observation_complete",
]
POLLUTANT_PREFIXES: tuple[str, ...] = ("pm25", "ozone")

INTEGRATED_COLUMNS: list[str] = [
    "year",
    "state_fips",
    "sex",
    "race_ethnicity",
    "age",
    "bmi",
    "smoker",
    "alcohol_servings_per_week",
    "exercise_minutes_per_week",
    "annual_aqi",
    *EPA_OPTIONAL_COLUMNS,
    "has_healthcare_coverage",
    "has_personal_doctor",
    "cost_barrier_to_care",
    "last_checkup_within_year",
    "sleep_hours_per_night",
    "physical_health_days",
    "mental_health_days",
    "label_heart_disease",
    "label_chronic_lung_disease",
    "label_stroke",
    "label_depression",
    "label_diabetes",
    "survey_weight",
]

EXPECTED_MISSING_EPA_STATE_FIPS: frozenset[str] = frozenset({"60", "66", "69"})
EXPECTED_MISSING_EPA_STATE_LABELS: dict[str, str] = {
    "60": "American Samoa",
    "66": "Guam",
    "69": "Northern Mariana Islands",
}


def _available_epa_columns(epa_state_year: pd.DataFrame) -> list[str]:
    """Return required and optional EPA columns that exist in this processed table."""
    return [*EPA_REQUIRED_COLUMNS, *[col for col in EPA_OPTIONAL_COLUMNS if col in epa_state_year]]


def _quality_gate_pollutant_features(joined: pd.DataFrame) -> pd.DataFrame:
    """Mask pollutant values unless their EPA observation-completeness flag is true."""
    out = joined.copy()
    for prefix in POLLUTANT_PREFIXES:
        mean_col = f"{prefix}_mean"
        count_col = f"{prefix}_monitor_count"
        percent_col = f"{prefix}_observation_percent"
        complete_col = f"{prefix}_observation_complete"
        pollutant_cols = [mean_col, count_col, percent_col, complete_col]
        if not all(col in out.columns for col in pollutant_cols):
            continue

        complete = out[complete_col].fillna(False).astype(bool)
        out[complete_col] = complete
        out[count_col] = pd.to_numeric(out[count_col], errors="coerce").fillna(0).astype("Int64")
        out[mean_col] = pd.to_numeric(out[mean_col], errors="coerce").where(complete)
        out[percent_col] = pd.to_numeric(out[percent_col], errors="coerce").where(complete)
    return out


def integrate_brfss_epa(
    brfss_person: pd.DataFrame,
    epa_state_year: pd.DataFrame,
    *,
    allow_missing_aqi: bool,
) -> pd.DataFrame:
    """Join BRFSS v2 person rows with EPA state-year AQI."""
    require_columns(
        actual=brfss_person.columns,
        required=BRFSS_REQUIRED_COLUMNS + BRFSS_V2_REQUIRED_COLUMNS,
        context="BRFSS",
    )
    require_columns(actual=epa_state_year.columns, required=EPA_REQUIRED_COLUMNS, context="EPA")
    epa_columns = _available_epa_columns(epa_state_year)

    joined = brfss_person.merge(
        epa_state_year.loc[:, epa_columns],
        on=["year", "state_fips"],
        how="left",
        validate="many_to_one",
    )
    joined["annual_aqi"] = pd.to_numeric(joined["annual_aqi"], errors="coerce").astype("Int64")
    joined["annual_aqi"] = joined["annual_aqi"].where(
        (joined["annual_aqi"] >= 0) & (joined["annual_aqi"] <= 500)
    )
    joined = _quality_gate_pollutant_features(joined)

    missing = int(joined["annual_aqi"].isna().sum())
    if missing and not allow_missing_aqi:
        missing_states = (
            joined.loc[joined["annual_aqi"].isna(), ["year", "state_fips"]]
            .drop_duplicates()
            .sort_values(["year", "state_fips"])
        )
        unexpected_missing = missing_states.loc[
            ~missing_states["state_fips"].isin(EXPECTED_MISSING_EPA_STATE_FIPS)
        ]
        if not unexpected_missing.empty:
            raise ValueError(
                "Missing annual_aqi after join for "
                f"{missing} rows. Missing state-year keys:\n"
                f"{missing_states.to_string(index=False)}\n"
                "If this is expected (e.g., territories), re-run with --allow-missing-aqi."
            )

    integrated_columns = [col for col in INTEGRATED_COLUMNS if col in joined.columns]
    return joined.loc[:, integrated_columns]


def expected_missing_state_labels(frame: pd.DataFrame) -> list[str]:
    """Return stable human-readable labels for expected missing EPA state/territory keys."""
    labels: list[str] = []
    unique_states = sorted({str(value) for value in frame["state_fips"].dropna().unique().tolist()})
    for state_fips in unique_states:
        label = EXPECTED_MISSING_EPA_STATE_LABELS.get(state_fips, state_fips)
        labels.append(f"{state_fips} ({label})")
    return labels


def build_integrated_tables(
    *,
    base_dir: Path,
    years: list[int],
    force: bool,
    dry_run: bool,
    allow_missing_aqi: bool,
) -> None:
    """Build integrated tables for the requested year(s)."""
    paths = build_ingest_paths(base_dir)
    epa_path = paths.epa_state_year_parquet()
    if not epa_path.exists():
        raise FileNotFoundError(
            f"Missing EPA processed table: {epa_path}. Run build_epa_tables first."
        )
    epa = pd.read_parquet(epa_path)

    for year in years:
        brfss_path = paths.brfss_person_parquet(year)
        if not brfss_path.exists():
            raise FileNotFoundError(
                f"Missing BRFSS processed table: {brfss_path}. Run build_brfss_tables first."
            )

        out_path = paths.integrated_person_year_parquet(year)
        if out_path.exists() and not force:
            print(f"Skip build (exists): {out_path}")
            continue

        brfss = pd.read_parquet(brfss_path)
        epa_year = epa.loc[epa["year"] == year].copy()

        print(f"Integrate: {brfss_path} + {epa_path} -> {out_path}")
        integrated = integrate_brfss_epa(
            brfss,
            epa_year,
            allow_missing_aqi=allow_missing_aqi,
        )

        if dry_run:
            print(f"DRY RUN: would write parquet -> {out_path}")
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            integrated.to_parquet(out_path, index=False)

        missing_aqi_rows = int(integrated["annual_aqi"].isna().sum())
        print(f"Rows written: {len(integrated):,} (annual_aqi nulls: {missing_aqi_rows:,})")
        if missing_aqi_rows:
            missing_states = (
                integrated.loc[integrated["annual_aqi"].isna(), ["year", "state_fips"]]
                .drop_duplicates()
                .sort_values(["year", "state_fips"])
            )
            print(
                "Missing annual_aqi kept for expected state/territory keys: "
                + ", ".join(expected_missing_state_labels(missing_states))
            )

        files: list[FileProvenance] = []
        if brfss_path.exists():
            files.append(collect_file_provenance(brfss_path, root=base_dir))
        if epa_path.exists():
            files.append(collect_file_provenance(epa_path, root=base_dir))
        if out_path.exists():
            files.append(collect_file_provenance(out_path, root=base_dir))

        write_provenance_json(
            paths.provenance_integrated_person_year(year),
            dataset_name="integrated_person_year",
            dataset_version=str(year),
            sources=[],
            files=files,
            extra={
                "rows": len(integrated),
                "annual_aqi_null_rows": missing_aqi_rows,
                "annual_aqi_null_state_fips": (
                    sorted(
                        {
                            str(value)
                            for value in integrated.loc[
                                integrated["annual_aqi"].isna(), "state_fips"
                            ]
                            .dropna()
                            .tolist()
                        }
                    )
                    if missing_aqi_rows
                    else []
                ),
                "allow_missing_aqi": allow_missing_aqi,
            },
            dry_run=dry_run,
        )


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Build integrated BRFSS + EPA training tables using a state-year join."
    )
    add_common_pipeline_args(parser)
    parser.add_argument(
        "--allow-missing-aqi",
        action="store_true",
        help="Allow rows with missing annual_aqi after join (e.g., territories).",
    )
    args = parser.parse_args(argv)
    years = parse_years_from_args(args)
    build_integrated_tables(
        base_dir=Path(args.base_dir),
        years=years,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
        allow_missing_aqi=bool(args.allow_missing_aqi),
    )


if __name__ == "__main__":
    main()
