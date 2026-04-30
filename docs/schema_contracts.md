# Schema Contracts (downstream contracts)

This document defines the minimum tables/files that downstream components (modeling, API, UI) can depend on.

It is intentionally smaller than `docs/data_dictionary.md`.

Status: **v2 contracts** (BRFSS 2023 + EPA 2023, state-year join).

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
  - scenario-editable feature columns: `age`, `bmi`, `smoker`,
    `alcohol_servings_per_week`, `exercise_minutes_per_week`
  - adjustment/context columns: `sex`, `race_ethnicity`, `has_healthcare_coverage`,
    `has_personal_doctor`, `cost_barrier_to_care`, `last_checkup_within_year`,
    `sleep_hours_per_night`, `physical_health_days`, `mental_health_days`
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

## BRFSS v2 feature roles

Training uses the union of scenario-editable, adjustment, and context features, with
condition-specific exclusions to avoid symptom-like label leakage:

- Scenario-editable: `age`, `bmi`, `smoker`, `alcohol_servings_per_week`,
  `exercise_minutes_per_week`
- Scenario-editable environmental feature from EPA join: `annual_aqi`
- BRFSS adjustment covariates: `sex`, `race_ethnicity`, `has_healthcare_coverage`,
  `has_personal_doctor`, `cost_barrier_to_care`, `last_checkup_within_year`,
  `sleep_hours_per_night`, `physical_health_days`, `mental_health_days`
- Survey weights: `survey_weight` is a sample-weight column, not a prediction feature.
- Leakage exclusions:
  - `physical_health_days` is excluded when training heart disease, chronic lung disease,
    stroke, and diabetes labels.
  - `mental_health_days` is excluded when training the depression label.

The public API remains backward-compatible: existing scenario requests can keep sending the
original editable fields, including `annual_aqi`. Non-editable BRFSS v2 covariates are not accepted
in public scenario payloads; artifact inference fills them from persisted preprocessing defaults so
direct clients cannot create scenario deltas by changing adjustment fields.

## Scenario response explanations and uncertainty

`POST /api/scenario/compare` condition responses include:

- `key_drivers`: backwards-compatible display labels for the top explanation items.
- `explanations`: typed records with `feature`, `display_name`, `direction`, `magnitude`,
  `method`, and `caveat`.
- `uncertainty`: `null` unless the artifact manifest declares `uncertainty_method`.

Explanation methods must match the artifact:

- `demo`: heuristic demo-mode contribution, not a trained-model explanation.
- `tree_path`: decision-tree split path from the saved explanation artifact.
- `shap`: TreeSHAP attribution from a tree-ensemble explanation artifact when the optional SHAP
  runtime is installed.

Uncertainty intervals are artifact-declared calibration summaries for communication, not clinical
confidence intervals for an individual.

## DuckDB (optional convenience)

DuckDB outputs are also gitignored. If used, the canonical DB file is:

- `data/processed/longevity_lab.duckdb`

Stable views:

- `v_brfss_person`
- `v_epa_aqi_state_year`
- `v_integrated_person_year`

Each view must match the corresponding parquet schema exactly.
