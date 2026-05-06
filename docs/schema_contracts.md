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
  - label columns: `label_heart_disease`, `label_chronic_lung_disease`, `label_asthma`,
    `label_stroke`, `label_depression`, `label_diabetes`, `label_kidney_disease`,
    `label_arthritis`
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
  - plus curated ACS/SVI state-year context columns when
    `data/processed/context/context_state_year.parquet` is present

## BRFSS v2 feature roles

Training uses the union of scenario-editable, adjustment, and manifest-gated context features, with
condition-specific exclusions to avoid symptom-like label leakage:

- Scenario-editable: `age`, `bmi`, `smoker`, `alcohol_servings_per_week`,
  `exercise_minutes_per_week`
- Scenario-editable environmental features from EPA join: `annual_aqi`, `pm25_mean`, and
  `ozone_mean`
- BRFSS adjustment covariates: `sex`, `race_ethnicity`, `has_healthcare_coverage`,
  `has_personal_doctor`, `cost_barrier_to_care`, `last_checkup_within_year`,
  `sleep_hours_per_night`, `physical_health_days`, `mental_health_days`
- State-year ACS/SVI context features: `acs_total_population`, `acs_poverty_percent`,
  `acs_median_household_income`, `acs_bachelors_degree_or_higher_percent`,
  `acs_uninsured_percent`, `acs_disability_percent`, `acs_broadband_percent`,
  `svi_overall_percentile`, `svi_theme1_socioeconomic_percentile`,
  `svi_theme2_household_characteristics_percentile`,
  `svi_theme3_racial_ethnic_minority_status_percentile`, and
  `svi_theme4_housing_transportation_percentile`.
- Survey weights: `survey_weight` is a sample-weight column, not a prediction feature.
- Leakage exclusions:
  - `physical_health_days` is excluded when training heart disease, chronic lung disease,
    asthma, stroke, diabetes, chronic kidney disease, and arthritis labels.
  - `mental_health_days` is excluded when training the depression label.

The public API remains backward-compatible: existing scenario requests can keep sending the
original editable fields, including `annual_aqi`. Non-editable BRFSS v2 covariates are not accepted
in public scenario payloads; artifact inference fills them from persisted preprocessing defaults so
direct clients cannot create scenario deltas by changing adjustment fields.

`GET /api/evidence/status` exposes the comprehensive evidence contract used by the Data Evidence
page: public source roles, local asset readiness, generated reports, production artifact download
configuration, active-vs-available feature inventory, active state-year ACS/SVI context only when
the artifact manifest declares context lookup provenance, and explicitly inactive gaps such as
county-level context.

## API contract v2

`GET /api/metadata/bootstrap` and `POST /api/scenario/compare` include
`contract_version: "v2"` and a shared `model_metadata` object. These fields are additive so v1-style
clients that read the original organs, conditions, runtime, and scenario scores can continue to work.

`model_metadata` exposes:

- `model_mode`: `demo` or `artifact`, matching the active scorer.
- `artifact_id`: the selected local bundle id when artifact-backed scoring is active.
- `data_vintage`, `dataset_name`, `dataset_version`, and `dataset_retrieved_at`: provenance copied
  from the active artifact manifest, or explicit demo values when no artifact is active.
- `explanation_methods`: explanation methods whose artifact paths are present in the active bundle.
  A condition can still return an empty `explanations` list when no qualifying rule-path split or
  attribution is available for the current row.
- `uncertainty_available` and `uncertainty_methods`: whether calibrated uncertainty summaries are
  available from the active artifact bundle.
- `contextual_geography`: the geographic context levels inferred from artifact features, such as
  state-level AQI or manifest-declared state-year ACS/SVI context. This object also includes
  `feature_count`, `features`, and `caveat`. County-level prediction semantics are not exposed
  because BRFSS person rows only support state-year serving joins.

`GET /api/metadata/bootstrap` also includes a `geography` object for explicit serving context:

- `supported_levels`: currently `["state"]`.
- `default_year`: the default context lookup year, currently `2023`.
- `context_lookup_active`: whether a processed state-year context table is readable for the
  default year.
- `geographies_endpoint`: the relative route for geography options.
- `caveat`: copy stating that geography context is background context, not a personal behavior.

`GET /api/context/geographies?year=2023` returns selectable state-year context options:

- `selected_year`
- `supported_levels`: currently `["state"]`
- `options`: state rows with `level`, `state_fips`, `label`, `year`, and `context_available`
- `readiness`: `active`, `table_exists`, `year_available`, safe relative `table_path`,
  `state_count`, `available_years`, and `message`

When `data/processed/context/context_state_year.parquet` is missing or unreadable, the endpoint
returns fallback state options with `context_available: false` and never exposes absolute local
paths.

`POST /api/scenario/compare` accepts optional `geography` metadata with `level: "state"`,
`state_fips`, and `year`. Existing requests without geography remain valid. Demo scoring ignores
geography. Artifact scoring injects ACS/SVI state-year context only when the active manifest
declares `context_features` metadata with exact feature names, source IDs, join keys, data vintage,
caveats, defaults, and a trusted bundle-local lookup path. If geography is missing or absent from
the lookup, the engine uses manifest-declared defaults.

`GET /api/models/cards` exposes model-card metrics for the same active model contract:

- `available`: whether trusted local metrics files were found for the active artifact bundle.
- `artifact_id`: the active relative bundle id, including nested path segments when applicable.
- `condition_cards`: per-condition rows with `rows_total`, train/test row counts, positive rate,
  feature count, context feature count/list, calibrated/base/no-context/no-AQI/no-pollutants
  metric sets, best tree parameters, and average-precision deltas for context, AQI, and pollutant
  ablations.

When demo mode is active or the active artifact has no readable metrics files, the endpoint returns
`available: false` instead of failing the UI.

Frontend pages must keep contextual geography visible as a separate background-context layer:

- Explorer shows the selected state/year, lookup readiness, active-vs-inactive model status,
  context feature count/list, data vintage, and caveat outside the editable scenario controls.
- Data Evidence groups active state-year context, inactive county context, and validation-only
  PLACES evidence separately from personal scenario inputs.
- Model Cards show context ablation lift, context feature lists, and subgroup caveats when
  artifact metrics are available.
- Scenario Lab includes geography/context rows in the export-style scenario summary.

## Scenario response explanations and uncertainty

`POST /api/scenario/compare` condition responses include:

- `key_drivers`: backwards-compatible display labels for the top explanation items.
- `explanations`: typed records with `feature`, `display_name`, `direction`, `magnitude`,
  `method`, and `caveat`.
- `uncertainty`: `null` unless the artifact manifest declares `uncertainty_method` and a
  bundle-local uncertainty payload exists. `calibration_interval` responses include lower/upper
  bounds, optional confidence level, caveat text, and calibration diagnostics from the artifact
  payload.

Explanation methods must match the artifact:

- `demo`: heuristic demo-mode contribution, not a trained-model explanation.
- `tree_path`: decision-tree split path from the saved explanation artifact.
- `shap`: TreeSHAP attribution from a tree-ensemble explanation artifact when the optional SHAP
  runtime is installed. SHAP artifacts must be manifest-declared and use compact background samples;
  if the optional runtime is missing, scoring returns no SHAP records rather than fabricating
  drivers.

Uncertainty intervals are artifact-declared calibration summaries for communication, not clinical
confidence intervals for an individual. The training pipeline writes them from held-out empirical
residual quantiles when enough validation rows are available.

## Shared disclaimer contract

The frontend keeps repeated safety language in `frontend/src/content/disclaimers.ts`. Pages that
show scores, model metadata, evidence assets, scenario exports, or public-health links should reuse
that shared copy instead of creating divergent warnings.

Required interpretation boundaries:

- Scores and probabilities are educational predictive estimates, not diagnosis, screening,
  treatment guidance, emergency triage, or personalized medical advice.
- Scenario deltas are predictive comparisons, not causal claims.
- Geography, environmental, ACS/SVI, and validation-context fields are background context unless a
  trusted artifact explicitly declares active context features.
- Uncertainty intervals are model communication summaries, not clinical confidence intervals.
- Public-health guidance links are general cited resources and do not replace clinicians.
- Artifact bundles are trusted local or SHA-verified release outputs only. The API must not accept
  arbitrary uploaded bundle paths or unverified remote joblib artifacts.

## DuckDB (optional convenience)

DuckDB outputs are also gitignored. If used, the canonical DB file is:

- `data/processed/longevity_lab.duckdb`

Stable views:

- `v_brfss_person`
- `v_epa_aqi_state_year`
- `v_integrated_person_year`

Each view must match the corresponding parquet schema exactly.
