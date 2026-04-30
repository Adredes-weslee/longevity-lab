# Scripted Reports

Scripted reports are the canonical evidence path for exploratory analysis. Notebooks may still live
outside tracked source as optional exploration artifacts, but they should not be cited as the source
of truth for metrics, figures, or tables used in submissions and model work.

## EDA Report

The EDA command reads processed Parquet tables only. It does not download raw data and should be safe
to run repeatedly after the pipeline has built `data/processed/` outputs.

```powershell
pdm run python -m longevity_lab.reports.eda --config conf/reports/eda.yaml
```

Optional overrides:

```powershell
pdm run python -m longevity_lab.reports.eda --year 2023 --output-dir reports/eda
pdm run python -m longevity_lab.reports.eda --base-dir data --years 2022,2023
```

Default outputs are written under `reports/eda/`, which is gitignored:

- `summaries/eda_summary.json`: row counts, columns, numeric summaries, categorical counts, label
  prevalence, optional processed-table presence, and notebook policy.
- `figures/condition_prevalence.svg` and `.png`: condition-label prevalence chart.
- `figures/feature_missingness.svg` and `.png`: top configured missingness chart.
- `eda_report.md`: Markdown report for review and submission drafting.
- `eda_report.html`: static HTML rendering of the same scripted evidence.

The default config is JSON-compatible YAML so the report runner can parse it without adding a YAML
runtime dependency. Add fields there before changing report code when a new processed table or
feature family should appear in the EDA output.

## Input Contract

The required input is:

- `data/processed/integrated/<year>/integrated_person_year.parquet`

The command also records availability and shape for these optional processed tables when present:

- `data/processed/epa_airdata/annual_aqi_state_year.parquet`
- `data/processed/context/context_state_year.parquet`
- `data/processed/context/context_county_year.parquet`

Report tests use synthetic processed Parquet files under a temporary `data/processed/` tree. They
must not depend on raw downloads or local full-size data.
