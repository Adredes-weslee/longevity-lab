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

### EPA AirData - Annual AQI by county (2023)

- Download page: `https://aqs.epa.gov/aqsweb/airdata/download_files.html#Annual`
- Zip (county-year): `https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_county_2023.zip`

Expected local paths (gitignored):

- `data/external/epa_airdata/annual_aqi_by_county_2023.zip`
- `data/external/epa_airdata/annual_aqi_by_county_2023/annual_aqi_by_county_2023.csv`

Notes:

- The raw file contains `State` and `County` names but **no FIPS codes**. Our v1 join is therefore **state-year**:
  we map `State` name -> `state_fips` and aggregate county rows to `annual_aqi_state_year` (see `docs/data_dictionary.md`).
- Registry source ID: `epa_airdata_annual_aqi_by_county`.

## Download commands (Windows)

Preferred (uses our scripts so provenance is recorded consistently):

```powershell
pdm run python -m longevity_lab.pipeline.download_brfss --year 2023
pdm run python -m longevity_lab.pipeline.download_epa_airdata --year 2023
```

Recommended first-time full local build:

1. Download BRFSS + EPA raw files
2. Build BRFSS processed tables
3. Build EPA processed tables
4. Build the integrated person-year table
5. Build DuckDB views
6. Verify in the dashboard Data integration page or `GET /api/pipeline/status`

## Build processed tables (after download)

These scripts convert raw downloads into the v1 processed Parquet contracts under `data/processed/`
and optionally build a local DuckDB file with stable views.

The pipeline CLIs default to the repo-root `data/` directory even if you invoke them from
`frontend/` or another subdirectory.

```powershell
pdm run python -m longevity_lab.pipeline.build_brfss_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_epa_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_integrated_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_duckdb_views
```

Note: EPA 2023 does not include a Guam state row. The integrated build keeps those BRFSS rows with
`annual_aqi = null` by default and still raises for unexpected missing joins.

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

EPA AirData (AQI by county) 2023:

```powershell
New-Item -ItemType Directory -Force -Path data\external\epa_airdata | Out-Null
curl.exe -L --fail --retry 3 --retry-delay 2 --ssl-no-revoke `
  -o data\external\epa_airdata\annual_aqi_by_county_2023.zip `
  https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_county_2023.zip
Expand-Archive -Path data\external\epa_airdata\annual_aqi_by_county_2023.zip -DestinationPath data\external\epa_airdata\annual_aqi_by_county_2023 -Force
```
