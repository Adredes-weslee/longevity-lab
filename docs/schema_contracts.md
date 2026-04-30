# Schema Contracts (downstream contracts)

This document defines the minimum tables/files that downstream components (modeling, API, UI) can depend on.

It is intentionally smaller than `docs/data_dictionary.md`.

Status: **v1 contracts** (BRFSS 2023 + EPA 2023, state-year join).

If you change any contract here, update:

- `docs/data_dictionary.md`
- `src/longevity_lab/api/schemas.py` if the API is affected
- tests covering the pipeline/API/UI contract boundaries

## Processed tables (files)

All of these are **gitignored** outputs written under `data/processed/`.

### `brfss_person.parquet`

- Path: `data/processed/brfss/<year>/brfss_person.parquet`
- Granularity: one row per respondent-year
- Required columns:
  - `year`, `state_fips`
  - feature columns: `age`, `bmi`, `smoker`, `alcohol_servings_per_week`, `exercise_minutes_per_week`
  - label columns: `label_heart_disease`, `label_chronic_lung_disease`, `label_stroke`,
    `label_depression`, `label_diabetes`
  - `survey_weight`

### `annual_aqi_state_year.parquet`

- Path: `data/processed/epa_airdata/annual_aqi_state_year.parquet`
- Granularity: one row per state-year
- Required columns:
  - `year`, `state_fips`, `annual_aqi`

### `integrated_person_year.parquet`

- Path: `data/processed/integrated/<year>/integrated_person_year.parquet`
- Granularity: one row per respondent-year
- Required columns:
  - all `brfss_person` required columns
  - plus `annual_aqi`

## DuckDB (optional convenience)

DuckDB outputs are also gitignored. If used, the canonical DB file is:

- `data/processed/longevity_lab.duckdb`

Stable views:

- `v_brfss_person`
- `v_epa_aqi_state_year`
- `v_integrated_person_year`

Each view must match the corresponding parquet schema exactly.
