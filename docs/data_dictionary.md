# Data Dictionary (v1, versioned)

This document defines the raw fields we rely on and the exact transforms used to derive the
processed features/labels consumed by modeling and the API.

It is the "human-readable contract" that complements `docs/schema_contracts.md`.

Status: **v1 pinned to BRFSS 2023 + EPA AirData 2023** (update this doc when the pipeline changes).
Public source metadata is versioned in `conf/data_sources.yaml` and copied into download
provenance JSON under `source_registry`.

## Conventions

- All raw data stays in `data/external/` (gitignored).
- All processed outputs stay in `data/processed/` (gitignored).
- Column names in processed tables should be **snake_case** and stable.
- Keep missingness explicit (document "refused/don't know" handling).

## Data sources (v1)

### BRFSS (CDC) 2023 LLCP microdata

- File: `data/external/brfss/2023/LLCP2023.XPT`
- Codebook: `data/external/brfss/2023/codebook/USCODE23_LLCP_*.HTML` (filename varies by CDC release)
- Registry source IDs: `cdc_brfss_llcp_xpt`, `cdc_brfss_llcp_codebook`

### EPA AirData 2023 Annual AQI by county

- File: `data/external/epa_airdata/annual_aqi_by_county_2023/annual_aqi_by_county_2023.csv`
- Note: this file provides `State` + `County` names but **no FIPS codes**.
- Registry source ID: `epa_airdata_annual_aqi_by_county`

## Feature contract (must match API)

These must exist in the integrated table and match the API schema in `src/longevity_lab/api/schemas.py`:

| Feature | Type | Units/Meaning | Notes |
|---|---:|---|---|
| `age` | int | years (estimated) | derived from `_AGEG5YR` midpoint; validated 18-100 |
| `bmi` | float | kg/m^2 | `_BMI5 / 100`; validated 10-60 |
| `smoker` | bool | current smoker | rule must be explicit |
| `alcohol_servings_per_week` | int | drinks/week (rounded) | `_DRNKWK2` has 2 implied decimals (e.g., 1400=14.00); use `round(_DRNKWK2 / 100)`, clamp 0-70 |
| `exercise_minutes_per_week` | int | minutes/week | from `PA3MIN_`, clamp 0-2000; round before Int64 cast |
| `annual_aqi` | int | AQI 0-500 | derived from EPA `Median AQI`, aggregated to state-year |

## Label contract (conditions)

Processed outputs should include binary label columns aligned to condition IDs in `src/longevity_lab/domain/catalog.py`:

| Condition ID | Label column | Rule (to specify) |
|---|---|---|
| `heart_disease` | `label_heart_disease` | `_MICHD == 1` |
| `chronic_lung_disease` | `label_chronic_lung_disease` | `CHCCOPD3 == 1` |
| `stroke` | `label_stroke` | `CVDSTRK3 == 1` |
| `depression` | `label_depression` | `ADDEPEV3 == 1` |
| `diabetes` | `label_diabetes` | `DIABETE4 == 1` |

## Canonical processed tables (v1 targets)

### `brfss_person` (one row per respondent-year)

Path (gitignored):

- `data/processed/brfss/<year>/brfss_person.parquet`

Required columns (v1):

| Column | Type | Nullable | Source | Transform | Notes |
|---|---|---:|---|---|---|
| `year` | int | no | BRFSS | constant | |
| `state_fips` | string | no | BRFSS | `str(int(_STATE)).zfill(2)` | `_STATE` is numeric FIPS |
| `age` | int | yes | BRFSS | decode `_AGEG5YR` | midpoint mapping (see below) |
| `bmi` | float | yes | BRFSS | decode `_BMI5` | `_BMI5==9999` -> null; else `_BMI5/100` |
| `smoker` | bool | yes | BRFSS | decode `_SMOKER3` | `True` if 1/2; `False` if 3/4; 9/null -> null |
| `alcohol_servings_per_week` | int | yes | BRFSS | decode `_DRNKWK2` | 0->0; 99900/null->null; else `round(_DRNKWK2/100)`; clamp 0-70 (2 implied decimals) |
| `exercise_minutes_per_week` | int | yes | BRFSS | decode `PA3MIN_` | blank->null; `0-99999` valid; treat `>99999` as null; clamp 0-2000 |
| `label_heart_disease` | int (0/1) | yes | BRFSS | decode `_MICHD` | 1->1, 2->0, blank->null |
| `label_chronic_lung_disease` | int (0/1) | yes | BRFSS | decode `CHCCOPD3` | 1->1, 2->0, 7/9/blank->null |
| `label_stroke` | int (0/1) | yes | BRFSS | decode `CVDSTRK3` | 1->1, 2->0, 7/9/blank->null |
| `label_depression` | int (0/1) | yes | BRFSS | decode `ADDEPEV3` | 1->1, 2->0, 7/9/blank->null |
| `label_diabetes` | int (0/1) | yes | BRFSS | decode `DIABETE4` | 1->1, 3->0; 2/4 treated as 0; 7/9/blank->null |
| `survey_weight` | float | yes | BRFSS | passthrough `_LLCPWT` | final raked weight |

#### BRFSS v1 decode details (2023)

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
- We removed `sleep_hours_per_night` from the v1 contract because it is not present in LLCP2023.

### `epa_aqi_state_year` (one row per state-year)

Path (gitignored):

- `data/processed/epa_airdata/annual_aqi_state_year.parquet`

Required columns (v1):

| Column | Type | Nullable | Source | Transform | Notes |
|---|---|---:|---|---|---|
| `year` | int | no | EPA | parse | |
| `state_fips` | string | no | EPA | map `State` name -> FIPS | static mapping table (50 states + DC + territories as needed) |
| `annual_aqi` | int | no | EPA | aggregate + clamp | v1 = `round(weighted_mean(county['Median AQI'], weights='Days with AQI'))`, clamp 0-500 |

Notes:

- EPA raw file has no FIPS. We compute `state_fips` by mapping `State` name to its FIPS code.
- We aggregate from county rows to state-year because BRFSS 2023 does not expose county identifiers.
- EPA 2023 does not include a Guam state row. The integrated table therefore keeps BRFSS Guam rows
  with `annual_aqi = null` by default while still failing on unexpected missing joins.

### `integrated_person_year` (one row per respondent-year)

Path (gitignored):

- `data/processed/integrated/<year>/integrated_person_year.parquet`

This is the modeling table. It must include:

- `brfss_person` required columns
- plus the integrated `annual_aqi`
- plus stable join keys used

Join caveat:

- `annual_aqi` may be null for documented EPA coverage gaps in BRFSS territories (currently Guam,
  `state_fips=66` for 2023). This is expected and preserved in provenance.

## Join strategy (must be documented and tested)

V1 joins by **state-year**:

- BRFSS key: (`state_fips`, `year`)
- EPA key: (`state_fips`, `year`)

Rationale:

- BRFSS 2023 LLCP microdata does not contain county/FIPS identifiers.
- EPA annual AQI file does not contain FIPS identifiers; it provides state/county names only.

## Provenance format (v1, implemented)

Pipeline commands emit a machine-readable provenance JSON under `data/processed/provenance/`
(gitignored). Filenames are stable and keyed by dataset and year(s):

- `brfss_raw_<year>.json` (`download_brfss`)
- `brfss_person_<year>.json` (`build_brfss_tables`)
- `epa_airdata_annual_aqi_by_county_<year>.json` (`download_epa_airdata`)
- `epa_airdata_annual_aqi_state_year_<years>.json` (`build_epa_tables`, where `<years>` is
  `2021_2022_2023` for `--years 2021,2022,2023`)
- `integrated_person_year_<year>.json` (`build_integrated_tables`)

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
