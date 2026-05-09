# Longevity Lab

Longevity Lab is a local-first product prototype for interactive organ-level lifestyle risk communication, built on public health data, calibrated interpretable models, and a React + FastAPI interface.

## Project status

This repo is intentionally usable *today* (end-to-end UI <-> API), and it now includes a real local training/evaluation path for tree-based artifact bundles.

- Current state: typed API + runnable UI + explicit compare/apply UX + a reference-based silhouette
  heatmap + BRFSS/EPA/PLACES/ACS/SVI evidence pipeline + promoted XGBoost/SHAP artifact serving,
  Community Context evidence panels, and Hydra/Optuna training entrypoints that write calibrated
  per-condition artifact bundles with metrics, prediction samples, explanations, and ablation metrics.
- Default serving mode is `auto`: the backend uses a valid local artifact bundle when present and
  otherwise falls back to clearly labeled demo scoring.
- Current production path: public GitHub Release model/evidence bundles are downloaded and verified
  during Render builds; raw/processed datasets and local model artifacts stay out of git.
- Product expansion roadmap: `docs/roadmap.md`
- Completed expansion plan history: `docs/superpowers/plans/2026-04-30-longevity-lab-expansion.md`
- Feature/status tracker: `docs/feature_status.md`

## Stack

- `frontend/`: Vite + React + TypeScript + D3 utilities
- `src/longevity_lab/`: FastAPI API, domain model, public-data pipeline, training, and serving code
- `data/`: raw/processed/sample data layout
- `docs/`: architecture, roadmap, contracts, and implementation plans
  - Feature tracker: `docs/feature_status.md`
  - Product roadmap: `docs/roadmap.md`
  - Historical Superpowers PR plan: `docs/superpowers/plans/2026-04-30-longevity-lab-expansion.md`

## Why this repo is structured this way

- The data pipeline, model artifacts, organ mappings, and UI contracts are tightly coupled.
- A single repo keeps schemas, docs, and boilerplate in one place without monorepo tooling overhead.

## Quick start

Start here if you are new to the repo:

1. Read `docs/quickstart.md` for the full developer flow.
2. Read `CONTRIBUTING.md` + `docs/git_workflow.md` before opening a PR.
3. Use `docs/feature_status.md` to find the next work item and check what is real vs demo.

### Prereqs

- Python 3.12+
- PDM 2.26+ (`pipx install pdm`)
- Node.js 22+ (npm 10+)

### One-command bootstrap

PowerShell:

```powershell
.\scripts\bootstrap_dev.ps1
```

bash/zsh:

```bash
bash scripts/bootstrap_dev.sh
```

The bootstrap installs backend dev and training dependencies plus frontend lockfile dependencies by
default. For optional SHAP/notebook work, add `-Explainability -Notebook` in PowerShell or
`--explainability --notebook` in bash/zsh.

### Backend

Optional: copy `.env.example` to `.env` to override local settings (engine selection, paths).
If your frontend runs on a different port, update `LONGEVITY_LAB_CORS_ALLOW_ORIGINS` (no `*`).
If you use the Vite `/api` proxy (default), you can also set it empty to disable CORS.

PowerShell:

```powershell
pdm run python -m uvicorn longevity_lab.api.main:app --reload
```

bash/zsh:

```bash
pdm run python -m uvicorn longevity_lab.api.main:app --reload
```

Verify:

```powershell
curl.exe http://127.0.0.1:8000/api/health
```

bash/zsh:

```bash
curl http://127.0.0.1:8000/api/health
```

### Frontend

PowerShell:

```powershell
cd frontend
npm ci
npm run dev
```

bash/zsh:

```bash
cd frontend
npm ci
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000`.
For deployed static frontends, set `VITE_API_BASE_URL` at build time to the backend origin without
`/api`. For local frontend-only overrides, copy `frontend/.env.example` to `frontend/.env`.

See `docs/quickstart.md` for common workflows (tests, lint, running both).

### Launch the dashboard

- Explorer view: `http://localhost:5173/`
- Data Evidence view: `http://localhost:5173/#/data`
- Community Context view: `http://localhost:5173/#/community`
- Model Cards view: `http://localhost:5173/#/models`
- Scenario Lab view: `http://localhost:5173/#/lab`

Use the Explorer page for the organ heatmap + drill-down flow. Current and what-if inputs stay
visible side by side, and the scores update live as sliders move. Use the `Delta | Baseline |
Scenario` toggle to switch the body view. Live slider scoring intentionally calls the fast
`/api/scenario/compare` path without explanations; selected drill-down SHAP/rule-path details load
separately through `/api/scenario/explain` so explanation generation does not block score updates.
Use the Data Evidence page to distinguish active scoring inputs from local-only data, generated
reports, validation context, and inactive geography features. Use Community Context for ACS/SVI,
PLACES, and causal-workbench evidence that does not modify Explorer personal scoring. Use Model
Cards to inspect active model metadata and Scenario Lab to summarize the current what-if
comparison.

## Deployment

See `docs/deployment.md` for the free-tier deployment profile. The checked-in `render.yaml`
configures a Render FastAPI service plus an optional Render static frontend. Vercel can also serve
the static frontend from `frontend/` when `VITE_API_BASE_URL` points to the deployed API origin.
Do not commit raw datasets or trained artifact bundles for deployment.

### Run all checks

PowerShell:

```powershell
.\scripts\check_all.ps1
```

bash/zsh:

```bash
bash scripts/check_all.sh
```

## E2E smoke test (Playwright)

```powershell
cd frontend
npm run test:e2e
```

Current smoke coverage:

- app loads and renders the compare flow
- organ drill-down opens from the heatmap/callout interaction
- heatmap mode toggle switches between delta and absolute views
- numeric inputs clamp to supported ranges
- live slider edits update results automatically through the no-explanation compare path
- selected drill-down explanations refresh separately after score updates settle
- stale comparison results clear correctly after a failed compare request

## Training and evaluation

Install the training extras before running the model pipeline:

```powershell
pdm install -G dev -G train
```

Train a calibrated bundle from the integrated 2023 table:

```powershell
pdm run python -m longevity_lab.pipeline.train
```

Summarize the latest bundle:

```powershell
pdm run python -m longevity_lab.pipeline.evaluate
```

Write report-ready overall + subgroup metrics:

```powershell
pdm run python -m longevity_lab.pipeline.evaluate artifacts.output_path=artifacts/models/eval-summary.json artifacts.slice_output_path=artifacts/models/eval-slices.json
```

The API auto-detects a valid local bundle by default. To require artifact mode and fail fast when
no valid bundle exists, set:

```powershell
$env:LONGEVITY_LAB_ENGINE='artifact'
```

Optional:

```powershell
$env:LONGEVITY_LAB_ARTIFACT_BUNDLE='real-20260508-xgboost-shap'
```

The default training scope covers eight BRFSS-derived conditions: heart disease, chronic lung
disease, asthma, stroke, depression, diabetes, chronic kidney disease, and arthritis. Bundled
outputs are written under `artifacts/models/<bundle_id>/` (gitignored) and include:

- `manifest.json`
- `training_summary.json`
- per-condition calibrated pipelines, explanation pipelines, metrics JSONs, prediction Parquet files,
  feature-importance JSONs, and tree text dumps

## Analysis reports

Scripted reports are the canonical analysis evidence path. Legacy notebooks from the project
prototype are kept outside tracked source under `legacy_artifacts/` and are optional exploration
artifacts only.

Generate the processed-data EDA report:

```powershell
pdm run python -m longevity_lab.reports.eda --config conf/reports/eda.yaml
```

Outputs are written under gitignored `reports/eda/` as JSON summaries, SVG/PNG figures, Markdown,
and HTML. See `docs/reports.md` for the input contract and override flags.

## Repo layout

```text
frontend/                 React UI
src/longevity_lab/        Python package
  api/                    FastAPI app and routes
  domain/                 Typed domain definitions
  services/               Metadata and scenario services
  pipeline/               Data ingest, training, and evaluation entrypoints
  reports/                Scripted EDA/report generation
tests/                    Backend tests
data/
  sample/                 Small checked-in demo assets only
  external/               Ignored raw public datasets
  processed/              Ignored derived tables and snapshots
artifacts/
  models/                 Ignored trained model artifacts
  evidence/               Ignored public evidence bundles for deployed context pages
reports/                  Ignored generated report outputs
docs/                     Architecture, roadmap, contracts, and implementation plans
```

## Current scope

This product prototype currently ships with:

- a typed FastAPI backend,
- a runnable React frontend,
- a deterministic demo scenario engine as an explicit fallback,
- artifact-backed calibrated model serving when a valid local bundle is available,
- BRFSS, EPA AirData, ACS, SVI, and PLACES ingest/build scripts (to `data/processed/`, gitignored),
- optional public evidence-bundle download for deployed Community Context panels without changing
  Explorer scoring.

It does **not** commit trained model artifacts, raw/processed datasets, or final polished anatomical
art assets. Trained bundles are produced locally under `artifacts/models/`; public evidence bundles
are downloaded under `artifacts/evidence/`. Both artifact families are intentionally gitignored.

## Pipeline (download + build)

This writes raw data to `data/external/` and derived tables to `data/processed/` (both gitignored).
If you skip this, the app still runs, but the UI's **Data Evidence** page will show the expected artifacts as "Missing".

These CLIs default to the repo-root `data/` directory even if you run them from `frontend/` or
another subdirectory.

```powershell
pdm run python -m longevity_lab.pipeline.download_brfss --year 2023
pdm run python -m longevity_lab.pipeline.download_epa_airdata --year 2023
pdm run python -m longevity_lab.pipeline.download_acs --year 2022
pdm run python -m longevity_lab.pipeline.download_svi --year 2022
pdm run python -m longevity_lab.pipeline.download_places --year 2025
pdm run python -m longevity_lab.pipeline.build_brfss_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_epa_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_context_tables --year 2022
pdm run python -m longevity_lab.pipeline.build_places_tables --year 2025
pdm run python -m longevity_lab.pipeline.build_integrated_tables --year 2023 --context-year 2022
pdm run python -m longevity_lab.pipeline.build_duckdb_views
```

Note: EPA 2023 does not include a Guam state row. The integrated build keeps those BRFSS rows with
`annual_aqi = null` by default and still raises for unexpected missing joins.
SVI is currently registry-supported through the 2022 release, while PLACES uses the 2025 county
release. The integrated 2023 table uses `--context-year 2022` to record that ACS/SVI context vintage
explicitly in `context_data_year` instead of silently pretending it is 2023 context.

Verify:

```powershell
curl.exe http://127.0.0.1:8000/api/pipeline/status?year=2023
```

## Documentation map

- Start here: `docs/quickstart.md`
- Feature/status tracker: `docs/feature_status.md`
- Contributing guidelines: `CONTRIBUTING.md` + `docs/git_workflow.md`
- Dataset sources + download notes: `docs/datasets.md`
- Data dictionary (fields + transformations): `docs/data_dictionary.md`
- Scripted reports: `docs/reports.md`
- Schema contracts (tables/views): `docs/schema_contracts.md`
- Architecture rationale: `docs/architecture.md`
- Baseline implementation history: `docs/implementation_plan.md`
- Git workflow: `docs/git_workflow.md`
- Developer quickstart: `docs/quickstart.md`
- Deployment profile: `docs/deployment.md`
