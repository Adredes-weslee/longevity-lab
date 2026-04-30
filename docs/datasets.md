# Datasets (sources, versions, and download notes)

This project uses **public** datasets and keeps raw/processed data **out of git**.

Raw downloads belong under `data/external/` (gitignored). Derived tables belong under `data/processed/` (gitignored).

## Data-source registry (v1)

Scriptable public sources are registered in `conf/data_sources.yaml`. Each record includes:

- `source_id`, title, official landing URL, and concrete download URL template.
- Supported years, geography, expected local file pattern, and local landing path.
- Checksum policy and license/terms notes for provenance review.

The registry is intentionally small and curated: it includes only sources that are already used by
the local pipeline or are approved for near-term ingestion. Download scripts enrich each provenance
JSON with a `source_registry` block so raw files can be traced back to the exact registry record.

## Baseline dataset choices (v1)

For reproducibility and easy onboarding (no auth tokens), we prefer **official** sources over third-party mirrors.

### BRFSS (CDC) - 2023 LLCP microdata

- Landing page: `https://www.cdc.gov/brfss/annual_data/annual_2023.html`
- Microdata (SAS transport): `https://www.cdc.gov/brfss/annual_data/2023/files/LLCP2023XPT.zip`
- Codebook zip (HTML): `https://www.cdc.gov/brfss/annual_data/2023/zip/codebook23_llcp-v2-508.zip`

Expected local paths (gitignored):

- `data/external/brfss/2023/LLCP2023XPT.zip`
- `data/external/brfss/2023/LLCP2023.XPT`
- `data/external/brfss/2023/codebook/USCODE23_LLCP_*.HTML`

Notes:

- We use the **CDC release** instead of third-party mirrors to avoid external credentials and keep provenance clear.
- Registry source IDs: `cdc_brfss_llcp_xpt`, `cdc_brfss_llcp_codebook`.

### EPA AirData - Annual AQI and annual concentration summaries (2023)

- Download page: `https://aqs.epa.gov/aqsweb/airdata/download_files.html#Annual`
- Zip (county-year): `https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_county_2023.zip`
- Zip (monitor-year annual concentration): `https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_2023.zip`

Expected local paths (gitignored):

- `data/external/epa_airdata/annual_aqi_by_county_2023.zip`
- `data/external/epa_airdata/annual_aqi_by_county_2023/annual_aqi_by_county_2023.csv`
- `data/external/epa_airdata/annual_conc_by_monitor_2023.zip`
- `data/external/epa_airdata/annual_conc_by_monitor_2023/annual_conc_by_monitor_2023.csv`

Notes:

- The raw file contains `State` and `County` names but **no FIPS codes**. Our v1 join is therefore **state-year**:
  we map `State` name -> `state_fips` and aggregate county rows to `annual_aqi_state_year` (see `docs/data_dictionary.md`).
- The annual concentration file contains monitor-year records with FIPS codes, parameter codes, observation counts,
  observation percentages, and EPA completeness indicators. The local pipeline filters it to PM2.5 (`88101`) and ozone (`44201`).
- Registry source IDs: `epa_airdata_annual_aqi_by_county`, `epa_airdata_annual_conc_by_monitor`.

### Census ACS 5-year API - curated context variables

- Developer page: `https://www.census.gov/data/developers/data-sets/acs-5year.html`
- API endpoint template: `https://api.census.gov/data/{year}/acs/acs5`
- Current local registry support: ACS 5-year releases 2017-2024 for the curated variable set.

Expected local paths (gitignored):

- `data/external/acs/acs5/<year>/acs5_state_context.json`
- `data/external/acs/acs5/<year>/acs5_county_context.json`

Curated feature families:

- Poverty, median household income, bachelor's degree or higher, uninsured population, disability, broadband subscription, and total population for state aggregation weights.
- The raw downloads include the ACS estimate variables and corresponding MOE variables needed to record `*_moe_available` flags in processed outputs.
- The downloader splits ACS API calls into chunks under the Census API variable limit, then merges them into the expected local JSON files.
- Registry source ID: `census_acs5_api_context`.

### CDC/ATSDR SVI - U.S. county CSV

- Download page: `https://svi.cdc.gov/dataDownloads/data-download.html`
- CSV URL template: `https://svi.cdc.gov/Documents/Data/<year>/csv/states_counties/SVI_<year>_US_county.csv`
- Current local registry support: 2014, 2016, 2018, 2020, and 2022 for the selected SVI percentile fields.

Expected local path (gitignored):

- `data/external/svi/<year>/SVI_<year>_US_county.csv`

Notes:

- The pipeline uses the U.S. county CSV so county percentiles are ranked against counties nationally.
- SVI percentile fields should not be compared as time-series measures across SVI releases; CDC/ATSDR ranks each release within its own year.
- Registry source ID: `cdc_atsdr_svi_us_county_csv`.

### CDC PLACES - County Open Data, 2025 release

- Data portal: `https://www.cdc.gov/places/tools/data-portal.html`
- CSV download: `https://data.cdc.gov/api/views/swc5-untb/rows.csv?accessType=DOWNLOAD`
- Current local registry support: PLACES 2025 county Open Data release.

Expected local path (gitignored):

- `data/external/places/county/<release-year>/places_county_<release-year>.csv`

Curated measures:

- Modeled condition context: CHD, COPD, stroke, depression, and diagnosed diabetes.
- Behavior/context measures aligned with scenario inputs: current smoking, binge drinking, no leisure-time physical activity, obesity, and short sleep duration.

Notes:

- PLACES values are modeled aggregate geography estimates. They are useful for county context and external reasonableness checks, but they are **not** independent person-level labels for model training or evaluation.
- The local `--year` flag refers to the PLACES release year. The raw PLACES `year` column is preserved separately in processed outputs as the estimate year.
- Registry source ID: `cdc_places_county_opendata`.

## Download commands (Windows)

Preferred (uses our scripts so provenance is recorded consistently):

```powershell
pdm run python -m longevity_lab.pipeline.download_brfss --year 2023
pdm run python -m longevity_lab.pipeline.download_epa_airdata --year 2023
pdm run python -m longevity_lab.pipeline.download_acs --year 2022
pdm run python -m longevity_lab.pipeline.download_svi --year 2022
pdm run python -m longevity_lab.pipeline.download_places --year 2025
```

Recommended first-time full local build:

1. Download BRFSS + EPA raw files
2. Build BRFSS processed tables
3. Build EPA processed county-year and state-year tables
4. Build the integrated person-year table
5. Build DuckDB views
6. Verify in the dashboard Data integration page or `GET /api/pipeline/status`

## Build processed tables (after download)

These scripts convert raw downloads into processed Parquet contracts under `data/processed/`
and optionally build a local DuckDB file with stable views.

The pipeline CLIs default to the repo-root `data/` directory even if you invoke them from
`frontend/` or another subdirectory.

```powershell
pdm run python -m longevity_lab.pipeline.build_brfss_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_epa_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_context_tables --year 2022
pdm run python -m longevity_lab.pipeline.build_places_tables --year 2025
pdm run python -m longevity_lab.pipeline.build_integrated_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_duckdb_views
```

External PLACES reasonableness report:

```powershell
pdm run python -m longevity_lab.pipeline.validate_external_context `
  --year 2025 `
  --model-aggregate-path data\processed\validation\model_aggregates.csv
```

Use `--bundle-dir artifacts\models\<bundle-id>` instead of `--model-aggregate-path` to summarize per-condition prediction parquet files from a local trusted model bundle. The report writes CSV/JSON outputs under `data/processed/validation/` and provenance under `data/processed/provenance/`.

Note: EPA 2023 does not include a Guam state row. The integrated build keeps those BRFSS rows with
`annual_aqi = null` by default and still raises for unexpected missing joins.
PM2.5 and ozone exposure means are added only when EPA monitor rows pass quality checks:
`Completeness Indicator == Y`, observation percent at least 75, positive observation count, and non-null annual mean.
Incomplete pollutant rows still contribute monitor/completeness flags but not exposure means.

Tip: the UI includes a separate **Data integration** page (calls `GET /api/pipeline/status`) to show whether
these raw/processed artifacts exist locally.

If `curl.exe` fails with a certificate revocation error on Windows, add `--ssl-no-revoke`.

BRFSS 2023:

```powershell
New-Item -ItemType Directory -Force -Path data\external\brfss\2023 | Out-Null
curl.exe -L --fail --retry 3 --retry-delay 2 --ssl-no-revoke `
  -o data\external\brfss\2023\LLCP2023XPT.zip `
  https://www.cdc.gov/brfss/annual_data/2023/files/LLCP2023XPT.zip
Expand-Archive -Path data\external\brfss\2023\LLCP2023XPT.zip -DestinationPath data\external\brfss\2023 -Force

curl.exe -L --fail --retry 3 --retry-delay 2 --ssl-no-revoke `
  -o data\external\brfss\2023\codebook23_llcp-v2-508.zip `
  https://www.cdc.gov/brfss/annual_data/2023/zip/codebook23_llcp-v2-508.zip
Expand-Archive -Path data\external\brfss\2023\codebook23_llcp-v2-508.zip -DestinationPath data\external\brfss\2023\codebook -Force
```

EPA AirData (AQI by county and annual concentration by monitor) 2023:

```powershell
New-Item -ItemType Directory -Force -Path data\external\epa_airdata | Out-Null
curl.exe -L --fail --retry 3 --retry-delay 2 --ssl-no-revoke `
  -o data\external\epa_airdata\annual_aqi_by_county_2023.zip `
  https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_county_2023.zip
Expand-Archive -Path data\external\epa_airdata\annual_aqi_by_county_2023.zip -DestinationPath data\external\epa_airdata\annual_aqi_by_county_2023 -Force

curl.exe -L --fail --retry 3 --retry-delay 2 --ssl-no-revoke `
  -o data\external\epa_airdata\annual_conc_by_monitor_2023.zip `
  https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_2023.zip
Expand-Archive -Path data\external\epa_airdata\annual_conc_by_monitor_2023.zip -DestinationPath data\external\epa_airdata\annual_conc_by_monitor_2023 -Force
```
