# Data Dictionary (v2, versioned)

This document defines the raw fields we rely on and the exact transforms used to derive the
processed features/labels consumed by modeling and the API.

It is the "human-readable contract" that complements `docs/schema_contracts.md`.

Status: **v2 pinned to BRFSS 2023 + EPA AirData 2023, with ACS/SVI and CDC PLACES context tables added** (update this doc when the pipeline changes).
Public source metadata is versioned in `conf/data_sources.yaml` and copied into download
provenance JSON under `source_registry`.

## Conventions

- All raw data stays in `data/external/` (gitignored).
- All processed outputs stay in `data/processed/` (gitignored).
- Column names in processed tables should be **snake_case** and stable.
- Keep missingness explicit (document "refused/don't know" handling).

## Data sources

### BRFSS (CDC) 2023 LLCP microdata

- File: `data/external/brfss/2023/LLCP2023.XPT`
- Codebook: `data/external/brfss/2023/codebook/USCODE23_LLCP_*.HTML` (filename varies by CDC release)
- Registry source IDs: `cdc_brfss_llcp_xpt`, `cdc_brfss_llcp_codebook`

### EPA AirData 2023 Annual AQI by county and annual concentration by monitor

- File: `data/external/epa_airdata/annual_aqi_by_county_2023/annual_aqi_by_county_2023.csv`
- File: `data/external/epa_airdata/annual_conc_by_monitor_2023/annual_conc_by_monitor_2023.csv`
- Note: this file provides `State` + `County` names but **no FIPS codes**.
- Note: the annual concentration file provides state/county FIPS plus monitor-level records; local processing filters
  PM2.5 (`Parameter Code == 88101`) and ozone (`Parameter Code == 44201`).
- Registry source IDs: `epa_airdata_annual_aqi_by_county`, `epa_airdata_annual_conc_by_monitor`

## Feature contract (API + training roles)

### Census ACS 5-year curated context variables

- Files:
  - `data/external/acs/acs5/<year>/acs5_state_context.json`
  - `data/external/acs/acs5/<year>/acs5_county_context.json`
- Registry source ID: `census_acs5_api_context`
- Current configured years: ACS 5-year releases 2017-2024 for the curated variable set.

### CDC/ATSDR SVI U.S. county CSV

- File: `data/external/svi/<year>/SVI_<year>_US_county.csv`
- Registry source ID: `cdc_atsdr_svi_us_county_csv`
- Current configured years: 2014, 2016, 2018, 2020, and 2022 for the selected percentile fields.

### CDC PLACES county Open Data

- File: `data/external/places/county/<release-year>/places_county_<release-year>.csv`
- Registry source ID: `cdc_places_county_opendata`
- Current configured release year: 2025.
- Note: PLACES fields are modeled aggregate geography estimates. They are context and external reasonableness references, not independent person-level labels.

## Feature contract (API + training roles)

Scenario-editable inputs remain backward-compatible with the original API and frontend controls.
Adjustment/context covariates are available for model training and artifact inference but are not
required from the frontend.

| Feature | Role | Type | Units/Meaning | Notes |
|---|---|---:|---|---|
| `age` | scenario-editable | int | years (estimated) | derived from `_AGEG5YR` midpoint; validated 18-100 |
| `bmi` | scenario-editable | float | kg/m^2 | `_BMI5 / 100`; validated 10-60 |
| `smoker` | scenario-editable | bool | current smoker | `_SMOKER3` 1/2 true, 3/4 false |
| `alcohol_servings_per_week` | scenario-editable | int | drinks/week (rounded) | `_DRNKWK2` has 2 implied decimals (e.g., 1400=14.00); use `round(_DRNKWK2 / 100)`, clamp 0-70 |
| `exercise_minutes_per_week` | scenario-editable | int | minutes/week | from `PA3MIN_`, clamp 0-2000; round before Int64 cast |
| `annual_aqi` | scenario-editable | int | AQI 0-500 | derived from EPA `Median AQI`, aggregated to state-year |
| `pm25_mean` | scenario-editable environmental | float | micrograms/cubic meter | PM2.5 annual mean from complete EPA annual concentration monitor rows; nullable in data, defaulted in API |
| `ozone_mean` | scenario-editable environmental | float | parts per million | Ozone annual mean from complete EPA annual concentration monitor rows; nullable in data, defaulted in API |
| `sex` | adjustment | string | male/female | `SEXVAR`; nullable for unsupported/missing values |
| `race_ethnicity` | adjustment | string | imputed race/ethnicity category | `_IMPRACE`; nullable for unsupported/missing values |
| `has_healthcare_coverage` | adjustment | bool | any current coverage | from `PRIMINS1` |
| `has_personal_doctor` | adjustment | bool | one or more personal doctors | from `PERSDOC3` |
| `cost_barrier_to_care` | adjustment | bool | needed care but could not see doctor due cost | from `MEDCOST1` |
| `last_checkup_within_year` | adjustment | bool | routine checkup within past year | from `CHECKUP1` |
| `sleep_hours_per_night` | adjustment | int | hours/night | optional `SLEPTIM1`; all null when not present in the supported raw file |
| `physical_health_days` | adjustment with exclusions | int | poor physical health days in past 30 | excluded for physical chronic-condition labels |
| `mental_health_days` | adjustment with exclusions | int | poor mental health days in past 30 | excluded for depression label |
| `survey_weight` | sample weight | float | BRFSS final weight | `_LLCPWT`; used as sample weights, not as a predictor |

## Context feature contract (not scenario-editable)

Context fields are geography-level covariates for modeling, stratification, and provenance displays. They are not user-editable scenario inputs.

Configured fields live in `conf/context_features.yaml`.

| Feature | Type | Units/Meaning | Source/Transform |
|---|---:|---|---|
| `acs_total_population` | int | persons | ACS `B01003_001E`; used for state SVI aggregation weights |
| `acs_poverty_percent` | float | percent | `100 * B17001_002E / B17001_001E` |
| `acs_median_household_income` | float | dollars | ACS `B19013_001E` |
| `acs_bachelors_degree_or_higher_percent` | float | percent | `100 * sum(B15003_022E..B15003_025E) / B15003_001E` |
| `acs_uninsured_percent` | float | percent | `100 * sum(B27010_017E, B27010_033E, B27010_050E, B27010_066E) / B27010_001E` |
| `acs_disability_percent` | float | percent | `100 * summed B18101 disability cells / B18101_001E` |
| `acs_broadband_percent` | float | percent | `100 * B28002_004E / B28002_001E` |
| `svi_overall_percentile` | float | percentile rank 0-1 | SVI `RPL_THEMES`; `-999` -> null |
| `svi_theme1_socioeconomic_percentile` | float | percentile rank 0-1 | SVI `RPL_THEME1`; `-999` -> null |
| `svi_theme2_household_characteristics_percentile` | float | percentile rank 0-1 | SVI `RPL_THEME2`; `-999` -> null |
| `svi_theme3_racial_ethnic_minority_status_percentile` | float | percentile rank 0-1 | SVI `RPL_THEME3`; `-999` -> null |
| `svi_theme4_housing_transportation_percentile` | float | percentile rank 0-1 | SVI `RPL_THEME4`; `-999` -> null |

For every ACS feature above, processed tables also include a boolean `<feature>_moe_available` column. These flags record whether the raw ACS MOE variables required for that feature were present and non-null; the current PR does not derive aggregate MOE values.

### CDC PLACES county context variables

PLACES context fields are county-level modeled aggregate estimates from the CDC PLACES county Open Data release. The table stores crude prevalence percentages and lower/upper confidence limits for the selected measures.

| Feature | Type | Units/Meaning | Source/Transform |
|---|---:|---|---|
| `release_year` | int | PLACES release year | CLI `--year` for the downloaded release |
| `year` | int | latest selected PLACES estimate year | max raw PLACES `year` across selected measures for the county/release |
| `places_estimate_year_min` | int | earliest selected estimate year | min raw PLACES `year` across selected measures |
| `places_estimate_year_max` | int | latest selected estimate year | max raw PLACES `year` across selected measures |
| `state_fips` | string | 2-digit state FIPS | derived from `locationid` |
| `county_fips` | string | 5-digit county FIPS | raw `locationid`, zero-padded |
| `geography_name` | string | county display name | `locationname` + state name |
| `places_total_population` | int | persons | raw `totalpopulation` |
| `places_total_pop_18plus` | int | adults | raw `totalpop18plus`; used for aggregate validation weighting |
| `places_coronary_heart_disease_crude_prevalence` | float | percent | PLACES `CHD`, `datavaluetypeid == CrdPrv` |
| `places_chronic_obstructive_pulmonary_disease_crude_prevalence` | float | percent | PLACES `COPD`, crude prevalence |
| `places_current_asthma_crude_prevalence` | float | percent | PLACES `CASTHMA`, crude prevalence |
| `places_stroke_crude_prevalence` | float | percent | PLACES `STROKE`, crude prevalence |
| `places_depression_crude_prevalence` | float | percent | PLACES `DEPRESSION`, crude prevalence |
| `places_diabetes_crude_prevalence` | float | percent | PLACES `DIABETES`, crude prevalence |
| `places_arthritis_crude_prevalence` | float | percent | PLACES `ARTHRITIS`, crude prevalence |
| `places_current_smoking_crude_prevalence` | float | percent | PLACES `CSMOKING`, crude prevalence |
| `places_binge_drinking_crude_prevalence` | float | percent | PLACES `BINGE`, crude prevalence |
| `places_no_leisure_time_physical_activity_crude_prevalence` | float | percent | PLACES `LPA`, crude prevalence |
| `places_obesity_crude_prevalence` | float | percent | PLACES `OBESITY`, crude prevalence |
| `places_short_sleep_duration_crude_prevalence` | float | percent | PLACES `SLEEP`, crude prevalence |

Each PLACES prevalence feature also has `<feature>_estimate_year`, `<feature>_low`, and `<feature>_high` columns from the raw PLACES estimate year and confidence-limit fields.

## Label contract (conditions)

Processed outputs should include binary label columns aligned to condition IDs in `src/longevity_lab/domain/catalog.py`:

| Condition ID | Label column | Rule (to specify) |
|---|---|---|
| `heart_disease` | `label_heart_disease` | `_MICHD == 1` |
| `chronic_lung_disease` | `label_chronic_lung_disease` | `CHCCOPD3 == 1` |
| `asthma` | `label_asthma` | current asthma from `ASTHMA3` and `ASTHNOW` |
| `stroke` | `label_stroke` | `CVDSTRK3 == 1` |
| `depression` | `label_depression` | `ADDEPEV3 == 1` |
| `diabetes` | `label_diabetes` | `DIABETE4 == 1` |
| `kidney_disease` | `label_kidney_disease` | `CHCKDNY2 == 1` |
| `arthritis` | `label_arthritis` | `HAVARTH4 == 1` |

## Canonical processed tables (v2 targets)

### `brfss_person` (one row per respondent-year)

Path (gitignored):

- `data/processed/brfss/<year>/brfss_person.parquet`

Required columns (v2):

| Column | Type | Nullable | Source | Transform | Notes |
|---|---|---:|---|---|---|
| `year` | int | no | BRFSS | constant | |
| `state_fips` | string | no | BRFSS | `str(int(_STATE)).zfill(2)` | `_STATE` is numeric FIPS |
| `sex` | string | yes | BRFSS | decode `SEXVAR` | 1->`male`, 2->`female`, else null |
| `race_ethnicity` | string | yes | BRFSS | decode `_IMPRACE` | see mapping below |
| `age` | int | yes | BRFSS | decode `_AGEG5YR` | midpoint mapping (see below) |
| `bmi` | float | yes | BRFSS | decode `_BMI5` | `_BMI5==9999` -> null; else `_BMI5/100` |
| `smoker` | bool | yes | BRFSS | decode `_SMOKER3` | `True` if 1/2; `False` if 3/4; 9/null -> null |
| `alcohol_servings_per_week` | int | yes | BRFSS | decode `_DRNKWK2` | 0->0; 99900/null->null; else `round(_DRNKWK2/100)`; clamp 0-70 (2 implied decimals) |
| `exercise_minutes_per_week` | int | yes | BRFSS | decode `PA3MIN_` | blank->null; `0-99999` valid; treat `>99999` as null; clamp 0-2000 |
| `has_healthcare_coverage` | bool | yes | BRFSS | decode `PRIMINS1` | 1-10->true, 88->false, 77/99/blank->null |
| `has_personal_doctor` | bool | yes | BRFSS | decode `PERSDOC3` | 1/2->true, 3->false, 7/9/blank->null |
| `cost_barrier_to_care` | bool | yes | BRFSS | decode `MEDCOST1` | 1->true, 2->false, 7/9/blank->null |
| `last_checkup_within_year` | bool | yes | BRFSS | decode `CHECKUP1` | 1->true, 2/3/4/8->false, 7/9/blank->null |
| `sleep_hours_per_night` | int | yes | BRFSS | decode optional `SLEPTIM1` | 0-24 valid, 77/99/blank->null; all null when absent |
| `physical_health_days` | int | yes | BRFSS | decode `PHYSHLTH` | 1-30 days, 88->0, 77/99/blank->null |
| `mental_health_days` | int | yes | BRFSS | decode `MENTHLTH` | 1-30 days, 88->0, 77/99/blank->null |
| `label_heart_disease` | int (0/1) | yes | BRFSS | decode `_MICHD` | 1->1, 2->0, blank->null |
| `label_chronic_lung_disease` | int (0/1) | yes | BRFSS | decode `CHCCOPD3` | 1->1, 2->0, 7/9/blank->null |
| `label_asthma` | int (0/1) | yes | BRFSS | decode `ASTHMA3` + `ASTHNOW` | current asthma yes -> 1; never asthma or not current -> 0; unknown/refused -> null when unresolved |
| `label_stroke` | int (0/1) | yes | BRFSS | decode `CVDSTRK3` | 1->1, 2->0, 7/9/blank->null |
| `label_depression` | int (0/1) | yes | BRFSS | decode `ADDEPEV3` | 1->1, 2->0, 7/9/blank->null |
| `label_diabetes` | int (0/1) | yes | BRFSS | decode `DIABETE4` | 1->1, 3->0; 2/4 treated as 0; 7/9/blank->null |
| `label_kidney_disease` | int (0/1) | yes | BRFSS | decode `CHCKDNY2` | 1->1, 2->0, 7/9/blank->null |
| `label_arthritis` | int (0/1) | yes | BRFSS | decode `HAVARTH4` | 1->1, 2->0, 7/9/blank->null |
| `survey_weight` | float | yes | BRFSS | passthrough `_LLCPWT` | final raked weight; sample weight only |

#### BRFSS v2 decode details (2023)

Age (`_AGEG5YR` -> `age` midpoint):

| `_AGEG5YR` | Range | `age` |
|---:|---|---:|
| 1 | 18-24 | 21 |
| 2 | 25-29 | 27 |
| 3 | 30-34 | 32 |
| 4 | 35-39 | 37 |
| 5 | 40-44 | 42 |
| 6 | 45-49 | 47 |
| 7 | 50-54 | 52 |
| 8 | 55-59 | 57 |
| 9 | 60-64 | 62 |
| 10 | 65-69 | 67 |
| 11 | 70-74 | 72 |
| 12 | 75-79 | 77 |
| 13 | 80-99 | 90 |
| 14 | DK/Refused/Missing | null |

Notes:

- LLCP2023 does not include a usable county/FIPS column, so **county-level joins are not possible** from BRFSS alone.
- The 2023 variable layout used by the current annual LLCP source does not list `SLEPTIM1`.
  `sleep_hours_per_night` is kept in the v2 schema as a nullable optional field; the builder decodes
  it if a supported 2023 release includes it and otherwise emits nulls.

Race/ethnicity (`_IMPRACE` -> `race_ethnicity`):

| `_IMPRACE` | `race_ethnicity` |
|---:|---|
| 1 | `white_non_hispanic` |
| 2 | `black_non_hispanic` |
| 3 | `asian_non_hispanic` |
| 4 | `aian_non_hispanic` |
| 5 | `hispanic` |
| 6 | `other_non_hispanic` |

Leakage exclusions:

- `physical_health_days` is excluded from heart disease, chronic lung disease, asthma, stroke,
  diabetes, chronic kidney disease, and arthritis models because recent poor physical health can be
  a symptom or consequence of those labels.
- `mental_health_days` is excluded from depression models because recent poor mental health overlaps
  the depression outcome construct.
- `survey_weight` is used only as a sample weight in training/evaluation and is not included in the
  model feature matrix.

### `epa_county_year` (one row per county-year where EPA AQI or pollutant data exist)

Path (gitignored):

- `data/processed/epa_airdata/epa_county_year.parquet`

Required columns (EPA pollutant expansion):

| Column | Type | Nullable | Source | Transform | Notes |
|---|---|---:|---|---|---|
| `year` | int | no | EPA | parse | |
| `state_fips` | string | no | EPA | map `State` name or use `State Code` | |
| `county_fips` | string | yes | EPA annual concentration | `State Code` + `County Code` | AQI-only counties can be null because annual AQI lacks FIPS |
| `county_name` | string | yes | EPA | passthrough | used to align AQI rows to monitor rows when FIPS is unavailable |
| `annual_aqi` | int | yes | EPA annual AQI | county `Median AQI`, clamped 0-500 | |
| `aqi_days_with_aqi` | int | yes | EPA annual AQI | `Days with AQI` | |
| `aqi_observation_complete` | bool | no | EPA annual AQI | true when `Days with AQI >= 274` | 75% of a non-leap year |
| `pm25_mean` | float | yes | EPA annual concentration | observation-count-weighted `Arithmetic Mean` | only from quality-passing PM2.5 monitors |
| `pm25_monitor_count` | int | no | EPA annual concentration | unique complete PM2.5 monitors | 0 when no quality-passing monitors |
| `pm25_observation_percent` | float | yes | EPA annual concentration | observation-count-weighted percent | null when incomplete |
| `pm25_observation_complete` | bool | no | EPA annual concentration | true when at least one PM2.5 monitor passes quality checks | |
| `ozone_mean` | float | yes | EPA annual concentration | observation-count-weighted `Arithmetic Mean` | only from quality-passing ozone monitors |
| `ozone_monitor_count` | int | no | EPA annual concentration | unique complete ozone monitors | 0 when no quality-passing monitors |
| `ozone_observation_percent` | float | yes | EPA annual concentration | observation-count-weighted percent | null when incomplete |
| `ozone_observation_complete` | bool | no | EPA annual concentration | true when at least one ozone monitor passes quality checks | |

Pollutant monitor quality checks:

- `Completeness Indicator == "Y"`
- `Observation Percent >= 75`
- `Observation Count > 0`
- `Arithmetic Mean` is non-null

### `epa_aqi_state_year` (one row per state-year)

Path (gitignored):

- `data/processed/epa_airdata/annual_aqi_state_year.parquet`

Required columns (EPA pollutant expansion):

| Column | Type | Nullable | Source | Transform | Notes |
|---|---|---:|---|---|---|
| `year` | int | no | EPA | parse | |
| `state_fips` | string | no | EPA | map `State` name -> FIPS | static mapping table (50 states + DC + territories as needed) |
| `annual_aqi` | int | no | EPA | aggregate + clamp | v1 = `round(weighted_mean(county['Median AQI'], weights='Days with AQI'))`, clamp 0-500 |
| `pm25_mean` | float | yes | `epa_county_year` | monitor-count-weighted state mean | null when no complete PM2.5 counties |
| `pm25_monitor_count` | int | no | `epa_county_year` | sum of complete PM2.5 monitors | |
| `pm25_observation_percent` | float | yes | `epa_county_year` | monitor-count-weighted state percent | |
| `pm25_observation_complete` | bool | no | `epa_county_year` | true when monitor count > 0 | |
| `ozone_mean` | float | yes | `epa_county_year` | monitor-count-weighted state mean | null when no complete ozone counties |
| `ozone_monitor_count` | int | no | `epa_county_year` | sum of complete ozone monitors | |
| `ozone_observation_percent` | float | yes | `epa_county_year` | monitor-count-weighted state percent | |
| `ozone_observation_complete` | bool | no | `epa_county_year` | true when monitor count > 0 | |

Notes:

- EPA raw file has no FIPS. We compute `state_fips` by mapping `State` name to its FIPS code.
- We aggregate from county rows to state-year because BRFSS 2023 does not expose county identifiers.
- `annual_aqi` is retained with the same name and state-year semantics for backwards compatibility.
- EPA 2023 does not include a Guam state row. The integrated table therefore keeps BRFSS Guam rows
  with `annual_aqi = null` by default while still failing on unexpected missing joins.

### `integrated_person_year` (one row per respondent-year)

Path (gitignored):

- `data/processed/integrated/<year>/integrated_person_year.parquet`

This is the modeling table. It must include:

- `brfss_person` required columns
- plus the integrated `annual_aqi`
- plus quality-gated pollutant columns when present in the EPA state-year table:
  `pm25_mean`, `pm25_monitor_count`, `pm25_observation_percent`, `pm25_observation_complete`,
  `ozone_mean`, `ozone_monitor_count`, `ozone_observation_percent`, `ozone_observation_complete`
- plus curated ACS/SVI state-year context columns when
  `data/processed/context/context_state_year.parquet` is available
- plus `context_data_year` when ACS/SVI context is joined from an explicit or exact context
  vintage
- plus stable join keys used

Join caveat:

- `annual_aqi` may be null for documented EPA coverage gaps in BRFSS territories (currently Guam,
  `state_fips=66` for 2023). This is expected and preserved in provenance.

### `context_county_year` (one row per county-year)

Path (gitignored):

- `data/processed/context/context_county_year.parquet`

Required columns:

- Join keys and labels: `year`, `state_fips`, `county_fips`, `geography_name`
- Context feature columns listed in the context feature contract above
- ACS MOE availability flags: `<acs_feature>_moe_available`

### `context_state_year` (one row per state-year)

Path (gitignored):

- `data/processed/context/context_state_year.parquet`

Required columns:

- Join keys and labels: `year`, `state_fips`, `geography_name`
- ACS state-level context feature columns derived directly from ACS state API rows
- SVI columns aggregated from county rows as population-weighted means using `acs_total_population`
- ACS MOE availability flags: `<acs_feature>_moe_available`

State-level SVI values are compact descriptive context only. They are not CDC/ATSDR state-specific SVI ranks.

Serving contract:

- The API exposes explicit state-year geography selection through `GET /api/context/geographies`
  and optional `geography` metadata on scenario-compare requests.
- The serving geography level is state only. County-level ACS/SVI and PLACES rows remain
  context, validation, or future-map data because BRFSS 2023 LLCP person rows do not expose county
  identifiers.
- Geography context is not scenario-editable behavior. Selecting a state changes artifact-backed
  scores only when the trusted artifact manifest declares exact state-year context features,
  source IDs, join keys, data vintage, caveats, defaults, and a bundle-local lookup asset. Demo
  mode and artifacts without that manifest metadata do not activate ACS/SVI context.

### `places_county_year` (one row per county per PLACES release)

Path (gitignored):

- `data/processed/places/places_county_year.parquet`

Required columns:

- Join keys and labels: `release_year`, `year`, `state_fips`, `state_abbr`, `state_name`, `county_fips`, `county_name`, `geography_name`
- Population fields: `places_total_population`, `places_total_pop_18plus`
- PLACES selected crude prevalence fields and confidence-limit fields listed above

PLACES is not joined into the current person-year table because BRFSS 2023 LLCP does not expose county identifiers. Use it as county context and for aggregate reasonableness reports only.

### `places_external_context_validation` report

Paths (gitignored):

- `data/processed/validation/places_external_context_validation_<release-year>.csv`
- `data/processed/validation/places_external_context_validation_<release-year>.json`

This report compares aggregate model risk patterns with population-weighted PLACES crude prevalence estimates at the model geography available in the input (`county_fips`, `state_fips`, or national). It records:

- `condition_id` and PLACES `measureid`
- `model_mean_predicted_probability`
- `places_crude_prevalence` and `places_crude_prevalence_probability`
- absolute and relative differences
- a caveat that PLACES estimates are modeled aggregate context, not independent person-level labels

## Join strategy (must be documented and tested)

V2 joins by **state-year**, with an explicit context-vintage override when needed:

- BRFSS key: (`state_fips`, `year`)
- EPA key: (`state_fips`, `year`)
- ACS/SVI state context key: (`state_fips`, `year`) by default.
- ACS/SVI explicit context-vintage key: `state_fips` after filtering the processed context table to
  `--context-year`; the output records this value in `context_data_year`.

Rationale:

- BRFSS 2023 LLCP microdata does not contain county/FIPS identifiers.
- EPA annual AQI file does not contain FIPS identifiers; it provides state/county names only.
- Current BRFSS rows can join ACS/SVI context only at state-year granularity. County-level context
  remains non-serving context or validation data.
- SVI is currently registry-supported through the 2022 release. When building 2023 BRFSS artifacts
  with 2022 ACS/SVI context, the integrated build must use `--context-year 2022` so context vintage
  is explicit and auditable.

## Provenance format (v2, implemented)

ACS/SVI context tables are built separately:

- County context key: (`county_fips`, `year`)
- State context key: (`state_fips`, `year`)
- Current BRFSS person rows can only join context by (`state_fips`, `year`) unless a future BRFSS contract exposes county identifiers.

## Provenance format (v2, implemented)

Pipeline commands emit a machine-readable provenance JSON under `data/processed/provenance/`
(gitignored). Filenames are stable and keyed by dataset and year(s):

- `brfss_raw_<year>.json` (`download_brfss`)
- `brfss_person_<year>.json` (`build_brfss_tables`)
- `epa_airdata_annual_aqi_by_county_<year>.json` (`download_epa_airdata`)
- `epa_airdata_annual_aqi_state_year_<years>.json` (`build_epa_tables`, where `<years>` is
  `2021_2022_2023` for `--years 2021,2022,2023`)
- `integrated_person_year_<year>.json` (`build_integrated_tables`)
- `census_acs5_state_context_raw_<year>.json` (`download_acs`)
- `census_acs5_county_context_raw_<year>.json` (`download_acs`)
- `cdc_atsdr_svi_us_county_raw_<year>.json` (`download_svi`)
- `context_tables_<years>.json` (`build_context_tables`)
- `cdc_places_county_raw_<release-year>.json` (`download_places`)
- `places_county_year_<release-years>.json` (`build_places_tables`)
- `places_external_context_validation_<release-year>.json` (`validate_external_context`)

Payload fields (see `src/longevity_lab/pipeline/common.py`):

- `dataset_name`
- `dataset_version`
- `retrieved_at` (UTC ISO timestamp)
- `sources` (URLs)
- `files`: list of
  - `path` (relative to `data/`)
  - `bytes`
  - `sha256`
  - `url` (optional; present for downloaded files)
- plus dataset-specific extras (e.g., row counts, null counts, dropped rows) at the top level.
- `source_registry` for registry-backed download steps, including source IDs, official URLs,
  concrete download URLs, expected file patterns, checksum policy, license notes, geography, and
  local landing paths.

Note: provenance JSON is written under `data/processed/` and is therefore gitignored. Future report
scripts should copy or summarize the relevant provenance into generated report outputs.
